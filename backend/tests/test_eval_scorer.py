"""抽取评测计分测试：docs/EXTRACTION_EVAL.md 的计分口径。"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.extract.eval_scorer import (  # noqa: E402
    aggregate_statement_scores,
    score_revenue,
    score_statements,
)


def test_score_statements_miss_false_intercepted():
    gold = [
        {"kind": "overview", "text": "人形机器人是具身智能的载体。"},
        {"kind": "timeline", "text": "2023年11月工信部发布指导意见。"},
        {"kind": "overview", "text": "减速器是核心零部件。"},
    ]
    extracted = [
        {"kind": "overview", "text": "人形机器人是具身智能的载体。"},
        {"kind": "overview", "text": "人形机器人市场将增长十倍。"},  # 误抽：gold 没有
        {"kind": "timeline", "text": "2023年11月工信部发布指导意见。"},
    ]
    # 下标 1 的误抽被校验器拦截（引文里没有“十倍”）
    issues = {1: ["number_not_in_source:十倍"]}
    s = score_statements(gold, extracted, issues)
    assert s["gold_total"] == 3 and s["matched"] == 2
    assert s["missed"] == 1 and s["miss_rate"] == 1 / 3
    assert s["false_total"] == 1
    assert s["validator_intercepted"] == 1 and s["escaped"] == 0
    assert s["interception_rate"] == 1.0
    assert s["per_kind"]["overview"]["missed"] == 1


def test_score_statements_escaped_counts():
    gold = [{"kind": "overview", "text": "甲公司主营减速器。"}]
    extracted = [{"kind": "overview", "text": "甲公司主营减速器。"},
                 {"kind": "overview", "text": "甲公司市占率第一。"}]
    # 误抽通过了校验（漏网）：escaped 必须被数出来，上线门槛是 0
    s = score_statements(gold, extracted, {0: [], 1: []})
    assert s["escaped"] == 1
    assert s["interception_rate"] == 0.0


def test_score_revenue():
    gold = [{"segment": "谐波减速器及金属部件", "share": 0.8267},
            {"segment": "其他", "share": 0.1733}]
    extracted = [{"segment": "谐波减速器及金属部件", "share": 0.83},
                 {"segment": "智能装备", "share": 0.17}]
    s = score_revenue(gold, extracted)
    assert s["matched"] == 1
    assert s["missed_segments"] == ["其他"]
    assert s["extra_segments"] == ["智能装备"]
    assert abs(s["max_abs_error"] - 0.0033) < 1e-9


def test_aggregate():
    a = score_statements(
        [{"kind": "overview", "text": "甲"}],
        [{"kind": "overview", "text": "甲"}],
        {0: []},
    )
    b = score_statements(
        [{"kind": "overview", "text": "乙"}, {"kind": "overview", "text": "丙"}],
        [{"kind": "overview", "text": "乙"}],
        {0: []},
    )
    agg = aggregate_statement_scores([a, b])
    assert agg["docs"] == 2
    assert agg["gold_total"] == 3 and agg["matched"] == 2
    assert agg["miss_rate"] == 1 / 3
    assert agg["escaped"] == 0
