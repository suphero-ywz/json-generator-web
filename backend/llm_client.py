"""
LLM 客户端（多后端：DeepSeek 云端 / Ollama 本地）

负责：
- 检测各后端是否已配置 / 在线
- 解析 provider（auto / deepseek / ollama）
- 调用 OpenAI 兼容 API 生成动作数据
- 构造 Prompt（含动态约束注入）
- 解析 LLM 返回的 JSON

API 文档：
- DeepSeek: https://api-docs.deepseek.com
- Ollama: https://docs.ollama.com
"""

from __future__ import annotations
import os
import json
import re
import asyncio
import time
import httpx
from element_pool import (
    get_category_config,
    get_body_parts_for_category,
    get_emotions_for_category,
    get_actions_for_category,
)

TIMEOUT = 600  # 单次生成超时秒数（本地 CPU 推理较慢，云端不受影响）
PROBE_TTL = 30.0  # 在线探测结果缓存秒数
PROVIDER_ORDER = ["ollama", "deepseek"]  # auto 模式优先级（本地 Ollama 优先，DeepSeek 备选）


def env_int(name: str, default: int) -> int:
    """读取环境变量整数，未设置或非法时回退默认值。"""
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


# 性能调优旋钮（可在 .env 中覆盖，main.py 先于本模块加载 .env）
RECENT_QUERY_LIMIT = env_int("LLM_RECENT_QUERY_LIMIT", 12)     # 传给 LLM 的已生成 query 上限
DEEPSEEK_MAX_TOKENS = env_int("DS_MAX_TOKENS", 2500)           # DeepSeek 单次调用最大输出
OLLAMA_MAX_TOKENS = env_int("OLLAMA_MAX_TOKENS", 2000)         # Ollama 单次调用最大输出


def _build_providers() -> dict:
    """从环境变量构建后端配置表。"""
    ds_base = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    ds_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    ds_key = os.getenv("DEEPSEEK_API_KEY", "")

    ollama_base = os.getenv("OLLAMA_API_BASE", "")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen3:8b")

    # 旧式 .env 兼容：Ollama 未配置但 DEEPSEEK_API_BASE 指向本地时，
    # 将其继承为 Ollama 的地址，并把 DeepSeek 重置回云端默认（使两后端可并存）
    if not ollama_base and ("localhost" in ds_base or "127.0.0.1" in ds_base):
        ollama_base = ds_base
        ollama_model = ds_model
        ds_base = "https://api.deepseek.com/v1"

    return {
        "deepseek": {
            "label": "DeepSeek",
            "base": ds_base,
            "model": ds_model,
            "key": ds_key,
            "needs_key": True,
            "enabled": bool(ds_key),
        },
        "ollama": {
            "label": "Ollama",
            "base": ollama_base,
            "model": ollama_model,
            "key": "",
            "needs_key": False,
            "enabled": bool(ollama_base),
        },
    }


PROVIDERS = _build_providers()

# 兼容导出（deepseek 的旧模块级常量，防外部脚本引用）
API_BASE = PROVIDERS["deepseek"]["base"]
MODEL_NAME = PROVIDERS["deepseek"]["model"]


def provider_config_available(pid: str) -> bool:
    """配置层可用性：DeepSeek 需 Key；Ollama 需显式配置 base。"""
    cfg = PROVIDERS.get(pid)
    return bool(cfg and cfg["enabled"])


def check_api() -> bool:
    """检测是否有任一后端已配置（main.py 启动横幅使用）。"""
    return any(provider_config_available(p) for p in PROVIDER_ORDER)


_probe_cache: dict[str, tuple[float, bool]] = {}  # pid -> (探测时间, 结果)


def _cached_online(pid: str) -> bool | None:
    """读取在线探测缓存（同步）。过期或无记录返回 None。"""
    hit = _probe_cache.get(pid)
    if hit is None:
        return None
    ts, result = hit
    if time.monotonic() - ts > PROBE_TTL:
        return None
    return result


async def check_provider_online(pid: str) -> bool:
    """在线探测后端是否真正可用（带 TTL 缓存，失败也缓存）。"""
    if pid not in PROVIDERS:
        return False
    cached = _cached_online(pid)
    if cached is not None:
        return cached
    cfg = PROVIDERS[pid]
    headers = {"Authorization": f"Bearer {cfg['key']}"} if cfg["needs_key"] else {}
    ok = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{cfg['base']}/models", headers=headers)
        ok = r.status_code == 200
    except Exception:
        ok = False
    _probe_cache[pid] = (time.monotonic(), ok)
    return ok


