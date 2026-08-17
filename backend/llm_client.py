"""
DeepSeek LLM 客户端

负责：
- 检测 API Key 是否已配置
- 调用 DeepSeek API 生成动作数据
- 构造 Prompt（含动态约束注入）
- 解析 LLM 返回的 JSON

API 文档：https://api-docs.deepseek.com
"""

from __future__ import annotations
import os
import json
import re
import asyncio
import httpx
from element_pool import (
    get_category_config,
    get_body_parts_for_category,
    get_emotions_for_category,
    get_actions_for_category,
)

API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")  # DeepSeek-V3，中文能力强
TIMEOUT = 60  # 单次生成超时秒数


def _get_api_key() -> str:
    """获取 API Key（从环境变量）"""
    return os.getenv("DEEPSEEK_API_KEY", "")


def _is_local() -> bool:
    """是否使用本地推理服务（Ollama 等，无需 API Key）"""
    return "localhost" in API_BASE or "127.0.0.1" in API_BASE


def check_api() -> bool:
    """检测 LLM 是否可用（本地服务无需 Key，云端需配置 Key）"""
    return _is_local() or bool(_get_api_key())


async def check_api_online() -> tuple[bool, str]:
    """在线检测 API 是否真正可用"""
    api_key = _get_api_key()
    if not api_key:
        return False, "未配置 DEEPSEEK_API_KEY 环境变量"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{API_BASE}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if r.status_code == 200:
                return True, MODEL_NAME
            return False, f"API 认证失败（{r.status_code}），请检查 Key 是否正确"
    except Exception as e:
        return False, f"API 连接失败: {e}"


def _build_system_prompt() -> str:
    """构造系统角色设定"""
    return "你是一个数字人动作设计师，专门为光学动作捕捉数据采集服务。你生成的每一条动作都必须独特、有创意、不模板化。你严格遵循格式要求，只输出合法的 JSON。"


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

    recent_str = "暂无" if not recent_queries else "、".join(recent_queries[:5])

    return f"""请创造一个全新的、独特的「{category}」类别动作。

【参考示例（高质量模板）】
互动类：
  query: "高兴地用双手大幅度快速比一次心" | text: "一个人快速用双手完成一次大幅比心，最后回到站立姿态" | motion_description: "[[情绪:开心]，[动作:比心]，[次数:1次]，[手部:双手]，[幅度:大幅]，[速度:快速]]" | query_description: "[[比心]，[情绪:开心]，[次数:1次]，[手部:双手]，[幅度:大幅]，[速度:快速]]" | voice_feedback: "爱心发射！把满满的爱都送给你哟～" | aug_text: ["双手比心一次回到站立","双手快速比心一次然后站直","一个人快速用双手完成一次大幅比心，最后回到站立姿态","一个人用双手快速比心一次，之后回到站立姿势","一个人面带开心，快速用双手完成一次大幅比心，然后缓缓回到站立姿态","一个人情绪开心，双手快速大幅比心一次，随后恢复直立站姿"]
站立类：
  query: "来，立正" | text: "一个人双脚并拢，全身挺直，标准站姿保持稳定，最后回到站立姿态" | motion_description: "[[情绪:严肃]，[动作:立正]，[次数:1次]，[幅度:标准]，[速度:标准]]" | query_description: "[[立正]，[情绪:严肃]]" | voice_feedback: "立正完毕，随时待命！" | aug_text: ["全身立正一次回到站立","立正一次然后站好","一个人双脚并拢全身挺直标准站姿保持稳定最后回到站立姿态","一个人全身立正一次之后恢复站立姿势","一个人面容严肃，双脚并拢全身挺直标准站姿保持稳定，动作干脆利落","一个人情绪严肃，全身立正一次，姿态挺拔，随后恢复直立"]

【要素要求】
- 身体部位从以下选取：{body_parts_str}
- 动作方式参考：{actions_str}
- 动作必须是人类可以完成的，物理上真实可行
- 不要与以下已有动作重复：{recent_str}

【输出规范】
- query: 口语化指令，5-15 字，自然结尾（吧/呗/一下/看看）
- text: 以「一个人」开头，描述身体部位、幅度、速度、动作，以「最后回到站立姿态」结尾
- motion_description: 标签格式，「，」分隔，必含 [情绪:xxx][动作:xxx][次数:x次/步数:x步][幅度:xxx][速度:xxx]，可选 [手部:xxx][脚部:xxx][方向:xxx]
- query_description: 标签格式，以 [[动作名] 开头，可含 [情绪:xxx][次数:x次][手部:xxx][幅度:xxx][速度:xxx]（部分标签可省略）
- voice_feedback: 自然口语化回应，13-22 字（如「好嘞，...哈！」「嘿嘿，...哟~」）
- aug_text: 6 个文本变体数组，从极简描述到详细叙述，最后一个最详细

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
  "aug_text": ["简短版","略简版","标准版","略详版","详细版","最详版"]
}}"""


