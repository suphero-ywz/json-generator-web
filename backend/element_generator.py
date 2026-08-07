"""
要素池组合生成器 — 兜底模式

从各类别要素池中随机抽取元素，组合成符合规范的 JSON 数据。
以参考模板库 (merged_deduplicated.json, 3738 条) 为质量标准。
输出格式遵循 dataset_train_aug 标签格式。
"""

from __future__ import annotations
import random
import re
from element_pool import (
    AMPLITUDES, SPEEDS, REPEATS,
    QUERY_TEMPLATES, VOICE_TEMPLATES,
    get_category_config,
    get_emotions_for_category, get_actions_for_category,
)


def _pick(items: list) -> str:
    return random.choice(items)


# === 动作→身体部位语义匹配 ===

HEAD_ONLY_ACTIONS = {"歪头", "仰头", "低头", "转头", "点头", "摇头"}
HEAD_ACTION_BODY_PARTS = ["头部"]

STANDING_POSTURE_ACTIONS = {"立正", "稍息", "军姿", "靠墙站", "踮脚", "单脚站立"}
STANDING_POSTURE_PARTS = ["全身", "双脚", "双腿"]

ARM_ACTIONS = {"背手", "叉腰", "抱胸", "抱臂", "贴裤缝", "举过头顶",
               "挥手", "飞吻", "比心", "比V", "竖大拇指", "OK手势",
               "敬礼", "抱拳行礼", "举手提问", "打招呼"}
ARM_PARTS = ["双手", "右手", "左手", "双臂"]

HAND_ACTIONS = {"击掌", "握手", "碰拳", "鼓掌", "捂嘴笑", "摊手",
                "么么哒", "挽手", "掰手腕", "拜拜", "撒花庆祝",
                "头顶比心", "手指比心", "脸颊比心", "爱心发射",
                "背后比心", "单手半心", "双手大爱心", "胸前比心",
                "侧面比心", "跳跃比心", "招手", "挥手"}
HAND_PARTS = ["双手", "右手", "左手", "手指", "指尖"]

FULL_BODY_ACTIONS = {"拥抱", "鞠躬", "合影pose", "录视频", "挽留",
                     "鞠躬道歉", "叉腰得意", "招呼"}
FULL_BODY_PARTS = ["全身", "双手", "双臂"]

LEG_ACTIONS = {"慢走", "快走", "大步走", "踮脚走", "倒退走", "猫步",
               "绕圈走", "蹑手蹑脚走", "碎步走", "侧身走",
               "慢跑", "冲刺跑", "原地跑", "高抬腿跑", "折返跑",
               "追逐跑", "快步奔跑", "小碎步跑",
               "原地跳", "单脚跳", "双脚蹦", "连续跳", "跳起举手",
               "跳起转身", "开合跳",
               "警惕后退", "让路后退", "快速后退", "告别后退",
               "小心后退", "侧身后退", "踮脚后退",
               "左右横移", "螃蟹步", "防守滑步", "侧身挤过", "闪躲",
               "侧移一步", "横向跨步",
               "原地踏步", "高抬腿踏步", "跺脚", "踩水花踏步",
               "碎步踏", "单脚跺地", "双脚交替踏"}
LEG_PARTS = ["双脚", "双腿", "全身", "左脚", "右脚"]

SQUAT_ACTIONS = {"深蹲", "半蹲", "马步", "弓步", "蹲下捡物",
                 "蹲下系鞋带", "蹲下休息"}
SQUAT_PARTS = ["双腿", "全身", "膝盖"]

KNEEL_ACTIONS = {"求婚跪", "行礼跪", "系鞋带跪", "骑士受封跪",
                 "跪姿射击", "单膝下跪致敬"}
KNEEL_PARTS = ["右膝", "左膝", "全身"]

STUNT_ACTIONS = {"后空翻", "侧手翻", "倒立", "前滚翻", "鲤鱼打挺",
                 "单手俯卧撑", "旋转跳跃", "劈叉"}
STUNT_PARTS = ["全身", "双手", "双脚"]