def resolve_provider(requested: str) -> str:
    """解析 provider：显式合法且已配置 -> 用之；auto/未知 -> 按优先级选择。"""
    configured = [p for p in PROVIDER_ORDER if provider_config_available(p)]
    if requested in PROVIDER_ORDER and provider_config_available(requested):
        return requested
    if requested not in ("auto", *PROVIDER_ORDER):
        print(f"[LLM] 未知 provider: {requested}，回退 auto")
    if not configured:
        # 都未配置：返回最后一项，生成时会失败并降级要素池
        return PROVIDER_ORDER[-1]
    # auto / 显式但不可用：按优先级选探测结果不是失败的
    for p in configured:
        if _cached_online(p) is not False:
            return p
    return configured[0]


def _build_system_prompt() -> str:
    """构造系统角色设定"""
    return "你是一个数字人动作设计师，专门为光学动作捕捉数据采集服务。你生成的每一条动作都必须独特、有创意、不模板化。你严格遵循格式要求，只输出合法的 JSON。/no_think"


def _format_recent_queries(recent_queries: list[str]) -> str:
    """把已生成 query 格式化为 prompt 中的严禁重复列表（逐行格式避免顿号歧义）。"""
    if not recent_queries:
        return "暂无"
    return "\n".join(f"- 「{q}」" for q in recent_queries[:RECENT_QUERY_LIMIT])


def _build_user_prompt(category: str, recent_queries: list[str]) -> str:
    """为指定类别构造用户 prompt（含参考示例）"""
    cfg = get_category_config(category)
    if not cfg:
        cfg = get_category_config("其他")

    body_parts = get_body_parts_for_category(category)
    body_parts_str = "、".join(body_parts)
    emotions = get_emotions_for_category(category)
    emotions_str = "、".join(f"[{e}]" for e in emotions)
    actions = get_actions_for_category(category)
    actions_str = "、".join(actions[:20])

    recent_str = _format_recent_queries(recent_queries)

    return f"""请创造一个全新的、独特的「{category}」类别动作。

【参考示例】
  query: "来，立正" | text: "一个人双脚并拢，全身挺直，标准站姿保持稳定，最后回到站立姿态" | motion_description: "[[情绪:严肃]，[动作:立正]，[次数:1次]，[幅度:标准]，[速度:标准]]" | query_description: "[[立正]，[情绪:严肃]]" | voice_feedback: "立正完毕，随时待命！" | aug_text: ["最简版","最详版"]

【要素要求】
- 身体部位从以下选取：{body_parts_str}
- 动作方式参考：{actions_str}
- 动作必须是人类可以完成的，物理上真实可行

【已生成动作（严禁重复）】
{recent_str}

【输出规范】
- query: 口语化指令，5-15 字，自然结尾（吧/呗/一下/看看）
- text: 以「一个人」开头，描述身体部位、幅度、速度、动作，以「最后回到站立姿态」结尾
- motion_description: 标签格式，「，」分隔，必含 [情绪:xxx][动作:xxx][次数:x次/步数:x步][幅度:xxx][速度:xxx]，可选 [手部:xxx][脚部:xxx][方向:xxx]
- query_description: 标签格式，以 [[动作名] 开头，可含 [情绪:xxx][次数:x次][手部:xxx][幅度:xxx][速度:xxx]（部分标签可省略）
- voice_feedback: 自然口语化回应，13-22 字（如「好嘞，...哈！」「嘿嘿，...哟~」）
- aug_text: 2 个文本变体数组：[0] 为最简版（10 字以内，只含核心动作），[1] 为最详版（60 字以上，含身体部位、幅度、速度、次数细节）

【约束】
- 情绪从以下选：{emotions_str}
- 幅度：大幅 / 小幅 / 标准  |  速度：快速 / 慢速 / 标准
- 动作重复 ≤3 次，行走/跑步 ≤5 步，爬行 ≤6 步
- [爆发] 必须配快速，[优雅] 配慢速或标准，[疲惫][困倦] 不能配快速
- 禁止悬浮、飞行、危险、自残动作
- is_head: 仅头部动作（歪头/点头/摇头/仰头/低头/转头）且不涉及其他部位 → true

输出严格按以下 JSON 格式，不要输出任何其他内容：
{{
  "query": "口语指令",
  "query_description": "[[动作名]，[情绪:xxx]，...]",
  "text": "一个人...，最后回到站立姿态",
  "motion_description": "[[情绪:xxx]，[动作:xxx]，[次数:x次]，[手部:xxx]，[幅度:xxx]，[速度:xxx]]",
  "voice_feedback": "口语反馈",
  "aug_text": ["最简版","最详版"]
}}"""


