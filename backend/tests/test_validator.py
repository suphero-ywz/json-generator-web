"""validator 纯函数测试：validate_format（格式）与 validate_content（内容护栏）。"""

import pytest

from validator import validate_content, validate_format

# === 合法样本 ===

FORMAT_OK = {
    "query": "做立正吧",
    "query_description": "[立正]，[情绪:专注]，[次数:1次]",
    "text": "一个人立正一次，目光专注，最后回到站立姿态",
    "motion_description": "[情绪:专注]，[动作:立正]，[次数:1次]，[幅度:标准]，[速度:标准]",
    "voice_feedback": "好嘞，站得笔直！",
    "category": "站立",
    "aug_text": ["a", "b", "c", "d", "e", "f"],
    "is_head": True,
}

CONTENT_OK = {
    "query": "挥挥手吧",
    "query_description": "[挥手]",
    "text": "一个人双手自然挥动2次，幅度标准，最后回到站立姿态",
    "motion_description": "[情绪:专注]，[动作:挥手]，[次数:2次]，[幅度:标准]，[速度:标准]",
    "voice_feedback": "好嘞",
    "category": "站立",
    "aug_text": ["a", "b", "c", "d", "e", "f"],
}


def _mutate(base: dict, **changes) -> dict:
    return {**base, **changes}


# === validate_format ===

def test_format_accepts_valid_sample():
    ok, err = validate_format(FORMAT_OK)
    assert ok, err


@pytest.mark.parametrize("field", [
    "query", "query_description", "text", "motion_description",
    "voice_feedback", "category", "aug_text",
])
def test_format_rejects_missing_required_field(field):
    ok, err = validate_format({k: v for k, v in FORMAT_OK.items() if k != field})
    assert not ok
    assert "缺少必填字段" in err


def test_format_rejects_empty_string_field():
    ok, err = validate_format(_mutate(FORMAT_OK, category="  "))
    assert not ok
    assert "为空" in err


def test_format_query_too_short():
    ok, err = validate_format(_mutate(FORMAT_OK, query="啊"))
    assert not ok
    assert "2-50" in err


def test_format_query_too_long():
    ok, err = validate_format(_mutate(FORMAT_OK, query="啊" * 51))
    assert not ok
    assert "2-50" in err


def test_format_text_must_end_with_back_to_standing():
    ok, err = validate_format(_mutate(
        FORMAT_OK, text="一个人立正一次，目光专注，然后站直"))
    assert not ok
    assert "回到站立姿态" in err


def test_format_voice_feedback_too_long():
    ok, err = validate_format(_mutate(FORMAT_OK, voice_feedback="啊" * 31))
    assert not ok
    assert "30" in err


def test_format_rejects_unparseable_motion_description():
    ok, err = validate_format(_mutate(
        FORMAT_OK, motion_description="平静地做了个立正动作"))
    assert not ok
    assert "标签格式无法解析" in err


def test_format_requires_emotion_and_action_tags():
    ok, err = validate_format(_mutate(
        FORMAT_OK, motion_description="[动作:立正]，[次数:1次]"))
    assert not ok
    assert "[情绪:xxx]" in err


def test_format_requires_count_or_steps_tag():
    ok, err = validate_format(_mutate(
        FORMAT_OK, motion_description="[情绪:专注]，[动作:立正]，[幅度:标准]，[速度:标准]"))
    assert not ok
    assert "次数" in err or "步数" in err


def test_format_rejects_invalid_amplitude():
    ok, err = validate_format(_mutate(
        FORMAT_OK, motion_description="[情绪:专注]，[动作:立正]，[次数:1次]，[幅度:超大]，[速度:标准]"))
    assert not ok
    assert "幅度取值无效" in err


def test_format_rejects_invalid_speed():
    ok, err = validate_format(_mutate(
        FORMAT_OK, motion_description="[情绪:专注]，[动作:立正]，[次数:1次]，[幅度:标准]，[速度:光速]"))
    assert not ok
    assert "速度取值无效" in err