DANCE_ACTIONS = {"曳步舞", "机械舞", "肚皮舞", "芭蕾旋转", "街舞",
                 "踢踏舞", "广场舞", "扭腰舞", "手势舞"}
DANCE_PARTS = ["全身", "双脚", "腰部", "双手"]

CRAWL_ACTIONS = {"狗爬", "匍匐前进", "蜘蛛爬", "熊爬", "鳄鱼爬",
                 "婴儿爬", "低姿爬行", "侧身爬"}
CRAWL_PARTS = ["双手", "双脚", "全身", "手肘"]

CARRY_ACTIONS = {"搬箱子", "推车", "端花瓶", "拉行李箱", "挂画",
                 "拎袋子", "抬桌子", "拖地", "扫地", "晾衣服",
                 "浇花", "搬重物", "端茶水", "挪花盆"}
CARRY_PARTS = ["双手", "双臂", "全身"]

DAILY_ACTIONS = {"梳头", "洗脸", "喝水", "打哈欠", "擦汗", "推眼镜",
                 "揉眼睛", "戴耳机", "伸懒腰", "看手表", "整理衣领",
                 "扇风", "打电话", "摸下巴思考", "看书", "照镜子",
                 "拍身上的灰"}
DAILY_PARTS_BY_ACTION = {
    "梳头": ["右手", "左手", "双手"],
    "洗脸": ["双手", "右手", "左手"],
    "喝水": ["右手", "左手", "双手"],
    "打哈欠": ["全身", "头部", "双手"],
    "擦汗": ["右手", "左手", "双手"],
    "推眼镜": ["右手", "左手", "手指"],
    "揉眼睛": ["右手", "左手", "手指"],
    "戴耳机": ["双手", "右手", "左手"],
    "伸懒腰": ["全身", "双手", "双臂"],
    "看手表": ["右手", "左手"],
    "整理衣领": ["右手", "左手", "双手"],
    "扇风": ["右手", "左手", "双手"],
    "打电话": ["右手", "左手", "双手"],
    "摸下巴思考": ["右手", "左手", "手指"],
    "看书": ["双手", "右手", "左手"],
    "照镜子": ["全身", "右手", "双手"],
    "拍身上的灰": ["右手", "双手", "左手"],
}

# === 动作→部位映射 ===
ACTION_BODY_MAP = {}
ACTION_BODY_MAP.update({a: HEAD_ACTION_BODY_PARTS for a in HEAD_ONLY_ACTIONS})
ACTION_BODY_MAP.update({a: STANDING_POSTURE_PARTS for a in STANDING_POSTURE_ACTIONS})
ACTION_BODY_MAP.update({a: ARM_PARTS for a in ARM_ACTIONS})
ACTION_BODY_MAP.update({a: HAND_PARTS for a in HAND_ACTIONS})
ACTION_BODY_MAP.update({a: FULL_BODY_PARTS for a in FULL_BODY_ACTIONS})
ACTION_BODY_MAP.update({a: LEG_PARTS for a in LEG_ACTIONS})
ACTION_BODY_MAP.update({a: SQUAT_PARTS for a in SQUAT_ACTIONS})
ACTION_BODY_MAP.update({a: KNEEL_PARTS for a in KNEEL_ACTIONS})
ACTION_BODY_MAP.update({a: STUNT_PARTS for a in STUNT_ACTIONS})
ACTION_BODY_MAP.update({a: DANCE_PARTS for a in DANCE_ACTIONS})
ACTION_BODY_MAP.update({a: CRAWL_PARTS for a in CRAWL_ACTIONS})
ACTION_BODY_MAP.update({a: CARRY_PARTS for a in CARRY_ACTIONS})


def _get_body_parts_for_action(action: str, category: str) -> list[str]:
    if action in ACTION_BODY_MAP:
        return ACTION_BODY_MAP[action]
    if action in DAILY_PARTS_BY_ACTION:
        return DAILY_PARTS_BY_ACTION[action]
    cfg = get_category_config(category)
    if cfg:
        return cfg.get("body_parts", ["全身"])
    return ["全身"]


