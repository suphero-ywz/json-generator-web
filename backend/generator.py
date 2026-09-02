"""
生成调度器

根据模式生成动作数据：
- LLM 模式：调用 DeepSeek / Ollama API 创造全新动作。数据 100% 由 LLM 产出——
  调用失败的缺口留待下一轮继续 LLM 重试，轮数预算（MAX_LLM_ROUNDS）耗尽后
  如实返回缺量，绝不混入要素池数据。
- 要素池模式：组合要素生成动作（纯本地同步生成），预算轮后保留放宽去重的补齐语义。

质量护栏：LLM 产出逐条过 validate_content（内容护栏：部位越界/物理禁词/情绪-速度/
次数上限），违规丢弃、缺口由后续轮次自动补，丢弃数随 meta 返回。

去重：query 单键指纹，任务级共享（单次任务或批量全部文件共用一个 seen，
同 query 文件间硬拦截不入列）+ 类别级调用互斥锁 + provider 级全局防重提示窗口
（recent 仅提示、跨任务压低复读概率）——指纹层保证任务内零重复，提示层
压低跨任务撞车，同类别 LLM 调用全局串行（跨文件、跨任务）。

支持单次生成和批量生成（文件级有界并发）。
"""

from __future__ import annotations
import uuid
import asyncio
import json
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from element_generator import generate_single as pool_generate_single
from llm_client import generate_batch as llm_generate_batch
from llm_client import RECENT_QUERY_LIMIT, env_int
from validator import validate_content
from database import add_many_to_pool, save_history


# 性能调优旋钮（可在 .env 中覆盖，main.py 先于本模块加载 .env）
CONCURRENCY = env_int("GEN_CONCURRENCY", 12)                      # 云端 DeepSeek 并发请求数
OLLAMA_CONCURRENCY = env_int("GEN_OLLAMA_CONCURRENCY", 2)         # Ollama 并发（本地推理，实测 GPU/CPU 下 2 最优，可自行调优）
BATCH_SIZE = env_int("GEN_BATCH_SIZE", 5)                         # DeepSeek 每次 API 调用生成的记录数
OLLAMA_BATCH_SIZE = env_int("GEN_OLLAMA_BATCH_SIZE", 3)           # Ollama 独立小批（控制单次推理时长）
FILE_CONCURRENCY = env_int("GEN_FILE_CONCURRENCY", 3)             # DeepSeek 批量任务文件级并发
OLLAMA_FILE_CONCURRENCY = env_int("GEN_OLLAMA_FILE_CONCURRENCY", 1)  # Ollama 文件级保持串行（CPU 已打满）
# 生成预算（轮）：每轮每个类别尝试补齐其剩余配额，缺口自动滚入下一轮。
# LLM 模式耗尽后如实报缺（不混要素池）；要素池模式耗尽后进入放宽补齐。
MAX_LLM_ROUNDS = env_int("MAX_LLM_ROUNDS", 8)
MAX_POOL_ROUNDS = env_int("MAX_POOL_ROUNDS", 20)

# 取消回调：返回 True 时生成立即中止
ShouldCancel = Optional[Callable[[], Awaitable[bool]]]


# --- 全局防重提示窗口（按类别共享） ---
# LLM prompt 中「严禁重复」窗口的 query 来源：同类别全局共享（跨文件/跨任务），
# 配合类别锁保证同类调用互斥 —— 任何一次调用的提示都覆盖此前同类全部产出。
_recent_by_category: dict[str, deque] = {}
_category_locks: dict[str, asyncio.Lock] = {}


def _category_recent(category: str) -> deque:
    dq = _recent_by_category.get(category)
    if dq is None:
        dq = deque(maxlen=RECENT_QUERY_LIMIT)
        _recent_by_category[category] = dq
    return dq


def _category_lock(category: str) -> asyncio.Lock:
    lock = _category_locks.get(category)
    if lock is None:
        lock = asyncio.Lock()
        _category_locks[category] = lock
    return lock


# --- 生成会话状态 ---

