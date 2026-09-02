"""generator 生成调度器测试。

mock llm_client，验证 2026-09-03 决议的行为契约：
- LLM 模式 100% LLM 产出：调用失败缺口留待下轮重试，预算耗尽如实报缺，绝不混要素池
- 内容护栏：validate_content 违规条丢弃并计数，缺口自动补
- 去重：query 单键指纹（同 query 不同 motion 只留一条）
- 要素池模式回归：满量且不触 LLM
- 批量：meta 跨文件聚合
"""

import asyncio

import pytest

import generator

CATS = [{"name": "跳跃", "weight": 1}]


def _run(coro):
    return asyncio.run(coro)


def _rec(query, emotion="开心", speed="标准", action="立定跳远"):
    """构造可通过 validate_content 的合规 LLM 产出。"""
    return {
        "query": query,
        "query_description": f"[[{action}]，[情绪:{emotion}]]",
        "text": "一个人双脚发力跳起，双臂摆动，落地缓冲平稳，最后回到站立姿态",
        "motion_description": (
            f"[[情绪:{emotion}]，[动作:{action}]，[次数:1次]，"
            f"[幅度:标准]，[速度:{speed}]]"
        ),
        "voice_feedback": "好嘞，跳得真高！",
        "category": "跳跃",
        "aug_text": ["变体一", "变体二", "变体三", "变体四", "变体五", "变体六"],
    }


def _bad_rec(query):
    """情绪-速度矛盾的违规产出（[爆发] 必须配 [快速]）。"""
    return _rec(query, emotion="爆发", speed="慢速")


@pytest.fixture
def no_db(monkeypatch):
    """隔离真实数据库：历史池写入与历史记录保存改为空操作。"""
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(generator, "add_many_to_pool", _noop)
    monkeypatch.setattr(generator, "save_history", _noop)


def _make_llm_fake(monkeypatch, responses):
    """按调用顺序返回 responses 的 llm_generate_batch mock。

    responses: list，None 表示整批失败，list[dict] 为产出；末项重复兜底。
    返回调用计数器，便于断言调用次数/轮次。
    """
    box = {"n": 0}

    async def fake(category, count, recent_queries, provider="auto"):
        idx = min(box["n"], len(responses) - 1)
        box["n"] += 1
        resp = responses[idx]
        if resp is None:
            return []
        return [dict(r) for r in resp[:count]]

    monkeypatch.setattr(generator, "llm_generate_batch", fake)
    return box


def _forbid_pool(monkeypatch):
    """要素池生成器炸弹：任何调用即测试失败（纯 LLM 模式不应触碰）。"""
    def _bomb(*_a, **_k):
        raise AssertionError("纯 LLM 模式不应调用要素池生成器")

    monkeypatch.setattr(generator, "pool_generate_single", _bomb)


def _forbid_llm(monkeypatch):
    """LLM mock 炸弹：要素池模式不应触发 LLM 调用。"""
    async def _bomb(*_a, **_k):
        raise AssertionError("要素池模式不应调用 LLM")

    monkeypatch.setattr(generator, "llm_generate_batch", _bomb)


# === LLM 模式：纯 LLM 契约 ===

def test_llm_full_success_pure_llm(no_db, monkeypatch):
    """正常路径：满量、全 LLM、一轮完成、无丢弃无缺量。"""
    _forbid_pool(monkeypatch)
    qs = [_rec(f"跳跃动作{i}") for i in range(10)]
    _make_llm_fake(monkeypatch, [qs[:5], qs[5:]])

    result = _run(generator.generate(CATS, 10, "llm"))
    meta = result["meta"]

    assert result["success"]
    assert len(result["data"]) == 10
    assert meta["missing"] == 0
    assert meta["discarded"] == 0
    assert meta["llm_failures"] == 0
    assert meta["rounds_used"] == 1
    # query 全部唯一
    assert len({d["query"] for d in result["data"]}) == 10


def test_llm_total_failure_reports_missing(no_db, monkeypatch):
    """LLM 持续不可用：预算耗尽后如实报缺，数据为空，要素池未被触碰。"""
    _forbid_pool(monkeypatch)
    _make_llm_fake(monkeypatch, [None])

    result = _run(generator.generate(CATS, 10, "llm"))
    meta = result["meta"]

    assert result["data"] == []
    assert meta["generated"] == 0
    assert meta["missing"] == 10
    assert meta["llm_failures"] == 8        # MAX_LLM_ROUNDS 默认预算耗尽
    assert meta["rounds_used"] == 8


def test_llm_recovers_after_failures(no_db, monkeypatch):
    """失败缺口自动滚入下一轮，恢复后补满；不混要素池。"""
    _forbid_pool(monkeypatch)
    qs = [_rec(f"恢复跳跃{i}") for i in range(10)]
    calls = _make_llm_fake(monkeypatch, [None, None, qs[:5], qs[5:]])

    result = _run(generator.generate(CATS, 10, "llm"))
    meta = result["meta"]

    assert len(result["data"]) == 10
    assert meta["missing"] == 0
    assert meta["llm_failures"] == 2
    assert meta["rounds_used"] == 3         # 前两轮失败、第三轮补满