# === 部位→标签映射 ===

UPPER_PARTS = {"右手", "左手", "双手", "双臂", "手指", "指尖",
               "手掌", "手腕", "手肘", "拳头", "掌心", "手背",
               "右臂", "左臂"}
LOWER_PARTS = {"右脚", "左脚", "双脚", "双腿", "膝盖", "右膝",
               "左膝", "大腿", "小腿", "脚掌"}


def _get_part_tag(body_part: str, category: str) -> str | None:
    """根据身体部位返回对应的部位标签（手部/脚部）。"""
    if body_part in UPPER_PARTS:
        return f"[手部:{body_part}]"
    if body_part in LOWER_PARTS:
        return f"[脚部:{body_part}]"
    return None


# === 字段生成 ===

def _generate_query(action: str, category: str) -> str:
    """生成口语化 query（5-20 字）。"""
    templates = QUERY_TEMPLATES.get(category, QUERY_TEMPLATES.get("其他", ["{action}"]))
    return random.choice(templates).replace("{action}", action)


def _generate_voice(action: str, category: str) -> str:
    """生成自然口语化语音反馈（13-22 字）。"""
    templates = VOICE_TEMPLATES.get(category, VOICE_TEMPLATES.get("其他", ["好嘞，{action}完成啦！"]))
    return random.choice(templates).replace("{action}", action)


def _generate_text(action: str, body_part: str, category: str,
                   amplitude: str, speed: str, repeat: str) -> str:
    """生成 text 字段（以「一个人」开头，以「最后回到站立姿态」结尾）。"""
    n = int(re.sub(r"\D", "", repeat) or "1")

    if action in HEAD_ONLY_ACTIONS:
        templates = [
            f"一个人{body_part}{amplitude}地{action}{n}次，目光专注，最后回到站立姿态",
            f"一个人{body_part}{amplitude}幅度{action}{n}次，脖颈放松，最后回到站立姿态",
        ]
    elif "走" in action or "跑" in action:
        templates = [
            f"一个人以{speed}速度{amplitude}幅度{action}，共{n}步，最后回到站立姿态",
            f"一个人用{body_part}{speed}地{action}，步幅均匀，共{n}步，最后回到站立姿态",
        ]
    elif "跳" in action and category == "跳跃":
        templates = [
            f"一个人双脚发力{action}{n}次，身体腾空后平稳落地，最后回到站立姿态",
            f"一个人腿部发力带动全身{action}{n}次，{amplitude}幅度，最后回到站立姿态",
        ]
    elif action in FULL_BODY_ACTIONS:
        templates = [
            f"一个人{body_part}自然地{action}{n}次，{amplitude}幅度，最后回到站立姿态",
            f"一个人身体{amplitude}幅度{action}{n}次，动作协调，最后回到站立姿态",
        ]
    elif action in ARM_ACTIONS or action in HAND_ACTIONS:
        templates = [
            f"一个人用{body_part}以{speed}速度{amplitude}幅度{action}{n}次，最后回到站立姿态",
            f"一个人用{body_part}{amplitude}地{action}{n}次，上肢动作标准，最后回到站立姿态",
        ]
    elif action in LEG_ACTIONS:
        templates = [
            f"一个人用{body_part}{speed}地{action}，保持身体平衡，最后回到站立姿态",
            f"一个人以{amplitude}幅度用{body_part}{action}，节奏均匀，最后回到站立姿态",
        ]
    else:
        templates = [
            f"一个人用{body_part}{amplitude}地{action}{n}次，动作干脆利落，最后回到站立姿态",
            f"一个人以{amplitude}幅度用{body_part}{action}{n}次，节奏均匀，最后回到站立姿态",
        ]
    return random.choice(templates)


def _is_head_only(action: str, body_part: str, category: str) -> bool:
    return action in HEAD_ONLY_ACTIONS and body_part == "头部"


