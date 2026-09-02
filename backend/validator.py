"""
格式校验器

三层校验流水线：
1. 格式校验 — 字段存在性、类型、枚举值、标签格式
2. 内容合法性 — AI 护栏落地（数量约束、部位合法性、物理可行性等）
3. 去重校验 — query_pool 去重 + 批次去重 + 跨文件去重
"""

from __future__ import annotations
import re
from database import query_exists


# === 工具函数 ===

def _parse_tags(md: str) -> dict[str, str]:
    """解析标签格式的 motion_description，返回 {key: value} 字典。"""
    tags = {}
    for match in re.finditer(r"\[([^\[\]]+):([^\[\]]+)\]", md):
        tags[match.group(1)] = match.group(2)
    return tags


# === 格式校验 ===

def validate_format(data: dict) -> tuple[bool, str]:
    """
    格式校验 — 检查必填字段、长度、枚举值、标签格式。

    Returns:
        (是否通过, 错误原因)
    """
    required = ["query", "query_description", "text", "motion_description",
                "voice_feedback", "category", "aug_text"]
    for field in required:
        if field not in data:
            return False, f"缺少必填字段: {field}"
        if field == "aug_text":
            if not isinstance(data[field], list) or len(data[field]) != 6:
                return False, f"aug_text 须为 6 个元素的数组"
        elif not isinstance(data[field], str) or not data[field].strip():
            return False, f"字段 {field} 为空"

    query = data["query"]
    text = data["text"]
    md = data["motion_description"]
    vf = data["voice_feedback"]

    # query 长度 2-50
    if len(query) < 2 or len(query) > 50:
        return False, f"query 长度为 {len(query)}，须在 2-50 之间"

    # text 必须以"回到站立姿态"结尾
    if "回到站立姿态" not in text:
        return False, "text 未以'回到站立姿态'结尾"

    # voice_feedback 长度 ≤ 30
    if len(vf) > 30:
        return False, f"voice_feedback 长度 {len(vf)}，超过 30 字符"

    # motion_description 标签格式校验
    tags = _parse_tags(md)
    if not tags:
        return False, f"motion_description 标签格式无法解析: {md[:50]}"

    for required_tag in ["情绪", "动作"]:
        if required_tag not in tags:
            return False, f"motion_description 缺少 [{required_tag}:xxx] 标签"

    # 次数或步数
    if "次数" not in tags and "步数" not in tags:
        return False, "motion_description 缺少 [次数:x次] 或 [步数:x步] 标签"

    # 幅度取值
    if "幅度" in tags and tags["幅度"] not in ("大幅", "小幅", "标准"):
        return False, f"幅度取值无效: {tags['幅度']}"

    # 速度取值
    if "速度" in tags and tags["速度"] not in ("快速", "慢速", "标准"):
        return False, f"速度取值无效: {tags['速度']}"

    # is_head 检验
    if "is_head" in data and not isinstance(data["is_head"], bool):
        return False, "is_head 类型错误，须为 bool"

    return True, ""


# === 内容合法性校验 ===

CATEGORY_STEP_LIMITS = {
    "行走": 5, "跑步": 5, "后退": 3, "侧移": 3,
}
CATEGORY_CRAWL_LIMIT = 6  # 爬行
CATEGORY_REPEAT_LIMITS = {
    "跳跃": 3, "踏步": 4,
}

# 情绪-速度一致性映射 — 模块级共享：validator 校验用，
# element_generator.generate_single 生成时同步按此约束抽取（源头收窄）
EMOTION_SPEED_MAP = {
    "爆发": ["快速"],
    "优雅": ["慢速", "标准"],
    "疲惫": ["慢速"],
    "困倦": ["慢速"],
    "惊吓": ["快速"],
}

BODY_PART_FORBIDDEN_ACTIONS = {
    "头部": ["踢", "踩", "跳", "跑", "打", "指", "握", "抓"],
    "脚": ["握", "抓", "指", "写", "画"],
    "腿": ["握", "抓", "指", "写", "画"],
}

FORBIDDEN_WORDS_PHYSICS = [
    "悬浮", "飞行", "飘", "腾空超过", "瞬移", "瞬间", "闪现",
    "同时向左又向右", "同时向前又向后", "反弯", "反向弯折", "逆关节",
]