def test_llm_discards_rule_violations_and_refills(no_db, monkeypatch):
    """内容护栏：违规条（爆发+慢速）被丢弃计数，缺口由后续调用补足。"""
    _forbid_pool(monkeypatch)
    good = [_rec(f"合规跳跃{i}") for i in range(5)]
    first = good[:2] + [_bad_rec(f"矛盾跳跃{i}") for i in range(3)]
    _make_llm_fake(monkeypatch, [first, good[2:]])

    result = _run(generator.generate(CATS, 5, "llm"))
    meta = result["meta"]

    assert len(result["data"]) == 5
    assert meta["missing"] == 0
    assert meta["discarded"] == 3
    assert meta["llm_failures"] == 0
    # 数据中不含违规条
    assert all("矛盾跳跃" not in d["query"] for d in result["data"])


def test_llm_same_query_different_motion_dedup(no_db, monkeypatch):
    """query 单键指纹：同 query 不同 motion 只保留一条。"""
    _forbid_pool(monkeypatch)
    dup_a = _rec("再来一跳")
    dup_b = _rec("再来一跳", action="开合跳")    # 同 query、不同动作
    others = [_rec(f"独立跳跃{i}") for i in range(3)]
    _make_llm_fake(monkeypatch, [[dup_a, others[0]], [dup_b, others[1]], [others[2]]])

    result = _run(generator.generate(CATS, 4, "llm"))
    queries = [d["query"] for d in result["data"]]

    assert len(result["data"]) == 4
    assert len(set(queries)) == 4               # 同 query 重复被指纹挡掉
    assert queries.count("再来一跳") == 1
    assert result["meta"]["missing"] == 0


# === 要素池模式：回归 ===

def test_pool_mode_full_no_llm(no_db, monkeypatch):
    """要素池模式：真实组合生成，满量、无缺口、不触 LLM。"""
    _forbid_llm(monkeypatch)

    result = _run(generator.generate(CATS, 10, "element_pool"))
    meta = result["meta"]

    assert result["success"]
    assert len(result["data"]) == 10
    assert meta["missing"] == 0
    assert meta["llm_failures"] == 0
    assert len({d["query"] for d in result["data"]}) == 10


def test_llm_seen_shared_across_calls(no_db, monkeypatch):
    """任务级共享指纹：同一 seen 集续跑第二批，复读首批 query 被拦、缺口补新。

    等价模型：批量任务多文件并发共享 seen 时（入列原子、单线程），结果与
    串行共享 seen 一致——本测试以两次共享 seen 的串行调用来锁定契约：
    文件间（调用间）query 零重叠是硬保证，recent 窗口仅为提示。
    """
    _forbid_pool(monkeypatch)
    qa, qb = _rec("共享跳A"), _rec("共享跳B")
    qc, qd = _rec("共享跳C"), _rec("共享跳D")
    # 调用1：首次批量；调用2：复读 A + 新 C；调用3：新 D 兜底
    _make_llm_fake(monkeypatch, [[qa, qb], [qa, qc], [qd]])

    seen = set()
    first = _run(generator._generate_records(
        CATS, 2, True, "deepseek", seen, None, None))
    second = _run(generator._generate_records(
        CATS, 2, True, "deepseek", seen, None, None))

    q_first = {r["query"] for r in first.records}
    q_second = {r["query"] for r in second.records}

    assert q_first == {"共享跳A", "共享跳B"}
    assert len(second.records) == 2          # 复读 A 被拦后缺口由 C/D 补足
    assert q_second == {"共享跳C", "共享跳D"}
    assert not (q_first & q_second)          # 跨调用零重叠（文件间零重叠的等价模型）
    assert len(first.records) == 2 and len(second.records) == 2   # 均满量无缺口


# === 批量：共享核心循环 + meta 聚合 ===

def test_batch_pure_llm_meta_aggregates(no_db, monkeypatch):
    """批量：每文件经共享核心循环产出纯 LLM 数据，顶层 meta 跨文件聚合。"""
    _forbid_pool(monkeypatch)
    counter = {"i": 0}

    async def fake(category, count, recent_queries, provider="auto"):
        out = []
        for _ in range(count):
            counter["i"] += 1
            out.append(_rec(f"批量跳跃{counter['i']}"))
        return out

    monkeypatch.setattr(generator, "llm_generate_batch", fake)

    result = _run(generator.generate_batch(CATS, 4, 2, "llm"))
    meta = result["meta"]

    assert result["success"]
    assert len(result["files"]) == 2
    total = sum(len(f["data"]) for f in result["files"])
    assert total == 8
    assert meta["generated"] == 8
    assert meta["missing"] == 0
    assert meta["llm_failures"] == 0
    assert meta["discarded"] == 0
    # 每文件自身 meta 齐全，且各文件数据无重叠 query
    all_queries = [d["query"] for f in result["files"] for d in f["data"]]
    assert len(set(all_queries)) == 8
    for f in result["files"]:
        assert f["meta"]["generated"] == 4