def test_format_rejects_non_bool_is_head():
    ok, err = validate_format(_mutate(FORMAT_OK, is_head=1))
    assert not ok
    assert "is_head" in err


def test_format_rejects_aug_text_wrong_length():
    ok, err = validate_format(_mutate(FORMAT_OK, aug_text=["a"] * 5))
    assert not ok
    assert "aug_text" in err


# === validate_content ===

def test_content_accepts_valid_sample():
    ok, err = validate_content(CONTENT_OK)
    assert ok, err


def test_content_rejects_repeat_over_global_limit():
    md = "[情绪:活力]，[动作:跳跃]，[次数:4次]，[幅度:大幅]，[速度:快速]"
    ok, err = validate_content(_mutate(CONTENT_OK, category="跳跃", motion_description=md))
    assert not ok
    assert "超过上限 3" in err


def test_content_rejects_walk_steps_over_limit():
    md = "[情绪:悠闲]，[动作:快走]，[步数:6步]，[幅度:标准]，[速度:慢速]"
    ok, err = validate_content(_mutate(CONTENT_OK, category="行走", motion_description=md))
    assert not ok
    assert "上限 5" in err


def test_content_accepts_walk_steps_at_limit():
    md = "[情绪:悠闲]，[动作:快走]，[步数:5步]，[幅度:标准]，[速度:慢速]"
    ok, err = validate_content(_mutate(CONTENT_OK, category="行走", motion_description=md))
    assert ok, err


def test_content_rejects_crawl_steps_over_limit():
    md = "[情绪:专注]，[动作:狗爬]，[步数:7步]，[幅度:标准]，[速度:标准]"
    ok, err = validate_content(_mutate(CONTENT_OK, category="爬行", motion_description=md))
    assert not ok
    assert "上限 6" in err


def test_content_rejects_forbidden_head_action():
    text = "一个人头部向前踢一下，最后回到站立姿态"
    ok, err = validate_content(_mutate(CONTENT_OK, text=text))
    assert not ok
    assert "头部不能执行" in err


def test_content_allows_head_pointing_exemption():
    # 头部 + 指 是豁免组合（点头/指头动作），应放行
    text = "一个人头部轻点，手指示意一下，最后回到站立姿态"
    ok, err = validate_content(_mutate(CONTENT_OK, text=text))
    assert ok, err


def test_content_rejects_physics_violation():
    text = "一个人慢慢悬浮起来，最后回到站立姿态"
    ok, err = validate_content(_mutate(CONTENT_OK, text=text))
    assert not ok
    assert "物理约束" in err


def test_content_rejects_safety_violation():
    text = "一个人做出打人动作，最后回到站立姿态"
    ok, err = validate_content(_mutate(CONTENT_OK, text=text))
    assert not ok
    assert "安全约束" in err


def test_content_standing_category_cannot_jump():
    text = "一个人双脚跳起，最后回到站立姿态"
    ok, err = validate_content(_mutate(CONTENT_OK, category="站立", text=text))
    assert not ok
    assert "站立" in err


def test_content_heart_gesture_cannot_leg_move():
    text = "一个人蹦跳着比心，最后回到站立姿态"
    ok, err = validate_content(_mutate(CONTENT_OK, category="比心手势", text=text))
    assert not ok
    assert "比心时不能做" in err


def test_content_emotion_speed_consistency():
    md = "[情绪:爆发]，[动作:冲刺跑]，[次数:2次]，[幅度:大幅]，[速度:慢速]"
    ok, err = validate_content(_mutate(CONTENT_OK, motion_description=md))
    assert not ok
    assert "情绪[爆发]" in err


def test_content_emotion_speed_consistent_passes():
    md = "[情绪:爆发]，[动作:冲刺跑]，[次数:2次]，[幅度:大幅]，[速度:快速]"
    ok, err = validate_content(_mutate(CONTENT_OK, motion_description=md))
    assert ok, err
