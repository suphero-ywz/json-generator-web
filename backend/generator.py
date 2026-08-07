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
from element_generator import generate_single as pool_generate_single
from llm_client import generate_single as llm_generate_single
from llm_client import generate_batch as llm_generate_batch
from validator import validate_full
from database import add_many_to_pool, save_history


CONCURRENCY = 12          # 并发 API 请求数
BATCH_SIZE = 5            # 每次 API 调用生成的记录数


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


def _split_into_chunks(category_counts: dict[str, int]) -> list[tuple[str, int]]:
    """将每个类别的记录数拆分为 BATCH_SIZE 大小的块。"""
    chunks = []
    for cat_name, total in category_counts.items():
        remaining = total
        while remaining > 0:
            size = min(BATCH_SIZE, remaining)
            chunks.append((cat_name, size))
            remaining -= size
    return chunks


async def generate(
    categories: list[dict],
    total_count: int,
    mode: str,
    actor_id: str = "Skeleton0",
) -> dict:
    """单次生成，带重试补全确保达到目标条数。"""
    use_llm = (mode == "llm")
    category_counts = _calc_category_counts(categories, total_count)
    all_data: list[dict] = []
    all_queries: set[str] = set()
    max_rounds = 8 if use_llm else 20

    for _round in range(max_rounds):
        shortfall = total_count - len(all_data)
        if shortfall <= 0:
            break

        # 按比例分配剩余量
        shortfall_by_cat = _calc_category_counts(categories, shortfall)
        chunks = _split_into_chunks(shortfall_by_cat)

        sem = asyncio.Semaphore(CONCURRENCY)

        async def _run_chunk(cat_name: str, count: int) -> list[dict]:
            async with sem:
                used = set(r["query"] for r in all_data)
                if use_llm:
                    records = await llm_generate_batch(cat_name, count, [])
                    if not records:
                        records = [_pool_fallback(cat_name, used) for _ in range(count)]
                        records = [r for r in records if r is not None]
                    return records
                else:
                    records = [pool_generate_single(cat_name, used) for _ in range(count)]
                    return [r for r in records if r is not None]

        if not chunks:
            break

        results = await asyncio.gather(*[_run_chunk(cat, n) for cat, n in chunks])

        new_count = 0
        for records in results:
            for r in records:
                fp = (r["query"], r["category"], r["motion_description"])
                if fp not in all_queries:
                    all_data.append(r)
                    all_queries.add(fp)
                    new_count += 1

        if new_count == 0:
            break

    # 最后一轮：放宽去重，允许同 query 不同 motion_description 的记录
    final_round = 0
    while len(all_data) < total_count and final_round < 5:
        final_round += 1
        sf = total_count - len(all_data)
        sf_by_cat = _calc_category_counts(categories, sf)
        extra_chunks = _split_into_chunks(sf_by_cat)
        sem2 = asyncio.Semaphore(CONCURRENCY)
        async def _run_relaxed(cat_name: str, cnt: int) -> list[dict]:
            async with sem2:
                records = [pool_generate_single(cat_name, set()) for _ in range(cnt)]
                return [r for r in records if r is not None]

        extra_results = await asyncio.gather(
            *[_run_relaxed(cat, n) for cat, n in extra_chunks]
        )
        added = 0
        for records in extra_results:
            for r in records:
                all_data.append(r)
                added += 1
        if added == 0:
            break

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


async def generate_batch(
    categories: list[dict],
    total_count: int,
    file_count: int,
    mode: str,
    actor_id: str = "Skeleton0",
) -> dict:
    """批量生成（每个文件内带重试补全）。"""
    use_llm = (mode == "llm")
    files_data = []
    max_rounds = 8 if use_llm else 20

    for _i in range(file_count):
        file_data: list[dict] = []
        file_queries: set[str] = set()

        for _round in range(max_rounds):
            shortfall = total_count - len(file_data)
            if shortfall <= 0:
                break

            shortfall_by_cat = _calc_category_counts(categories, shortfall)
            chunks = _split_into_chunks(shortfall_by_cat)

            sem = asyncio.Semaphore(CONCURRENCY)

            async def _run_chunk(cat_name: str, count: int) -> list[dict]:
                async with sem:
                    used = set(r["query"] for r in file_data)
                    if use_llm:
                        records = await llm_generate_batch(cat_name, count, [])
                        if not records:
                            records = [_pool_fallback(cat_name, used) for _ in range(count)]
                            records = [r for r in records if r is not None]
                        return records
                    else:
                        records = [pool_generate_single(cat_name, used) for _ in range(count)]
                        return [r for r in records if r is not None]

            if not chunks:
                break

            results = await asyncio.gather(*[_run_chunk(cat, n) for cat, n in chunks])

            new_count = 0
            for records in results:
                for r in records:
                    fp = (r["query"], r["category"], r["motion_description"])
                    if fp not in file_queries:
                        file_data.append(r)
                        file_queries.add(fp)
                        new_count += 1

            if new_count == 0:
                break

        # 最后一轮：放宽去重
        final_round = 0
        while len(file_data) < total_count and final_round < 5:
            final_round += 1
            sf = total_count - len(file_data)
            sf_by_cat = _calc_category_counts(categories, sf)
            extra_chunks = _split_into_chunks(sf_by_cat)
            sem3 = asyncio.Semaphore(CONCURRENCY)
            async def _run_relaxed_b(cat_name: str, cnt: int) -> list[dict]:
                async with sem3:
                    records = [pool_generate_single(cat_name, set()) for _ in range(cnt)]
                    return [r for r in records if r is not None]

            extra_results = await asyncio.gather(
                *[_run_relaxed_b(cat, n) for cat, n in extra_chunks]
            )
            added = 0
            for records in extra_results:
                for r in records:
                    file_data.append(r)
                    added += 1
            if added == 0:
                break

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

        files_data.append({
            "record_id": file_id,
            "data": file_data,
            "stats": file_stats,
        })

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