@dataclass
class GenerationState:
    """一次生成会话（单次任务，或批量中的一个文件）的共享状态与统计。

    seen 为任务级共享指纹（由 generate / generate_batch 创建后注入）：
    批量任务的全部文件共用一个 seen——文件间同 query 从指纹层硬拦，
    杜绝「文件 A 已产出、文件 B 复读」的跨文件重复（recent 窗口仅提示不强制）。
    """
    requested: int
    records: list = field(default_factory=list)
    seen: set = field(default_factory=set)   # 任务级共享已入列 query（单键指纹）
    llm_failures: int = 0                    # LLM 整批调用失败次数（重试预算链已耗尽）
    discarded: int = 0                       # 内容护栏丢弃条数
    rounds_used: int = 0                     # 实际消耗的轮数


def _provider_concurrency(provider: str) -> int:
    """按 provider 选择 LLM 并发数。"""
    return OLLAMA_CONCURRENCY if provider == "ollama" else CONCURRENCY


def _batch_size(provider: str) -> int:
    """按 provider 选择每次 API 调用的记录数。"""
    return OLLAMA_BATCH_SIZE if provider == "ollama" else BATCH_SIZE


_provider_sems: dict[str, asyncio.Semaphore] = {}


def _provider_sem(provider: str) -> asyncio.Semaphore:
    """provider 级全局并发闸门。

    模块级共享：批量任务多文件并行时所有调用共用同一闸门，
    总并发恒等于 _provider_concurrency(provider)，不会随文件数膨胀。
    """
    if provider not in _provider_sems:
        _provider_sems[provider] = asyncio.Semaphore(_provider_concurrency(provider))
    return _provider_sems[provider]


async def _check_cancel(should_cancel: ShouldCancel) -> None:
    """检查是否应取消（用户点击停止 / 客户端断开），是则抛出取消异常。"""
    if should_cancel is not None and await should_cancel():
        raise asyncio.CancelledError("生成已被取消")


def _calc_category_counts(
    categories: list[dict], total_count: int
) -> dict[str, int]:
    """根据权重计算各类别的实际条数。"""
    total_weight = sum(c["weight"] for c in categories)
    counts = {}
    allocated = 0

    for i, c in enumerate(categories):
        if i == len(categories) - 1:
            counts[c["name"]] = total_count - allocated
        else:
            counts[c["name"]] = max(1, math.floor(total_count * c["weight"] / total_weight))
            allocated += counts[c["name"]]

    if total_count >= len(categories):
        for name in counts:
            if counts[name] < 1:
                counts[name] = 1

    return counts


# === 类别生成管道 ===

async def _run_category_pipeline(
    category: str,
    quota: int,
    use_llm: bool,
    provider: str,
    state: GenerationState,
    progress: Optional[dict],
    should_cancel: ShouldCancel,
) -> int:
    """类别管道：串行补齐该类别本轮配额，返回新增条数。

    LLM 模式：持类别锁（同类别全局互斥）逐次调用（每次 ≤ 批大小），产出逐条过
    validate_content，违规丢弃。一次调用失败或零新增即返回，剩余缺口留待下一轮
    （轮数预算兜底，避免同类死循环占锁）。
    要素池模式：同步组合生成，去重由 state.seen 指纹保证。
    """
    added = 0
    if use_llm:
        recent = _category_recent(category)
        async with _category_lock(category):
            while added < quota:
                await _check_cancel(should_cancel)
                n = min(quota - added, _batch_size(provider))
                async with _provider_sem(provider):
                    records = await llm_generate_batch(
                        category, n, list(recent), provider=provider)
                if not records:
                    state.llm_failures += 1
                    break
                before = added
                for r in records:
                    ok, _err = validate_content(r)
                    if not ok:
                        state.discarded += 1
                        continue
                    q = r.get("query", "")
                    if q and q not in state.seen:
                        state.seen.add(q)
                        recent.append(q)
                        state.records.append(r)
                        added += 1
                        if progress is not None:
                            progress["completed"] += 1
                if added == before:
                    break  # 调用成功但零入列（全坏/全撞）：下轮再试
        return added

    # 要素池：同步批量生成，定期让出事件循环以便进度轮询及时插队
    counter = 0
    while added < quota:
        await _check_cancel(should_cancel)
        rec = pool_generate_single(category, state.seen)
        if rec is None:
            break  # 素材组合尝试耗尽
        state.seen.add(rec["query"])
        state.records.append(rec)
        added += 1
        if progress is not None:
            progress["completed"] += 1
        counter += 1
        if counter % 5 == 0:
            await _check_cancel(should_cancel)
            await asyncio.sleep(0)
    return added


