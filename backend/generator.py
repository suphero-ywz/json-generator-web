"""
生成调度器

根据 LLM 可用性自动选择生成模式：
- LLM 模式：调用 DeepSeek API 创造全新动作（并发 + 批量）
- 要素池模式：组合要素生成动作（兜底）

支持单次生成和批量生成。
"""

from __future__ import annotations
import uuid
import asyncio
import math
from typing import Awaitable, Callable, Optional
from element_generator import generate_single as pool_generate_single
from llm_client import generate_single as llm_generate_single
from llm_client import generate_batch as llm_generate_batch
from llm_client import RECENT_QUERY_LIMIT, env_int
from validator import validate_full
from database import add_many_to_pool, save_history


# 性能调优旋钮（可在 .env 中覆盖，main.py 先于本模块加载 .env）
CONCURRENCY = env_int("GEN_CONCURRENCY", 12)                      # 云端 DeepSeek 并发请求数
OLLAMA_CONCURRENCY = env_int("GEN_OLLAMA_CONCURRENCY", 2)         # Ollama 并发（本地推理，实测 GPU/CPU 下 2 最优，可自行调优）
BATCH_SIZE = env_int("GEN_BATCH_SIZE", 5)                         # DeepSeek 每次 API 调用生成的记录数
OLLAMA_BATCH_SIZE = env_int("GEN_OLLAMA_BATCH_SIZE", 3)           # Ollama 独立小批（控制单次推理时长）
FILE_CONCURRENCY = env_int("GEN_FILE_CONCURRENCY", 3)             # DeepSeek 批量任务文件级并发
OLLAMA_FILE_CONCURRENCY = env_int("GEN_OLLAMA_FILE_CONCURRENCY", 1)  # Ollama 文件级保持串行（CPU 已打满）

# 取消回调：返回 True 时生成立即中止
ShouldCancel = Optional[Callable[[], Awaitable[bool]]]


def _llm_concurrency(provider: str) -> int:
    """按 provider 选择 LLM 并发数。"""
    return OLLAMA_CONCURRENCY if provider == "ollama" else CONCURRENCY


def _batch_size(provider: str) -> int:
    """按 provider 选择每次 API 调用的记录数。"""
    return OLLAMA_BATCH_SIZE if provider == "ollama" else BATCH_SIZE


_provider_sems: dict[str, asyncio.Semaphore] = {}


def _provider_sem(provider: str) -> asyncio.Semaphore:
    """provider 级全局并发闸门。

    模块级共享：批量任务多文件并行时所有 chunk 共用同一闸门，
    总并发恒等于 _llm_concurrency(provider)，不会随文件数膨胀。
    """
    if provider not in _provider_sems:
        _provider_sems[provider] = asyncio.Semaphore(_llm_concurrency(provider))
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


def _split_into_chunks(
    category_counts: dict[str, int], batch_size: int = BATCH_SIZE
) -> list[tuple[str, int]]:
    """将每个类别的记录数拆分为 batch_size 大小的块。"""
    chunks = []
    for cat_name, total in category_counts.items():
        remaining = total
        while remaining > 0:
            size = min(batch_size, remaining)
            chunks.append((cat_name, size))
            remaining -= size
    return chunks