def _fix_json(json_str: str) -> str:
    """尝试修复常见的 JSON 格式问题"""
    json_str = json_str.strip()
    json_str = re.sub(r"^```(?:json)?\s*", "", json_str)
    json_str = re.sub(r"\s*```$", "", json_str)
    return json_str


def _ollama_native_payload(base: str, payload: dict) -> tuple[str, dict]:
    """把 OpenAI 兼容层请求转为 Ollama 原生 /api/chat 请求。

    必须走原生端点：兼容层无法关闭 Qwen3 的思维链（thinking），
    thinking 曾占生成 token 的 98% 且其内容被兼容层丢弃，严重拖慢并侵占输出配额。
    """
    b = base.rstrip("/")
    if b.endswith("/v1"):
        b = b[:-3]
    body = dict(payload)
    body["think"] = False
    options = {
        "num_predict": body.pop("max_tokens", None),
        "temperature": body.pop("temperature", None),
        "top_p": body.pop("top_p", None),
    }
    body["options"] = {k: v for k, v in options.items() if v is not None}
    return f"{b}/api/chat", body


async def _call_llm_with_retry(payload: dict, provider: str = "auto",
                               max_retries: int = 2) -> dict | None:
    """带指数退避重试的 LLM API 调用（返回 OpenAI 兼容格式）。"""
    pid = resolve_provider(provider)
    cfg = PROVIDERS[pid]
    if cfg["needs_key"] and not cfg["key"]:
        print(f"[LLM] {cfg['label']} 未配置 API Key")
        return None
    # 当前 provider 网络不可达时可切换的备选（保持 PROVIDER_ORDER 优先级语义）
    fallback_pids = [p for p in PROVIDER_ORDER
                     if p != pid and provider_config_available(p)]
    last_error = None
    for attempt in range(max_retries + 1):
        # headers/url 依赖 pid，须在循环内构建（网络错误可能切换 provider）
        headers = {"Content-Type": "application/json"}
        if cfg["needs_key"]:
            headers["Authorization"] = f"Bearer {cfg['key']}"
        try:
            if pid == "ollama":
                url, body = _ollama_native_payload(cfg["base"], payload)
            else:
                url, body = f"{cfg['base']}/chat/completions", payload
            async with httpx.AsyncClient(timeout=(10, TIMEOUT, TIMEOUT, TIMEOUT)) as client:
                r = await client.post(url, json=body, headers=headers)
            if r.status_code == 200:
                if pid == "ollama":
                    # 原生响应 {message: {content}} 包装为 OpenAI 兼容格式
                    data = r.json()
                    content = data.get("message", {}).get("content", "")
                    print(f"[LLM] {pid} tokens: 输出 {data.get('eval_count', '?')} "
                          f"(输入 {data.get('prompt_eval_count', '?')})")
                    return {"choices": [{"message": {"content": content}}]}
                data = r.json()
                usage = data.get("usage", {})
                if usage:
                    print(f"[LLM] {pid} tokens: 输入 {usage.get('prompt_tokens', '?')} "
                          f"+ 输出 {usage.get('completion_tokens', '?')} "
                          f"= {usage.get('total_tokens', '?')}")
                return data
            if r.status_code == 429:
                print(f"[LLM] 请求限流，重试中...（第 {attempt + 1} 次）")
                await asyncio.sleep(2 * (attempt + 1))
                continue
            if 500 <= r.status_code < 600:
                last_error = f"HTTP {r.status_code}"
                print(f"[LLM] 服务器错误 {r.status_code}，重试中...（第 {attempt + 1} 次）")
                await asyncio.sleep(1 * (attempt + 1))
                continue
            # 4xx error - no retry
            print(f"[LLM] API 错误: HTTP {r.status_code} - {r.text[:200]}")
            return None
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError):
            last_error = "network"
            # 服务不可达：优先切换到备选 provider（如 Ollama 离线时切 DeepSeek）
            if fallback_pids:
                pid = fallback_pids.pop(0)
                cfg = PROVIDERS[pid]
                # model 须随 provider 切换（如 Qwen3-8B 不能发给 DeepSeek）
                payload = {**payload, "model": cfg["model"]}
                print(f"[LLM] 网络错误，切换至 {cfg['label']}...（第 {attempt + 1} 次）")
                continue
            print(f"[LLM] 网络错误，重试中...（第 {attempt + 1} 次）")
            await asyncio.sleep(1 * (attempt + 1))
            continue
        except Exception as e:
            print(f"[LLM] 未知错误: {e}")
            return None
    print(f"[LLM] 全部重试失败: {last_error}")
    return None


