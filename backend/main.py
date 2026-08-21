"""
FastAPI 入口 + 路由

提供以下 API：
- POST /api/generate         单次生成
- POST /api/generate/batch   批量生成
- POST /api/generate/cancel  取消进行中的生成
- GET  /api/status           检查 LLM 可用性
- GET  /api/history          历史记录列表
- DELETE /api/history/{id}    删除历史
- POST /api/history/{id}/regenerate  重新生成
- POST /api/import           导入 JSON
- GET  /api/query-pool/stats 去重池统计
"""

import json
import os
import sys
import uuid
import asyncio
from typing import Dict, Optional
from dotenv import load_dotenv

# 确保 .env 从正确的目录加载
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_PATH)
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from models import (
    GenerateRequest, BatchGenerateRequest, CancelRequest,
    GenerateResponse, BatchGenerateResponse,
    StatusResponse, ProviderInfo, ImportResult, QueryPoolStats,
)
from database import (
    init_db, list_history, delete_history, get_history,
    save_history, add_many_to_pool, get_pool_stats,
)
from generator import generate, generate_batch
from llm_client import (
    PROVIDERS, PROVIDER_ORDER, check_api, resolve_provider,
    check_provider_online, provider_config_available,
)


# 全局状态：LLM 是否可用（config 层初值，/api/status 会随探测结果更新）
_llm_available: bool = check_api()
_llm_model: str = PROVIDERS[resolve_provider("auto")]["model"]

# 进行中的生成任务（task_id -> Task），用于取消生成
_active_tasks: Dict[str, asyncio.Task] = {}


def _register_task(task_id: Optional[str]) -> Optional[str]:
    """注册当前协程任务，返回实际使用的 task_id（未提供时不注册）。"""
    if not task_id:
        return None
    _active_tasks[task_id] = asyncio.current_task()
    return task_id


def _unregister_task(task_id: Optional[str]) -> None:
    """任务结束后从注册表移除。"""
    if task_id:
        _active_tasks.pop(task_id, None)


def _resolve_mode(request_mode: str) -> str:
    """解析模式：auto 时根据 LLM 可用性自动判断，否则用用户选择。"""
    if request_mode == "llm":
        return "llm"
    if request_mode == "element_pool":
        return "element_pool"
    return "llm" if _llm_available else "element_pool"


def _resolve_provider(request_provider: str) -> str:
    """解析 provider 参数（未知/不可用回退 auto 逻辑）。"""
    return resolve_provider(request_provider or "auto")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _llm_available
    await init_db()
    _llm_available = check_api()
    if not _llm_available:
        print("[启动] 数据库已初始化 | 模式: element_pool（要素池）")
        print("[提示] 设置 DEEPSEEK_API_KEY 或 OLLAMA_API_BASE 环境变量即可启用 LLM 模式")
    else:
        for pid in PROVIDER_ORDER:
            cfg = PROVIDERS[pid]
            status = "已配置" if provider_config_available(pid) else "未配置"
            print(f"[启动] {cfg['label']}: {status}（{cfg['model']}）")
        default_pid = resolve_provider("auto")
        print(f"[启动] 数据库已初始化 | 默认后端: {PROVIDERS[default_pid]['label']}（{_llm_model}）")
    yield


