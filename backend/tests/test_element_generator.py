"""element_generator 冒烟测试：结构契约、格式契约、去重、批次数量。

情绪-速度已在生成源头约束（EMOTION_SPEED_MAP，见 generate_single），
但 validate_content 仍含其他内容护栏（次数上限等）并非全组合兼容，
故此处只断言 validate_format（结构层）+ 情绪-速度绑定契约。
"""

import random
import re

from element_generator import generate_batch_for_category, generate_single
from element_pool import CATEGORIES
from validator import EMOTION_SPEED_MAP, validate_format

SEEDS = [20260903, 7, 42]


def test_format_contract_for_every_category_and_seed():
    """全部 16 类 × 3 个种子：单条生成结果必须通过格式校验。"""
    for category in CATEGORIES:
        for seed in SEEDS:
            random.seed(seed)
            record = generate_single(category, set())
            assert record is not None, f"{category} 生成失败"
            ok, err = validate_format(record)
            assert ok, f"{category} (seed={seed}) 违反格式契约: {err}"


def test_single_returns_all_required_fields():
    random.seed(1)
    record = generate_single("站立", set())
    assert record is not None
    for field in [
        "query", "query_description", "text", "motion_description",
        "voice_feedback", "category", "aug_text",
    ]:
        assert field in record, f"缺少字段 {field}"
    assert len(record["aug_text"]) == 6
    assert isinstance(record["is_head"], bool)
    assert record["text"].endswith("最后回到站立姿态")


def test_single_does_not_mutate_used_queries():
    """生成器只读传入的 used 集合；去重由调用方负责登记。"""
    random.seed(3)
    used: set[str] = set()
    for _ in range(60):
        record = generate_single("站立", used)
        assert record is not None, "站立要素池应能持续产出"
        assert record["query"] not in used, "生成器不应往 used 集合写入或产出重复 query"
        used.add(record["query"])
    assert len(used) == 60


def test_batch_respects_count_and_returns_unique_queries():
    random.seed(11)
    used: set[str] = set()
    records, used = generate_batch_for_category("行走", 5, used)
    assert len(records) == 5
    assert len(used) == 5
    queries = [r["query"] for r in records]
    assert len(set(queries)) == 5, "批次内 query 必须唯一"


def test_batch_continues_after_prefilled_queries():
    """used 预填后，批次结果不得与历史 query 重复。"""
    random.seed(23)
    used: set[str] = set()
    for _ in range(40):
        record = generate_single("行走", used)
        assert record is not None
        used.add(record["query"])
    history = set(used)

    records, _ = generate_batch_for_category("行走", 3, used)
    assert len(records) == 3
    new_queries = {r["query"] for r in records}
    assert len(new_queries) == 3
    assert history.isdisjoint(new_queries), "批次结果不得与历史 query 重复"


def test_emotion_speed_binding_enforced():
    """源头约束回归：情绪命中 EMOTION_SPEED_MAP 时速度必须落在允许集内。"""
    random.seed(20260903)
    seen: dict[str, int] = {}
    for category in CATEGORIES:
        for _ in range(200):
            record = generate_single(category, set())
            assert record is not None
            tags = dict(re.findall(r"\[([^\[\]]+):([^\[\]]+)\]",
                                   record["motion_description"]))
            emotion = tags.get("情绪", "")
            if emotion in EMOTION_SPEED_MAP:
                assert tags.get("速度") in EMOTION_SPEED_MAP[emotion], (
                    f"{category}: 情绪[{emotion}] 配了 [{tags.get('速度')}], "
                    f"允许 {EMOTION_SPEED_MAP[emotion]}")
                seen[emotion] = seen.get(emotion, 0) + 1
    # 全部绑定情绪都应被采样覆盖（防止约束实际从未被触发、测试空转）
    assert set(EMOTION_SPEED_MAP) <= set(seen), \
        f"绑定情绪未被采样覆盖: {set(EMOTION_SPEED_MAP) - set(seen)}"