FORBIDDEN_WORDS_SAFETY = [
    "撞墙", "自打", "自扇", "自掐", "打人", "踢人", "掐脖子",
    "三周", "高空坠落", "头部着地",
]


def validate_content(data: dict) -> tuple[bool, str]:
    """
    内容合法性校验 — AI 护栏落地。

    Returns:
        (是否通过, 错误原因)
    """
    category = data.get("category", "")
    text = data.get("text", "")
    md = data.get("motion_description", "")
    tags = _parse_tags(md)

    if not tags:
        return False, "motion_description 解析失败"

    # --- 次数/步数校验 ---
    if "次数" in tags:
        match = re.match(r"(\d+)次", tags["次数"])
        if match:
            num = int(match.group(1))
            if num > 3:
                return False, f"动作重复次数 {num} 超过上限 3"
            if category in CATEGORY_REPEAT_LIMITS:
                limit = CATEGORY_REPEAT_LIMITS[category]
                if num > limit:
                    return False, f"类别「{category}」次数 {num} 超过上限 {limit}"

    if "步数" in tags:
        match = re.match(r"(\d+)步", tags["步数"])
        if match:
            num = int(match.group(1))
            if category in CATEGORY_STEP_LIMITS:
                limit = CATEGORY_STEP_LIMITS[category]
                if num > limit:
                    return False, f"类别「{category}」步数 {num} 超过上限 {limit}"
            if category == "爬行" and num > CATEGORY_CRAWL_LIMIT:
                return False, f"爬行步数 {num} 超过上限 {CATEGORY_CRAWL_LIMIT}"

    # --- 部位禁止越界 ---
    for body_part, forbidden in BODY_PART_FORBIDDEN_ACTIONS.items():
        if body_part in text:
            for verb in forbidden:
                if verb in text:
                    if body_part == "头部" and verb == "指":
                        continue
                    return False, f"{body_part}不能执行'{verb}'动作"

    # --- 物理可行性 ---
    for word in FORBIDDEN_WORDS_PHYSICS:
        if word in text:
            return False, f"违反物理约束: 检测到'{word}'"

    # --- 安全伦理 ---
    for word in FORBIDDEN_WORDS_SAFETY:
        if word in text:
            return False, f"违反安全约束: 检测到'{word}'"

    # --- 脚不离地（站立类）---
    if category == "站立":
        jump_words = ["跳起", "双脚离地", "腾空"]
        for jw in jump_words:
            if jw in text:
                return False, f"站立类别不能有'{jw}'"

    # --- 比心时不能做下肢复杂动作 ---
    if "比心" in category:
        leg_complex = ["跳", "蹦", "跑"]
        for lw in leg_complex:
            if lw in text:
                return False, f"比心时不能做'{lw}'动作"

    # --- 情绪-速度一致性 ---
    emotion_name = tags.get("情绪", "")
    speed = tags.get("速度", "")
    if emotion_name in EMOTION_SPEED_MAP:
        allowed = EMOTION_SPEED_MAP[emotion_name]
        if speed and speed not in allowed:
            return False, f"情绪[{emotion_name}]必须配{'/'.join(allowed)}速度，当前为{speed}"

    return True, ""


# === 去重校验 ===

async def validate_dedup(query: str, batch_used: set[str]) -> tuple[bool, str]:
    """
    去重校验。

    Returns:
        (是否通过, 错误原因)
    """
    if query in batch_used:
        return False, f"query '{query}' 在本批次内重复"

    exists = await query_exists(query)
    if exists:
        return False, f"query '{query}' 与历史记录重复"

    return True, ""


async def validate_full(
    data: dict, batch_used: set[str]
) -> tuple[bool, str]:
    """完整的校验流水线"""
    # 1. 格式
    ok, err = validate_format(data)
    if not ok:
        return False, f"格式校验失败: {err}"

    # 2. 内容
    ok, err = validate_content(data)
    if not ok:
        return False, f"内容校验失败: {err}"

    # 3. 去重
    ok, err = await validate_dedup(data["query"], batch_used)
    if not ok:
        return False, f"去重校验失败: {err}"

    return True, ""