async def generate(
    categories: list[dict],
    total_count: int,
    mode: str,
    actor_id: str = "Skeleton0",
    provider: str = "auto",
    should_cancel: ShouldCancel = None,
    progress: Optional[dict] = None,
) -> dict:
    """单次生成，带重试补全确保达到目标条数。

    Args:
        progress: 进度共享 dict（main.py 注册），每条记录完成时 completed += 1
    """
    use_llm = (mode == "llm")
    category_counts = _calc_category_counts(categories, total_count)
    all_data: list[dict] = []
    all_queries: set[str] = set()
    max_rounds = 8 if use_llm else 20

    for _round in range(max_rounds):
        await _check_cancel(should_cancel)
        shortfall = total_count - len(all_data)
        if shortfall <= 0:
            break

        # 按比例分配剩余量
        shortfall_by_cat = _calc_category_counts(categories, shortfall)
        chunks = _split_into_chunks(shortfall_by_cat, _batch_size(provider))

        sem = _provider_sem(provider)

        async def _run_chunk(cat_name: str, count: int) -> int:
            """执行一个 chunk，完成后立即去重入列并更新进度，返回新增条数。

            进度更新放在 chunk 级（而非整轮 gather 之后），
            使长时间 LLM 任务的进度条按批推进，而不是 0→100 一跳。
            """
            async with sem:
                await _check_cancel(should_cancel)
                used = set(r["query"] for r in all_data)
                if use_llm:
                    recent = list(dict.fromkeys(
                        r["query"] for r in all_data))[-RECENT_QUERY_LIMIT:]
                    records = await llm_generate_batch(
                        cat_name, count, recent, provider=provider)
                    if not records:
                        records = [_pool_fallback(cat_name, used) for _ in range(count)]
                        records = [r for r in records if r is not None]
                else:
                    records = [pool_generate_single(cat_name, used) for _ in range(count)]
                    records = [r for r in records if r is not None]
                    # 让出事件循环：大批量同步生成时进度轮询请求能及时插队
                    await asyncio.sleep(0)
                added = 0
                for r in records:
                    fp = (r["query"], r["category"], r["motion_description"])
                    if fp not in all_queries:
                        all_data.append(r)
                        all_queries.add(fp)
                        added += 1
                        if progress is not None:
                            progress["completed"] += 1
                return added

        if not chunks:
            break

        results = await asyncio.gather(*[_run_chunk(cat, n) for cat, n in chunks])

        if sum(results) == 0:
            break

    # 最后一轮：放宽去重，允许同 query 不同 motion_description 的记录
    final_round = 0
    while len(all_data) < total_count and final_round < 5:
        await _check_cancel(should_cancel)
        final_round += 1
        sf = total_count - len(all_data)
        sf_by_cat = _calc_category_counts(categories, sf)
        extra_chunks = _split_into_chunks(sf_by_cat)
        sem2 = asyncio.Semaphore(CONCURRENCY)
        async def _run_relaxed(cat_name: str, cnt: int) -> int:
            async with sem2:
                await _check_cancel(should_cancel)
                added = 0
                for _ in range(cnt):
                    rec = pool_generate_single(cat_name, set())
                    if rec is None:
                        continue
                    all_data.append(rec)
                    added += 1
                    if progress is not None:
                        progress["completed"] += 1
                return added

        extra_results = await asyncio.gather(
            *[_run_relaxed(cat, n) for cat, n in extra_chunks]
        )
        if sum(extra_results) == 0:
            break

    # 取消后不再保存任何数据
    await _check_cancel(should_cancel)
    _enrich_records(all_data, actor_id)
    record_id = str(uuid.uuid4())

    if all_data:
        pool_records = [(d["query"], d["category"], mode) for d in all_data]
        await add_many_to_pool(pool_records)

    import json
    await save_history(
        record_id=record_id,
        gen_type="single",
        count_per_file=total_count,
        file_count=1,
        total_records=len(all_data),
        categories_json=json.dumps(categories, ensure_ascii=False),
    )

    stats = {name: sum(1 for d in all_data if d["category"] == name)
             for name in category_counts}

    return {
        "success": True,
        "mode": mode,
        "data": all_data,
        "record_id": record_id,
        "stats": stats,
    }