app = FastAPI(
    title="动作数据集 JSON 生成器",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API 端点 ---

@app.get("/api/status", response_model=StatusResponse)
async def api_status():
    """检查当前生成模式与各 LLM 后端状态"""
    global _llm_available, _llm_model
    online = {}
    if PROVIDERS:
        results = await asyncio.gather(
            *[check_provider_online(p) for p in PROVIDERS],
            return_exceptions=True,
        )
        for pid, r in zip(PROVIDERS.keys(), results):
            online[pid] = bool(r) if not isinstance(r, Exception) else False
    providers = [
        ProviderInfo(
            id=pid,
            label=cfg["label"],
            model=cfg["model"],
            available=provider_config_available(pid),
            online=online.get(pid, False),
        )
        for pid, cfg in PROVIDERS.items()
    ]
    # 未探测过的按 config 兜底，避免启动瞬间误判 element_pool
    _llm_available = any(
        online.get(p, provider_config_available(p)) for p in PROVIDERS
    )
    _llm_model = PROVIDERS[resolve_provider("auto")]["model"]
    return StatusResponse(
        llm_available=_llm_available,
        mode="llm" if _llm_available else "element_pool",
        model=_llm_model,
        providers=providers,
    )


@app.post("/api/generate", response_model=GenerateResponse)
async def api_generate(req: GenerateRequest, request: Request):
    """单次生成"""
    task_id = _register_task(req.task_id)
    try:
        categories = [c.model_dump() for c in req.categories]
        mode = _resolve_mode(req.mode)
        provider = _resolve_provider(req.provider)
        result = await generate(
            categories, req.total_count, mode, req.actor_id,
            provider=provider,
            should_cancel=request.is_disconnected,
        )
        return GenerateResponse(**result)
    except asyncio.CancelledError:
        print("[取消] 单次生成任务已停止")
        return GenerateResponse(success=False, mode="error", error="生成已取消")
    except Exception as e:
        return GenerateResponse(success=False, mode="error", error=str(e))
    finally:
        _unregister_task(task_id)


@app.post("/api/generate/batch", response_model=BatchGenerateResponse)
async def api_generate_batch(req: BatchGenerateRequest, request: Request):
    """批量生成"""
    task_id = _register_task(req.task_id)
    try:
        categories = [c.model_dump() for c in req.categories]
        mode = _resolve_mode(req.mode)
        provider = _resolve_provider(req.provider)
        result = await generate_batch(
            categories, req.total_count, req.file_count, mode, req.actor_id,
            provider=provider,
            should_cancel=request.is_disconnected,
        )
        return BatchGenerateResponse(**result)
    except asyncio.CancelledError:
        print("[取消] 批量生成任务已停止")
        return BatchGenerateResponse(success=False, mode="error", error="生成已取消")
    except Exception as e:
        return BatchGenerateResponse(success=False, mode="error", error=str(e))
    finally:
        _unregister_task(task_id)


@app.post("/api/generate/cancel")
async def api_cancel_generate(req: CancelRequest):
    """取消进行中的生成任务（task_id 为空时取消全部）"""
    if req.task_id:
        task = _active_tasks.get(req.task_id)
        if task is None:
            return {"success": False, "error": "没有进行中的生成任务"}
        task.cancel()
        return {"success": True}
    if not _active_tasks:
        return {"success": False, "error": "没有进行中的生成任务"}
    for task in _active_tasks.values():
        task.cancel()
    return {"success": True}


@app.get("/api/history")
async def api_history():
    """获取历史记录（仅元数据）"""
    records = await list_history()
    return {"success": True, "data": records}


@app.delete("/api/history/{record_id}")
async def api_delete_history(record_id: str):
    """删除历史记录"""
    record = await get_history(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    await delete_history(record_id)
    return {"success": True}


@app.post("/api/history/{record_id}/regenerate")
async def api_regenerate(
    record_id: str, request: Request,
    mode: str = "auto", provider: str = "auto",
    task_id: Optional[str] = None,
):
    """用相同参数重新生成"""
    record = await get_history(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    categories = json.loads(record["categories_json"])
    count = record["count_per_file"]
    resolved_mode = _resolve_mode(mode)
    resolved_provider = _resolve_provider(provider)

    task_id = _register_task(task_id)
    try:
        if record["type"] == "single":
            result = await generate(
                categories, count, resolved_mode,
                provider=resolved_provider,
                should_cancel=request.is_disconnected,
            )
            return GenerateResponse(**result)
        else:
            result = await generate_batch(
                categories, count, record["file_count"], resolved_mode,
                provider=resolved_provider,
                should_cancel=request.is_disconnected,
            )
            return BatchGenerateResponse(**result)
    except asyncio.CancelledError:
        print("[取消] 重新生成任务已停止")
        return GenerateResponse(success=False, mode="error", error="生成已取消")
    finally:
        _unregister_task(task_id)


@app.post("/api/import", response_model=ImportResult)
async def api_import(file: UploadFile = File(...)):
    """导入 JSON 文件，query 写入去重池"""
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))

        # 支持数组或单个对象
        if isinstance(data, dict):
            data = [data]

        records = []
        skipped = 0
        for item in data:
            query = item.get("query", "")
            category = item.get("category", "其他")
            if query:
                records.append((query, category, "imported"))
            else:
                skipped += 1

        imported = await add_many_to_pool(records)

        return ImportResult(
            success=True,
            imported_count=imported,
            skipped_count=skipped + (len(data) - imported - skipped),
            total_count=len(data),
        )
    except json.JSONDecodeError:
        return ImportResult(
            success=False,
            imported_count=0,
            skipped_count=0,
            total_count=0,
            error="JSON 解析失败，请检查文件格式",
        )
    except Exception as e:
        return ImportResult(
            success=False,
            imported_count=0,
            skipped_count=0,
            total_count=0,
            error=str(e),
        )


@app.get("/api/query-pool/stats", response_model=QueryPoolStats)
async def api_pool_stats():
    """去重池统计"""
    stats = await get_pool_stats()
    return QueryPoolStats(**stats)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
