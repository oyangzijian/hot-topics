"""热度分计算 — 修正版规格 v2 §6.1（v2.1 两步走）。

硬性约束（2026-11-07 实测）：
- stock_board_concept_name_em() 只有 13 个字段，没有成交额、主力净流入、
  涨停家数。第一步（概念列表接口）只取涨跌幅/换手率/上涨占比/总市值/
  领涨股涨跌幅；第二步（成分股 stock_board_concept_cons_em 加总/计数，
  只对榜单前 N 个板块做，缓存 1 小时）补成交额和涨停数。
- 主力净流入：2026-11-07 晚验证不通过——stock_fund_flow_concept(symbol="即时")
  返回的是行业口径（387 行，列含“行业/净额”），不是概念板块口径，人形
  机器人这类概念不在其中；stock_concept_fund_flow_hist 当晚调 502 限流未
  验证。结论：热度分里去掉主力净流入，不硬编，待退避后重测再定。
- rank_pct 为标准百分位排名（含并列平均），取值 [0, 1]。
- 缺失指标权重置 0，其余权重归一化。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# v2.1 权重（键为指标名，与 HEAT_WEIGHTS_JSON 对应；合计 1.00）
# 注意：DEFAULT_WEIGHTS 里没有 main_net_inflow——验证不通过，已去掉。
DEFAULT_WEIGHTS: dict[str, float] = {
    "change_pct": 0.25,      # 第一步：概念列表
    "up_ratio": 0.20,        # 第一步：概念列表
    "turnover_rate": 0.10,   # 第一步：概念列表（换手率，不是成交额）
    "market_cap": 0.10,      # 第一步：概念列表
    "leading_change": 0.05,  # 第一步：概念列表
    "turnover_amount": 0.20,  # 第二步：成分股成交额加总
    "limit_up_count": 0.10,  # 第二步：成分股涨停数计数（近似，见 akshare_client）
}

METRIC_FIELDS = tuple(DEFAULT_WEIGHTS.keys())


@dataclass
class BoardMetrics:
    """一个概念板块在某一快照的可用指标。None = 该指标缺失。"""

    name: str
    code: str
    change_pct: float | None = None
    up_ratio: float | None = None  # 上涨家数 / (上涨+下跌)，分母为 0 时为 None
    turnover_rate: float | None = None  # 换手率(%)，不是成交额
    market_cap: float | None = None  # 总市值(元)
    leading_change: float | None = None  # 领涨股票-涨跌幅(%)
    leading_company: str | None = None  # 领涨股票名（仅展示用，不参与热度分）
    leading_code: str | None = None  # 领涨股票代码（供领涨公司点进公司页）
    up_count: int | None = None  # 上涨家数（第一步接口有）
    down_count: int | None = None  # 下跌家数（第一步接口有）
    turnover_amount: float | None = None  # 第二步：成分股成交额加总(元)
    limit_up_count: float | None = None  # 第二步：成分股涨停数计数（近似）

    def get(self, metric: str) -> float | None:
        return getattr(self, metric)


def _percentile_ranks(values: list[float | None]) -> list[float | None]:
    """标准百分位排名：(严格小于 x 的个数 + 0.5*等于 x 的个数) / n。

    缺失值保持 None；n 为全部样本数（含缺失），与 v2 规格一致。
    """
    n = len(values)
    out: list[float | None] = []
    for x in values:
        if x is None:
            out.append(None)
            continue
        less = sum(1 for v in values if v is not None and v < x)
        equal = sum(1 for v in values if v is not None and v == x)
        out.append((less + 0.5 * equal) / n)
    return out


def compute_heat_scores(
    boards: list[BoardMetrics],
    weights: dict[str, float] | None = None,
) -> list[dict]:
    """返回按 heat_score 降序、同分按 market_cap 降序排列的结果。

    每项：{name, code, heat_score, metrics, used_weights}。
    heat_score 为 0-100 的浮点数；空输入返回 []。
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items() if k in DEFAULT_WEIGHTS})
    if not boards:
        return []

    pcts: dict[str, list[float | None]] = {
        m: _percentile_ranks([b.get(m) for b in boards]) for m in METRIC_FIELDS
    }

    results: list[dict] = []
    for i, b in enumerate(boards):
        # 缺失归一化：只对本行可用的指标求和，再除以可用权重之和。
        usable = {m: w[m] for m in METRIC_FIELDS if pcts[m][i] is not None}
        if not usable:
            heat = 0.0
        else:
            total_w = sum(usable.values())
            heat = 100.0 * sum(pcts[m][i] * usable[m] for m in usable) / total_w
        results.append(
            {
                "name": b.name,
                "code": b.code,
                "heat_score": round(heat, 2),
                "metrics": {
                    "change_pct": b.change_pct,
                    "up_ratio": b.up_ratio,
                    "turnover_rate": b.turnover_rate,
                    "market_cap": b.market_cap,
                    "leading_change": b.leading_change,
                    "turnover_amount": b.turnover_amount,
                    "limit_up_count": b.limit_up_count,
                },
                "used_weights": usable,
            }
        )
    # 排序：heat 降序，同分 market_cap 降序（None 的市值排最后）
    results.sort(
        key=lambda r: (
            -r["heat_score"],
            -(r["metrics"]["market_cap"] or -1),
        )
    )
    return results


def topic_heat_score(board_scores: list[dict], weights: list[float] | None = None) -> float:
    """题材热度 = 其映射板块热度分的加权均值（默认权重均为 1）。

    对应 topic_concept_map.weight。空列表返回 0.0。
    """
    if not board_scores:
        return 0.0
    ws = weights if weights is not None else [1.0] * len(board_scores)
    if len(ws) != len(board_scores):
        raise ValueError("weights 长度必须与板块数一致")
    total = sum(ws)
    if total == 0:
        return 0.0
    return round(
        sum(s["heat_score"] * w for s, w in zip(board_scores, ws)) / total, 2
    )