async def _generate_one_file(
    categories: list[dict],
    total_count: int,
    file_count: int,
    mode: str,
    actor_id: str,
    provider: str,
    should_cancel: ShouldCancel,
    progress: Optional[dict] = None,
) -> dict:
    """生成一个文件的全部记录（含重试补全），返回 {record_id, data, stats}。"""
    use_llm = (mode == "llm")
    max_rounds = 8 if use_llm else 20
    file_data: list[dict] = []
    file_queries: set[str] = set()

    for _round in range(max_rounds):
        await _check_cancel(should_cancel)
        shortfall = total_count - len(file_data)
        if shortfall <= 0:
            break

        shortfall_by_cat = _calc_category_counts(categories, shortfall)
        chunks = _split_into_chunks(shortfall_by_cat, _batch_size(provider))

        sem = _provider_sem(provider)

        async def _run_chunk(cat_name: str, count: int) -> int:
            """执行一个 chunk，完成后立即去重入列并更新进度，返回新增条数。"""
            async with sem:
                await _check_cancel(should_cancel)
                used = set(r["query"] for r in file_data)
                if use_llm:
                    recent = list(dict.fromkeys(
                        r["query"] for r in file_data))[-RECENT_QUERY_LIMIT:]
                    records = await llm_generate_batch(
                        cat_name, count, recent, provider=provider)
                    if not records:
                        records = [_pool_fallback(cat_name, used) for _ in range(count)]
                        records = [r for r in records if r is not None]
                else:
                    records = [pool_generate_single(cat_name, used) for _ in range(count)]
                    records = [r for r in records if r is not None]
                    # 让出事件循环：大批量同步生成时进度轮询请求能及时插队
                    await asyncio.sleep(0)
                added = 0
                for r in records:
                    fp = (r["query"], r["category"], r["motion_description"])
                    if fp not in file_queries:
                        file_data.append(r)
                        file_queries.add(fp)
                        added += 1
                        if progress is not None:
                            progress["completed"] += 1
                return added

        if not chunks:
            break

        results = await asyncio.gather(*[_run_chunk(cat, n) for cat, n in chunks])

        if sum(results) == 0:
            break

    # 最后一轮：放宽去重
    final_round = 0
    while len(file_data) < total_count and final_round < 5:
        await _check_cancel(should_cancel)
        final_round += 1
        sf = total_count - len(file_data)
        sf_by_cat = _calc_category_counts(categories, sf)
        extra_chunks = _split_into_chunks(sf_by_cat)
        sem3 = asyncio.Semaphore(CONCURRENCY)
        async def _run_relaxed_b(cat_name: str, cnt: int) -> int:
            async with sem3:
                await _check_cancel(should_cancel)
                added = 0
                for _ in range(cnt):
                    rec = pool_generate_single(cat_name, set())
                    if rec is None:
                        continue
                    file_data.append(rec)
                    added += 1
                    if progress is not None:
                        progress["completed"] += 1
                return added

        extra_results = await asyncio.gather(
            *[_run_relaxed_b(cat, n) for cat, n in extra_chunks]
        )
        if sum(extra_results) == 0:
            break

    # 取消后不再保存任何数据
    await _check_cancel(should_cancel)
    _enrich_records(file_data, actor_id)
    file_id = str(uuid.uuid4())

    if file_data:
        pool_records = [(d["query"], d["category"], mode) for d in file_data]
        await add_many_to_pool(pool_records)

    import json
    await save_history(
        record_id=file_id,
        gen_type="batch",
        count_per_file=total_count,
        file_count=file_count,
        total_records=len(file_data),
        categories_json=json.dumps(categories, ensure_ascii=False),
    )

    file_stats = {
        name: sum(1 for d in file_data if d["category"] == name)
        for name in _calc_category_counts(categories, total_count)
    }

    return {
        "record_id": file_id,
        "data": file_data,
        "stats": file_stats,
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

    async def _run_file() -> dict:
        async with file_sem:
            await _check_cancel(should_cancel)
            result = await _generate_one_file(
                categories, total_count, file_count, mode,
                actor_id, provider, should_cancel, progress)
            if progress is not None:
                progress["files_done"] += 1  # 文件正常完成才计数
            return result

    # gather 按传入顺序返回结果，files_data 顺序与文件序一致
    files_data = await asyncio.gather(*[_run_file() for _ in range(file_count)])

    return {
        "success": True,
        "mode": mode,
        "files": files_data,
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


def _pool_fallback(category: str, used: set[str]) -> dict | None:
    """要素池兜底生成。"""
    for _ in range(3):
        record = pool_generate_single(category, used)
        if record is not None:
            return record
    return None
