"""zygc 营收占比（s2）+ 主力净流入验证测试（v2.1 更正）。

zygc 夹具：tests/fixtures/zygc_excerpt_20261107.csv，
摘录自 2026-11-07 晚实测（带 SH/SZ 前缀调用成功）：
- SH688017：2026-06-30 谐波减速器及金属部件 82.67%
- SZ002050：2026-06-30 制冷空调 61.80%、汽车零部件 38.20%
- SH601100：2025-12-31 液压油缸 48.02%、液压泵阀及马达 39.53%

主力净流入：2026-11-07 晚验证不通过——stock_fund_flow_concept(symbol="即时")
返回的是行业口径（387 行，列含“行业/净额”），不是概念板块口径；
stock_concept_fund_flow_hist 当晚调 502 限流未验证。热度分里去掉该指标。
"""
from pathlib import Path

import pandas as pd
import pytest

from app.services.heat_score import DEFAULT_WEIGHTS, BoardMetrics, compute_heat_scores
from app.services.revenue_share import parse_revenue_share, with_market_prefix

FIXTURE = Path(__file__).parent / "fixtures" / "zygc_excerpt_20261107.csv"
KEYWORDS = ["减速器", "伺服", "丝杠", "灵巧手", "执行器", "人形机器人", "机器人"]


def load_zygc() -> pd.DataFrame:
    return pd.read_csv(FIXTURE, encoding="utf-8-sig")


def test_market_prefix():
    assert with_market_prefix("688017") == "SH688017"
    assert with_market_prefix("002050") == "SZ002050"
    assert with_market_prefix("601100") == "SH601100"
    assert with_market_prefix("300124") == "SZ300124"
    assert with_market_prefix("920124") == "BJ920124"


def test_green_harmonic_s2_is_08267():
    df = load_zygc()
    result = parse_revenue_share(df[df["股票代码"] == 688017], KEYWORDS)
    assert result is not None
    assert result["share"] == pytest.approx(0.8267, abs=1e-4)
    assert result["matched_products"] == ["谐波减速器及金属部件"]
    assert result["report_date"] == "2026-06-30"


def test_sanhua_coarse_classification_is_missing_not_zero():
    # 三花产品分类太粗：制冷空调/汽车零部件都不含机器人关键词 -> 缺省 None，不是 0
    df = load_zygc()
    assert parse_revenue_share(df[df["股票代码"] == 2050], KEYWORDS) is None


def test_hengli_coarse_classification_is_missing_not_zero():
    # 恒立产品分类太粗：液压油缸/液压泵阀及马达都不含题材关键词 -> 缺省 None
    df = load_zygc()
    assert parse_revenue_share(df[df["股票代码"] == 601100], KEYWORDS) is None


def test_fund_flow_excluded_from_heat_weights():
    # 主力净流入验证不通过，热度分权重里不得有该指标
    assert "main_net_inflow" not in DEFAULT_WEIGHTS
    assert "net_inflow" not in DEFAULT_WEIGHTS
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9


def test_constituent_metrics_change_score_when_present():
    # 第二步指标齐全时按完整权重算；缺失时归一化，两者都应在 0-100 内且单调一致
    boards = [
        BoardMetrics(name="A", code="BK1", change_pct=2.0, up_ratio=0.8,
                     turnover_rate=5.0, market_cap=1e11, leading_change=10.0,
                     turnover_amount=5e9, limit_up_count=3),
        BoardMetrics(name="B", code="BK2", change_pct=-2.0, up_ratio=0.2,
                     turnover_rate=1.0, market_cap=1e10, leading_change=1.0,
                     turnover_amount=1e8, limit_up_count=0),
    ]
    scored = compute_heat_scores(boards)
    assert scored[0]["name"] == "A"
    assert scored[0]["heat_score"] > scored[1]["heat_score"]
    assert all(0 <= s["heat_score"] <= 100 for s in scored)
    # 第二步指标缺失时仍能算（归一化），且 A 仍高于 B
    for b in boards:
        b.turnover_amount = None
        b.limit_up_count = None
    scored2 = compute_heat_scores(boards)
    assert scored2[0]["name"] == "A"