def _build_motion_description(emotion: str, body_part: str, amplitude: str,
                               speed: str, action: str, repeat: str,
                               category: str) -> str:
    """生成 motion_description（标签格式）。"""
    tags = [f"[情绪:{emotion}]", f"[动作:{action}]"]

    n = int(re.sub(r"\D", "", repeat) or "1")
    if "步" in repeat:
        tags.append(f"[步数:{n}步]")
    else:
        tags.append(f"[次数:{n}次]")

    part_tag = _get_part_tag(body_part, category)
    if part_tag:
        tags.append(part_tag)

    tags.append(f"[幅度:{amplitude}]")
    tags.append(f"[速度:{speed}]")

    return "[" + "]，[".join(tags) + "]"


def _build_query_description(action: str, emotion: str, body_part: str,
                              amplitude: str, speed: str, repeat: str,
                              category: str) -> str:
    """生成 query_description（标签格式，部分标签可随机省略以模拟多样性）。"""
    tags = [f"[{action}]"]

    if random.random() < 0.6:
        tags.append(f"[情绪:{emotion}]")
    if random.random() < 0.5:
        n = int(re.sub(r"\D", "", repeat) or "1")
        if "步" in repeat:
            tags.append(f"[步数:{n}步]")
        else:
            tags.append(f"[次数:{n}次]")
    part_tag = _get_part_tag(body_part, category)
    if part_tag and random.random() < 0.7:
        tags.append(part_tag)
    if random.random() < 0.5:
        tags.append(f"[幅度:{amplitude}]")
    if random.random() < 0.4:
        tags.append(f"[速度:{speed}]")

    return "[" + "]，[".join(tags) + "]"


def _generate_aug_text(text: str, action: str, body_part: str,
                        category: str, emotion: str) -> list[str]:
    """生成 6 个文本变体（从极简到详细）。"""
    short_text = text.replace("，最后回到站立姿态", "").replace("最后回到站立姿态", "")

    variants = [
        f"{body_part}{action}一次，回到站立",
        f"{body_part}{action}一次，然后站直",
        text,
        f"一个人用{body_part}{action}一次，之后回到站立姿势",
        f"一个人面带{emotion}，{short_text}，然后缓缓回到站立姿态",
        f"一个人情绪{emotion}，{short_text}，随后恢复直立站姿",
    ]

    while len(variants) < 6:
        variants.append(text)

    return variants[:6]


def generate_single(category: str, used_queries: set[str]) -> dict | None:
    """
    从要素池生成单条动作数据。

    Returns:
        生成的动作数据 dict，或 None（要素池耗尽）
    """
    cfg = get_category_config(category)
    if not cfg:
        cfg = get_category_config("其他")

    actions = cfg["actions"]
    emotions = get_emotions_for_category(category)

    max_attempts = 100
    for _ in range(max_attempts):
        action = _pick(actions)
        body_parts = _get_body_parts_for_action(action, category)
        body_part = _pick(body_parts)
        emotion = _pick(emotions)
        amplitude = _pick(AMPLITUDES)
        speed = _pick(SPEEDS)
        repeat = _pick(REPEATS)

        raw_query = _generate_query(action, category)
        if raw_query in used_queries:
            continue

        text = _generate_text(action, body_part, category, amplitude, speed, repeat)
        motion_description = _build_motion_description(
            emotion, body_part, amplitude, speed, action, repeat, category)
        query_description = _build_query_description(
            action, emotion, body_part, amplitude, speed, repeat, category)
        voice_feedback = _generate_voice(action, category)
        is_head = _is_head_only(action, body_part, category)
        aug_text = _generate_aug_text(text, action, body_part, category, emotion)

        return {
            "query": raw_query,
            "query_description": query_description,
            "text": text,
            "motion_description": motion_description,
            "is_head": is_head,
            "voice_feedback": voice_feedback,
            "category": category,
            "aug_text": aug_text,
        }

    return None


def generate_batch_for_category(
    category: str, count: int, used_queries: set[str]
) -> tuple[list[dict], set[str]]:
    """为某个类别生成指定数量的动作数据。"""
    results = []
    for _ in range(count):
        record = generate_single(category, used_queries)
        if record is None:
            break
        results.append(record)
        used_queries.add(record["query"])
    return results, used_queries
