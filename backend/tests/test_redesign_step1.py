"""榜单拆分、新鲜度诚实标注、发布闸门测试。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.monitor.freshness import CN, check, describe_status, is_trading_time
from app.publish.gate import diff_changelog, route
from app.publish.validator import check_statement
from app.services.topic_filter import classify_topic, split_ranking

CFG = {"freshness": {
    "quotes_intraday": {"max_age": 180, "trading_only": True},
    "theme_heat_ts": {"max_age": 180, "trading_only": True},
    "announcements": {"max_age": 1800, "trading_only": False},
    "quotes_daily": {"max_age": 90000, "trading_only": False},
    "relevance_scores": {"max_age": 90000, "trading_only": False},
}}


def test_classify_and_split():
    names = ["东方财富热股", "昨日涨停_含一字", "近期新高", "农业种植", "绿色电力",
             "红利股", "TOPCon电池", "深股通", "预盈预增"]
    assert [classify_topic(n) for n in names] == (
        ["风格/行为"] * 3 + ["题材"] * 2 + ["风格/行为", "题材", "风格/行为", "风格/行为"]
    )
    a, b = split_ranking([{"name": n, "score": 1} for n in names])
    assert [x["name"] for x in a] == ["农业种植", "绿色电力", "TOPCon电池"]
    assert [x["rank"] for x in a] == [1, 2, 3] and len(b) == 6


def test_trading_time():
    assert is_trading_time(datetime(2026, 11, 9, 10, 0, tzinfo=CN))      # 周一上午
    assert not is_trading_time(datetime(2026, 11, 8, 10, 0, tzinfo=CN))  # 周日
    assert not is_trading_time(datetime(2026, 11, 9, 12, 0, tzinfo=CN))  # 午休


def test_weekend_never_stale():
    # 周日 10:00，快照是周五收盘：休市，不标 stale
    now = datetime(2026, 11, 8, 10, 0, tzinfo=CN)
    snap = datetime(2026, 11, 6, 15, 0, tzinfo=CN)
    d = describe_status(now, snap)
    assert d["market_status"] == "market_closed" and d["stale"] is False
    assert d["trade_date"] == "2026-11-06" and d["stale_reason"] is None


def test_trading_day_missed_refresh_is_stale():
    # 周一 10:00，快照还是上周五：交易日刷新失败，标 stale 并写清原因
    now = datetime(2026, 11, 9, 10, 0, tzinfo=CN)
    snap = datetime(2026, 11, 6, 15, 0, tzinfo=CN)
    d = describe_status(now, snap)
    assert d["market_status"] == "trading" and d["stale"] is True
    assert "2026-11-09" in (d["stale_reason"] or "")


def test_no_snapshot_is_stale():
    d = describe_status(datetime(2026, 11, 9, 10, 0, tzinfo=CN), None)
    assert d["stale"] is True and d["trade_date"] is None


def test_freshness_check_skips_off_session():
    now = datetime(2026, 11, 8, 10, 0, tzinfo=CN)
    last = {k: now for k in CFG["freshness"]}
    assert check(now, last, CFG) == []


def test_gate_and_validator():
    assert route([]) == "auto_publish" and route(["no_source"]) == "review"
    assert diff_changelog({"a": 1}, {"a": 2, "b": 3}) == "更新 1 条；新增 1 条"
    banned = ["龙头", "看好"]
    issues = check_statement(
        {"text": "该公司是龙头，市场规模 82.39 亿元",
         "sources": [{"url": "https://example.com", "page": 1,
                      "quote": "中国 2025 年人形机器人市场规模 82.39 亿元"}]},
        banned)
    assert "banned_word:龙头" in issues
    assert not any(i.startswith("number_not_in_source") for i in issues)
    issues2 = check_statement(
        {"text": "市场规模 999 亿元", "sources": [{"url": "https://example.com", "page": 1,
         "quote": "中国 2025 年人形机器人市场规模 82.39 亿元"}]}, banned)
    assert any(i.startswith("number_not_in_source") for i in issues2)