async def _fill_remaining_relaxed(
    categories: list[dict],
    total_count: int,
    state: GenerationState,
    progress: Optional[dict],
    should_cancel: ShouldCancel,
) -> None:
    """要素池末段：放宽去重（无视指纹）补齐缺口，最多 5 轮（沿用历史兜底语义）。"""
    for _ in range(5):
        await _check_cancel(should_cancel)
        shortfall = total_count - len(state.records)
        if shortfall <= 0:
            break
        sf_by_cat = _calc_category_counts(categories, shortfall)
        added = 0
        for cat, n in sf_by_cat.items():
            for _ in range(n):
                rec = pool_generate_single(cat, set())
                if rec is None:
                    continue
                state.records.append(rec)
                added += 1
                if progress is not None:
                    progress["completed"] += 1
        await asyncio.sleep(0)
        if added == 0:
            break


async def _generate_records(
    categories: list[dict],
    total_count: int,
    use_llm: bool,
    provider: str,
    seen: set,
    progress: Optional[dict],
    should_cancel: ShouldCancel,
) -> GenerationState:
    """核心生成循环（单次生成与批量每文件共用）。

    seen: 任务级共享指纹集——批量任务各文件注入同一 set，
        文件间同 query 硬拦截（q 已入列即弃）。
    LLM 模式：预算轮内各类别管道重试补齐，耗尽即止，缺口如实保留。
    要素池模式：预算轮后追加放宽去重的补齐段。
    """
    state = GenerationState(requested=total_count, seen=seen)
    max_rounds = MAX_LLM_ROUNDS if use_llm else MAX_POOL_ROUNDS

    for _ in range(max_rounds):
        await _check_cancel(should_cancel)
        shortfall = total_count - len(state.records)
        if shortfall <= 0:
            break
        shortfall_by_cat = _calc_category_counts(categories, shortfall)
        pending = [(cat, n) for cat, n in shortfall_by_cat.items() if n > 0]
        if not pending:
            break
        results = await asyncio.gather(*[
            _run_category_pipeline(cat, n, use_llm, provider, state,
                                   progress, should_cancel)
            for cat, n in pending
        ])
        state.rounds_used += 1
        # LLM 模式：失败/撞车缺口一律滚入下一轮重试，预算（MAX_LLM_ROUNDS）
        # 本身即兜底，不提前中断。要素池模式：全零 = 素材穷尽，停止空转。
        if not use_llm and sum(results) == 0:
            break

    if not use_llm:
        await _fill_remaining_relaxed(
            categories, total_count, state, progress, should_cancel)

    return state


def _build_meta(state: GenerationState) -> dict:
    """生成结果元数据：纯度/质量/预算统计（meta 随 API 返回，前端可展示）。"""
    generated = len(state.records)
    return {
        "generated": generated,
        "missing": max(0, state.requested - generated),
        "rounds_used": state.rounds_used,
        "llm_failures": state.llm_failures,
        "discarded": state.discarded,
    }


def _enrich_records(records: list[dict], actor_id: str = "Skeleton0") -> None:
    """补齐字段并按模板顺序重排。"""
    for i, r in enumerate(records):
        a_id = f"{i + 1}_{actor_id}"
        rid = f"{i + 1:04d}"
        intent = r.get("intent", "单意图动作")
        qd = r.get("query_description", f"[[{r.get('query', '')}]]")
        aug = r.get("aug_text", [r.get("text", "")] * 6)

        # 按模板顺序重建 dict
        keys_order = [
            "actor_id", "id", "query_description", "query", "text",
            "motion_description", "is_head", "voice_feedback", "category",
            "intent", "aug_text",
        ]
        ordered = {}
        for key in keys_order:
            if key == "actor_id":
                ordered[key] = a_id
            elif key == "id":
                ordered[key] = rid
            elif key == "query_description":
                ordered[key] = qd
            elif key == "intent":
                ordered[key] = intent
            elif key == "aug_text":
                ordered[key] = aug
            else:
                ordered[key] = r.get(key, "" if key != "is_head" else False)
        r.clear()
        r.update(ordered)


async def _persist(records: list[dict], mode: str) -> None:
    """已生成记录的 query 写入历史去重池（source 记模式）。"""
    if records:
        pool_records = [(d["query"], d["category"], mode) for d in records]
        await add_many_to_pool(pool_records)


# === 对外入口 ===