async def generate_single(category: str, recent_queries: list[str],
                          model: str | None = None,
                          provider: str = "auto") -> dict | None:
    """
    调用 LLM API 生成单条动作数据。

    Args:
        provider: auto / deepseek / ollama
    Returns:
        解析后的动作数据 dict，失败返回 None
    """
    pid = resolve_provider(provider)
    cfg = PROVIDERS[pid]
    if cfg["needs_key"] and not cfg["key"]:
        return None

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(category, recent_queries)

    payload = {
        "model": model or cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 1024,
        "stream": False,
    }

    try:
        result = await _call_llm_with_retry(payload, provider=pid)
        if result is None:
            return None
        content = result["choices"][0]["message"]["content"]
        response_text = _fix_json(content)
        data = json.loads(response_text)
        data["category"] = category
        data["is_head"] = _judge_is_head(
            data.get("query", ""), data.get("text", ""), category)
        data["aug_text"] = _derive_aug_text(
            data.get("text", ""), data.get("aug_text"),
            data.get("motion_description", ""))
        return data
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


async def generate_batch(category: str, count: int,
                         recent_queries: list[str],
                         model: str | None = None,
                         provider: str = "auto") -> list[dict]:
    """
    一次 API 调用生成多条动作数据（3-5 条），减少网络往返。

    Args:
        provider: auto / deepseek / ollama
    Returns:
        解析后的动作数据列表，失败返回空列表
    """
    pid = resolve_provider(provider)
    pcfg = PROVIDERS[pid]
    if pcfg["needs_key"] and not pcfg["key"]:
        return []

    system_prompt = _build_system_prompt()

    cat_cfg = get_category_config(category)
    if not cat_cfg:
        cat_cfg = get_category_config("其他")

    body_parts = get_body_parts_for_category(category)
    body_parts_str = "、".join(body_parts)
    emotions = get_emotions_for_category(category)
    emotions_str = "、".join(f"[{e}]" for e in emotions)
    actions = get_actions_for_category(category)
    actions_str = "、".join(actions[:20])
    recent_str = _format_recent_queries(recent_queries)

    user_prompt = f"""请创造 {count} 个全新的、互不重复的「{category}」类别动作。

【参考示例】
  query: "来，立正" | text: "一个人双脚并拢，全身挺直，标准站姿保持稳定，最后回到站立姿态" | motion_description: "[[情绪:严肃]，[动作:立正]，[次数:1次]，[幅度:标准]，[速度:标准]]" | query_description: "[[立正]，[情绪:严肃]]" | voice_feedback: "立正完毕，随时待命！" | aug_text: ["最简版","最详版"]

【要素要求】
- 身体部位：{body_parts_str}
- 动作参考（创造不同动作）：{actions_str}

【已生成动作（严禁重复）】
{recent_str}

【输出规范】
- query: 口语化，5-15字，自然结尾
- text: 以「一个人」开头，以「最后回到站立姿态」结尾
- motion_description: 标签格式，必含 [情绪:xxx][动作:xxx][次数:x次/步数:x步][幅度:xxx][速度:xxx]，可选 [手部:xxx][脚部:xxx]
- query_description: 标签格式，以 [[动作名] 开头，可含 [情绪:xxx][次数:x次][手部:xxx] 等，部分可省略
- voice_feedback: 口语化，13-22字
- aug_text: 2 个文本变体数组：[0] 为最简版（10 字以内，只含核心动作），[1] 为最详版（60 字以上，含身体部位、幅度、速度、次数细节）

【约束】
- 情绪：{emotions_str} | 幅度：大幅/小幅/标准 | 速度：快速/慢速/标准
- 次数≤3，步数≤5(行走/跑步)或≤6(爬行)
- [爆发]→快速，[优雅]→慢速/标准，[疲惫][困倦]→不配快速
- 禁止悬浮/飞行/危险动作

输出 JSON 数组（{count} 个对象）：
[
  {{
    "query": "口语指令",
    "query_description": "[[动作名]，[情绪:xxx]，...]",
    "text": "一个人...，最后回到站立姿态",
    "motion_description": "[[情绪:xxx]，[动作:xxx]，[次数:x次]，[手部:xxx]，[幅度:xxx]，[速度:xxx]]",
    "voice_feedback": "口语反馈",
    "aug_text": ["最简版","最详版"]
  }}
]"""

    payload = {
        "model": model or pcfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": OLLAMA_MAX_TOKENS if pid == "ollama" else DEEPSEEK_MAX_TOKENS,
        "stream": False,
    }

    try:
        print(f"[LLM] 正在为「{category}」生成 {count} 条记录（{pid}）...")
        result = await _call_llm_with_retry(payload, provider=pid)
        if result is None:
            print(f"[LLM] 失败，降级为要素池模式（{category}）")
            return []
        content = result["choices"][0]["message"]["content"]
        response_text = _fix_json(content)
        items = json.loads(response_text)
        if isinstance(items, dict):
            items = [items]
        for item in items:
            item["category"] = category
            item["is_head"] = _judge_is_head(
                item.get("query", ""), item.get("text", ""), category)
            item["aug_text"] = _derive_aug_text(
                item.get("text", ""), item.get("aug_text"),
                item.get("motion_description", ""))
        print(f"[LLM] 已为「{category}」生成 {len(items)} 条记录")
        return items
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"[LLM] JSON 解析失败: {e}")
        return []