def _fix_json(json_str: str) -> str:
    """尝试修复常见的 JSON 格式问题"""
    json_str = json_str.strip()
    json_str = re.sub(r"^```(?:json)?\s*", "", json_str)
    json_str = re.sub(r"\s*```$", "", json_str)
    return json_str


async def _call_llm_with_retry(payload: dict, max_retries: int = 2) -> dict | None:
    """带指数退避重试的 LLM API 调用。"""
    api_key = _get_api_key()
    if not _is_local() and not api_key:
        print("[LLM] 未配置 DEEPSEEK_API_KEY，且未启用本地模型")
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                r = await client.post(
                    f"{API_BASE}/chat/completions",
                    json=payload,
                    headers=headers,
                )
            if r.status_code == 200:
                return r.json()
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
            print(f"[LLM] 网络错误，重试中...（第 {attempt + 1} 次）")
            await asyncio.sleep(1 * (attempt + 1))
            continue
        except Exception as e:
            print(f"[LLM] 未知错误: {e}")
            return None
    print(f"[LLM] 全部重试失败: {last_error}")
    return None


async def generate_single(category: str, recent_queries: list[str],
                          model: str = MODEL_NAME) -> dict | None:
    """
    调用 DeepSeek API 生成单条动作数据。

    Returns:
        解析后的动作数据 dict，失败返回 None
    """
    api_key = _get_api_key()
    if not _is_local() and not api_key:
        return None

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(category, recent_queries)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.9,
        "top_p": 0.95,
        "max_tokens": 1024,
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        result = await _call_llm_with_retry(payload)
        if result is None:
            return None
        content = result["choices"][0]["message"]["content"]
        response_text = _fix_json(content)
        data = json.loads(response_text)
        data["category"] = category
        data["is_head"] = _judge_is_head(
            data.get("query", ""), data.get("text", ""), category)
        return data
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


async def generate_batch(category: str, count: int,
                         recent_queries: list[str],
                         model: str = MODEL_NAME) -> list[dict]:
    """
    一次 API 调用生成多条动作数据（3-5 条），减少网络往返。

    Returns:
        解析后的动作数据列表，失败返回空列表
    """
    api_key = _get_api_key()
    if not _is_local() and not api_key:
        return []

    system_prompt = _build_system_prompt()

    cfg = get_category_config(category)
    if not cfg:
        cfg = get_category_config("其他")

    body_parts = get_body_parts_for_category(category)
    body_parts_str = "、".join(body_parts)
    emotions = get_emotions_for_category(category)
    emotions_str = "、".join(f"[{e}]" for e in emotions)
    actions = get_actions_for_category(category)
    actions_str = "、".join(actions[:20])
    recent_str = "暂无" if not recent_queries else "、".join(recent_queries[:5])

    user_prompt = f"""请创造 {count} 个全新的、互不重复的「{category}」类别动作。

【参考示例】
  query: "高兴地用双手大幅度快速比一次心" | text: "一个人快速用双手完成一次大幅比心，最后回到站立姿态" | motion_description: "[[情绪:开心]，[动作:比心]，[次数:1次]，[手部:双手]，[幅度:大幅]，[速度:快速]]" | query_description: "[[比心]，[情绪:开心]，[次数:1次]，[手部:双手]，[幅度:大幅]，[速度:快速]]" | voice_feedback: "爱心发射！把满满的爱都送给你哟～" | aug_text: ["双手比心一次回到站立","双手快速比心一次然后站直","一个人快速用双手完成一次大幅比心，最后回到站立姿态","一个人用双手快速比心一次，之后回到站立姿势","一个人面带开心，快速用双手完成一次大幅比心，然后缓缓回到站立姿态","一个人情绪开心，双手快速大幅比心一次，随后恢复直立站姿"]

【要素要求】
- 身体部位：{body_parts_str}
- 动作参考（创造不同动作）：{actions_str}
- 不要重复：{recent_str}

【输出规范】
- query: 口语化，5-15字，自然结尾
- text: 以「一个人」开头，以「最后回到站立姿态」结尾
- motion_description: 标签格式，必含 [情绪:xxx][动作:xxx][次数:x次/步数:x步][幅度:xxx][速度:xxx]，可选 [手部:xxx][脚部:xxx]
- query_description: 标签格式，以 [[动作名] 开头，可含 [情绪:xxx][次数:x次][手部:xxx] 等，部分可省略
- voice_feedback: 口语化，13-22字
- aug_text: 6 个文本变体数组，从极简到详细

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
    "aug_text": ["简短版","略简版","标准版","略详版","详细版","最详版"]
  }}
]"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.9,
        "top_p": 0.95,
        "max_tokens": 4096,
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        print(f"[LLM] 正在为「{category}」生成 {count} 条记录...")
        result = await _call_llm_with_retry(payload)
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
        print(f"[LLM] 已为「{category}」生成 {len(items)} 条记录")
        return items
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"[LLM] JSON 解析失败: {e}")
        return []


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