async def generate(
    categories: list[dict],
    total_count: int,
    mode: str,
    actor_id: str = "Skeleton0",
    provider: str = "auto",
    should_cancel: ShouldCancel = None,
    progress: Optional[dict] = None,
) -> dict:
    """单次生成（带重试补全；LLM 模式缺量如实返回，不混要素池）。

    Args:
        progress: 进度共享 dict（main.py 注册），每条记录完成时 completed += 1
    """
    use_llm = (mode == "llm")
    state = await _generate_records(
        categories, total_count, use_llm, provider, set(), progress, should_cancel)

    # 取消后不再保存任何数据
    await _check_cancel(should_cancel)
    _enrich_records(state.records, actor_id)
    record_id = str(uuid.uuid4())

    await _persist(state.records, mode)
    await save_history(
        record_id=record_id,
        gen_type="single",
        count_per_file=total_count,
        file_count=1,
        total_records=len(state.records),
        categories_json=json.dumps(categories, ensure_ascii=False),
    )

    stats = {name: sum(1 for d in state.records if d["category"] == name)
             for name in _calc_category_counts(categories, total_count)}

    return {
        "success": True,
        "mode": mode,
        "data": state.records,
        "record_id": record_id,
        "stats": stats,
        "meta": _build_meta(state),
    }


async def _generate_one_file(
    categories: list[dict],
    total_count: int,
    file_count: int,
    mode: str,
    actor_id: str,
    provider: str,
    seen: set,
    should_cancel: ShouldCancel,
    progress: Optional[dict] = None,
) -> dict:
    """生成一个文件的全部记录（共享核心循环），返回 {record_id, data, stats, meta}。

    seen: 任务级共享指纹（批量各文件共用），文件间去重硬保证。
    """
    use_llm = (mode == "llm")
    state = await _generate_records(
        categories, total_count, use_llm, provider, seen, progress, should_cancel)

    # 取消后不再保存任何数据
    await _check_cancel(should_cancel)
    _enrich_records(state.records, actor_id)
    file_id = str(uuid.uuid4())

    await _persist(state.records, mode)
    await save_history(
        record_id=file_id,
        gen_type="batch",
        count_per_file=total_count,
        file_count=file_count,
        total_records=len(state.records),
        categories_json=json.dumps(categories, ensure_ascii=False),
    )

    file_stats = {
        name: sum(1 for d in state.records if d["category"] == name)
        for name in _calc_category_counts(categories, total_count)
    }

    return {
        "record_id": file_id,
        "data": state.records,
        "stats": file_stats,
        "meta": _build_meta(state),
    }


async def generate_batch(
    categories: list[dict],
    total_count: int,
    file_count: int,
    mode: str,
    actor_id: str = "Skeleton0",
    provider: str = "auto",
    should_cancel: ShouldCancel = None,
    progress: Optional[dict] = None,
) -> dict:
    """批量生成（文件级有界并发，每个文件内带重试补全）。

    Args:
        progress: 进度共享 dict（main.py 注册），completed 累计所有文件条数，
            files_done 为已完成文件数
    """
    file_sem = asyncio.Semaphore(
        OLLAMA_FILE_CONCURRENCY if provider == "ollama" else FILE_CONCURRENCY)
    # 任务级共享指纹：全部文件共用一个 seen，文件间同 query 硬拦截
    shared_seen: set = set()

    async def _run_file() -> dict:
        async with file_sem:
            await _check_cancel(should_cancel)
            result = await _generate_one_file(
                categories, total_count, file_count, mode,
                actor_id, provider, shared_seen, should_cancel, progress)
            if progress is not None:
                progress["files_done"] += 1  # 文件正常完成才计数
            return result

    # gather 按传入顺序返回结果，files_data 顺序与文件序一致
    files_data = await asyncio.gather(*[_run_file() for _ in range(file_count)])

    # 顶层聚合纯度/缺口统计（rounds_used 按文件分布，不聚合以免误导）
    meta = {
        "generated": sum(f["meta"]["generated"] for f in files_data),
        "missing": sum(f["meta"]["missing"] for f in files_data),
        "llm_failures": sum(f["meta"]["llm_failures"] for f in files_data),
        "discarded": sum(f["meta"]["discarded"] for f in files_data),
    }

    return {
        "success": True,
        "mode": mode,
        "files": files_data,
        "meta": meta,
    }
