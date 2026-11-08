"""分层 s2 缺省 + 刷新时段/退避测试（v2 §11 验收 #11、#12）。"""
from datetime import datetime, timezone, timedelta

from app.services.layering import LayerSignals, layer_for, layer_reason, layer_score
from app.workers.rank_refresh import REFRESH_INTERVAL_MINUTES, backoff_minutes, is_trading_time

CST = timezone(timedelta(hours=8))


def test_layer_score_without_s2_renormalises():
    # s2 缺省：其余权重归一化（除以 0.75），不编造营收占比
    score, weights = layer_score(LayerSignals(s1=1, s2=None, s3=0.5, s4=0.5, s5=1.0))
    assert weights == {"s1": 0.35 / 0.75, "s3": 0.15 / 0.75, "s4": 0.15 / 0.75, "s5": 0.10 / 0.75}
    assert score == 100 * (0.35 * 1 + 0.15 * 0.5 + 0.15 * 0.5 + 0.10 * 1) / 0.75
    assert layer_for(score) == "core"


def test_layer_reason_never_invents_revenue_share():
    reason = layer_reason(segment="减速器", main_product_evidence="谐波减速器", graph_hops=1)
    assert "营收占比" not in reason
    assert "谐波减速器" in reason


def test_layer_reason_marks_chain_only():
    reason = layer_reason(segment="减速器", chain_hit=True, concept_hit=False, graph_hops=2)
    assert "仅图谱命中" in reason


def test_trading_time_weekday_morning():
    # 2026-11-06 是周五
    assert is_trading_time(datetime(2026, 11, 6, 10, 0, tzinfo=CST)) is True
    assert is_trading_time(datetime(2026, 11, 6, 12, 0, tzinfo=CST)) is False  # 午休
    assert is_trading_time(datetime(2026, 11, 6, 14, 0, tzinfo=CST)) is True
    assert is_trading_time(datetime(2026, 11, 6, 16, 0, tzinfo=CST)) is False


def test_trading_time_weekend_off():
    # 2026-11-07 是周六
    assert is_trading_time(datetime(2026, 11, 7, 10, 0, tzinfo=CST)) is False


def test_backoff_sequence():
    assert [backoff_minutes(n) for n in range(1, 8)] == [1, 2, 4, 8, 16, 16, 16]
    assert backoff_minutes(0) == 0


def test_refresh_interval_is_30_minutes_per_user_decision():
    # 用户定：刷新频率 30 分钟，不是 15 分钟
    assert REFRESH_INTERVAL_MINUTES == 30
