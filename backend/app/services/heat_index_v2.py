"""题材热度指数 v1.0（z-score 公式）—— 直接采用 astock-data 包 astock/compute/heat_index.py，未改逻辑。

公式：heat = 50 + scale * sum(weight * zscore)，截断到 0-100；权重之和必须为 1。
状态：已实现、已算新旧对照（见 docs/heat_comparison.md），未上线。切换公式需用户批准
（RULES.md：改公式必须递增 version），当前线上仍是 v2.1 百分位加权。
注意：包的 compute_heat 对缺失指标按 0.0 处理（m.get(name, 0.0)），全样本缺失时该项 z=0、
无贡献；冻结快照只有 pct_change、up_ratio 两项可用，其余四项全部记 0，见对照表。
"""
from statistics import mean, pstdev


def zscores(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    m = mean(values.values())
    s = pstdev(values.values())
    if s == 0:
        return {k: 0.0 for k in values}
    return {k: (v - m) / s for k, v in values.items()}


def compute_heat(metrics: dict[str, dict[str, float]], cfg: dict) -> dict[str, float]:
    """metrics: {theme_id: {metric_name: value}}；cfg: heat_weights.yaml 内容。"""
    weights, scale = cfg["weights"], cfg.get("scale", 25)
    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise ValueError("热度权重之和必须为 1")
    zsum = {t: 0.0 for t in metrics}
    for name, w in weights.items():
        z = zscores({t: m.get(name, 0.0) for t, m in metrics.items()})
        for t in metrics:
            zsum[t] += w * z[t]
    return {t: round(max(0.0, min(100.0, 50 + scale * v)), 1) for t, v in zsum.items()}


def to_package_metrics(boards) -> dict[str, dict[str, float]]:
    """BoardMetrics 列表 -> 包公式的 6 项输入。

    映射关系（冻结快照只有前两项可用，其余记 0.0——按包代码 m.get(name, 0.0) 的口径）：
    - pct_change：板块涨跌幅（第一步接口有）。
    - up_ratio：上涨家数占比（第一步接口有）。
    - limit_up_count：涨停数（第二步成分股聚合有；冻结快照无）。
    - turnover_share：板块成交额 / 全市场成交额（第二步成交额加总后可算；冻结快照无）。
    - net_inflow：主力净流入（无可用来源；Tushare moneyflow 待验证，见 docs/OPEN_ISSUES.md）。
    - news_heat：新闻/搜索热度（包里也没有采集器，见 docs/OPEN_ISSUES.md）。
    返回的 metrics 里缺失项记 0.0；调用方应同时记录缺失清单，不得把 0.0 当成真实值展示。
    """
    total_amount = sum(b.turnover_amount or 0.0 for b in boards) or None
    out: dict[str, dict[str, float]] = {}
    for b in boards:
        out[b.name] = {
            "pct_change": b.change_pct or 0.0,
            "up_ratio": b.up_ratio or 0.0,
            "limit_up_count": float(b.limit_up_count or 0.0),
            "turnover_share": (
                (b.turnover_amount / total_amount) if (b.turnover_amount and total_amount) else 0.0
            ),
            "net_inflow": 0.0,
            "news_heat": 0.0,
        }
    return out


def missing_inputs(boards) -> list[str]:
    """当前这批 boards 里包公式缺失的输入项（供对照表与接口标注用）。"""
    missing = []
    if not any(b.limit_up_count is not None for b in boards):
        missing.append("limit_up_count")
    if not any(b.turnover_amount is not None for b in boards):
        missing.append("turnover_share")
    missing.append("net_inflow")
    missing.append("news_heat")
    return missing
