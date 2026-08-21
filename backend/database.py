from __future__ import annotations
import aiosqlite
import os
from datetime import datetime, timezone, timedelta

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "data.db")

# 北京时间偏移
TZ = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(TZ).isoformat()


async def get_db() -> aiosqlite.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA busy_timeout=10000")  # 并行文件写入时容忍写锁竞争
    return db


async def init_db():
    db = await get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS query_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'element_pool',
            created_at TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            count_per_file INTEGER NOT NULL,
            file_count INTEGER NOT NULL DEFAULT 1,
            total_records INTEGER NOT NULL,
            categories_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS keyword_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            field_type TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'global',
            source TEXT NOT NULL DEFAULT 'manual',
            reviewed INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)
    await db.commit()
    await db.close()


# --- query_pool 操作 ---

async def query_exists(query: str) -> bool:
    db = await get_db()
    cursor = await db.execute("SELECT 1 FROM query_pool WHERE query = ?", (query,))
    row = await cursor.fetchone()
    await db.close()
    return row is not None


async def add_to_pool(query: str, category: str, source: str):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO query_pool (query, category, source, created_at) VALUES (?, ?, ?, ?)",
            (query, category, source, _now()),
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        pass
    finally:
        await db.close()


async def add_many_to_pool(records: list[tuple[str, str, str]]):
    """批量写入去重池。每条为 (query, category, source)"""
    db = await get_db()
    count = 0
    for query, category, source in records:
        try:
            await db.execute(
                "INSERT INTO query_pool (query, category, source, created_at) VALUES (?, ?, ?, ?)",
                (query, category, source, _now()),
            )
            count += 1
        except aiosqlite.IntegrityError:
            pass
    await db.commit()
    await db.close()
    return count


async def get_pool_stats() -> dict:
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) as total FROM query_pool")
    total = (await cursor.fetchone())[0]
    cursor = await db.execute(
        "SELECT category, COUNT(*) as cnt FROM query_pool GROUP BY category"
    )
    by_category = {row["category"]: row["cnt"] for row in await cursor.fetchall()}
    cursor = await db.execute(
        "SELECT source, COUNT(*) as cnt FROM query_pool GROUP BY source"
    )
    by_source = {row["source"]: row["cnt"] for row in await cursor.fetchall()}
    await db.close()
    return {"total": total, "by_category": by_category, "by_source": by_source}


# --- history 操作 ---

async def save_history(
    record_id: str,
    gen_type: str,
    count_per_file: int,
    file_count: int,
    total_records: int,
    categories_json: str,
):
    db = await get_db()
    await db.execute(
        "INSERT INTO history (id, type, count_per_file, file_count, total_records, categories_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (record_id, gen_type, count_per_file, file_count, total_records, categories_json, _now()),
    )
    await db.commit()
    await db.close()


async def list_history() -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM history ORDER BY created_at DESC LIMIT 100"
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


async def get_history(record_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM history WHERE id = ?", (record_id,))
    row = await cursor.fetchone()
    await db.close()
    return dict(row) if row else None


async def delete_history(record_id: str):
    db = await get_db()
    await db.execute("DELETE FROM history WHERE id = ?", (record_id,))
    await db.commit()
    await db.close()


# --- keyword_pool 操作 ---

async def add_keyword(keyword: str, field_type: str, category: str, source: str, reviewed: bool = False):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO keyword_pool (keyword, field_type, category, source, reviewed, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (keyword, field_type, category, source, 1 if reviewed else 0, _now()),
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        pass
    finally:
        await db.close()


async def get_new_keywords(limit: int = 50) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM keyword_pool WHERE reviewed = 0 ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


async def review_keyword(keyword_id: int, approved: bool):
    db = await get_db()
    if approved:
        await db.execute("UPDATE keyword_pool SET reviewed = 1 WHERE id = ?", (keyword_id,))
    else:
        await db.execute("DELETE FROM keyword_pool WHERE id = ?", (keyword_id,))
    await db.commit()
    await db.close()