_MD_TAG_RE = re.compile(r"\[([^\[\]]+):([^\[\]]+)\]")


def _parse_md_tags(md: str) -> dict[str, str]:
    """解析 motion_description 标签（与 validator._parse_tags 同规则）。"""
    return dict(_MD_TAG_RE.findall(md or ""))


def _derive_aug_text(text: str, aug_text: object, motion_description: str) -> list[str]:
    """把 LLM 返回的 aug_text 补齐为 6 个变体（从简到详）。

    兼容规则：
    - 返回 6 个及以上：原样截取前 6（旧模型/旧缓存零回归）
    - 返回 2 个：[0]=最简版，[1]=最详版，中间 4 个模板派生
    - 返回 1 个：视为同时充当首尾，中间 4 个派生
    - 返回 0 个/缺失/非 list：最简版=short_text，最详版=text
    """
    if isinstance(aug_text, list) and len(aug_text) >= 6:
        return aug_text[:6]
    if isinstance(aug_text, list) and aug_text:
        v_min, v_det = str(aug_text[0]), str(aug_text[-1])
    else:
        v_min, v_det = "", ""

    short_text = text.replace("，最后回到站立姿态", "").replace("最后回到站立姿态", "")
    if not short_text:
        # text 缺失/异常：无正文可派生，全部回退同一兜底值
        base = v_min or v_det or text or ""
        return [base] * 6
    if not v_min:
        v_min = short_text
    if not v_det:
        v_det = text

    emotion = _parse_md_tags(motion_description).get("情绪", "")
    if emotion:
        # short_text 以「一个人」开头时去掉前缀，避免「一个人面带xx，一个人...」主语重复
        body = short_text[3:] if short_text.startswith("一个人") else short_text
        mid1 = f"一个人面带{emotion}，{body}，然后缓缓回到站立姿态"
        mid2 = f"一个人情绪{emotion}，{body}，随后恢复直立站姿"
    else:
        mid1 = f"{short_text}，动作自然流畅"
        mid2 = f"{short_text}，随后恢复直立站姿"

    return [v_min, short_text, text, mid1, mid2, v_det]


def _judge_is_head(query: str, text: str, category: str) -> bool:
    """判断是否为仅头部动作"""
    head_keywords = ["歪头", "仰头", "低头", "转头", "点头", "摇头"]
    body_keywords = [
        "手", "脚", "腿", "臂", "肩", "腰", "背", "膝", "身",
        "指", "拳", "掌", "腕", "肘",
    ]
    has_head = any(kw in text for kw in head_keywords)
    has_body = any(kw in text for kw in body_keywords)
    return has_head and not has_body
