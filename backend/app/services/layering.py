"""公司分层 — 修正版规格 v2 §6.2.

硬性约束（2026-11-07 实测，更正）：
- stock_zygc_em 不是接口死了，是之前调用错了：代码必须带市场前缀 SH/SZ
  （见 services/revenue_share.py）。s2（题材相关业务营收占比）有路了：
  用带前缀的 zygc，取最新报告期、按产品分类，产品名与题材关键词匹配后
  加总占比；匹配不到的记缺省（None），不记 0，权重归一化。
- 三花、恒立的产品分类本身太粗，机器人业务拆不出来——匹配不到时如实记缺省。
- layer_reason 里不得出现无来源的百分比。
"""
from __future__ import annotations

from dataclasses import dataclass

# 原权重；s2 缺省时按剩余权重之和归一化
BASE_WEIGHTS: dict[str, float] = {
    "s1": 0.35,  # 主营产品属于题材主环节 0/1
    "s2": 0.25,  # 题材相关业务营收占比 0-1，可缺省
    "s3": 0.15,  # 市值在题材内百分位 0-1
    "s4": 0.15,  # 机构研报覆盖数在题材内百分位 0-1
    "s5": 0.10,  # 图谱关联跳数：1跳=1，2跳=0.5，3跳及以上=0.2
}
CORE_THRESHOLD = 60.0


@dataclass
class LayerSignals:
    s1: float | None = None
    s2: float | None = None  # None = 缺省（Phase 1 默认状态）
    s3: float | None = None
    s4: float | None = None
    s5: float | None = None

    def get(self, name: str) -> float | None:
        return getattr(self, name)


def layer_score(signals: LayerSignals) -> tuple[float, dict[str, float]]:
    """返回 (layer_score 0-100, 实际使用的归一化权重)。

    s2 为 None 时按剩余权重归一化（s2 缺省时除以 0.75）；s2 有值时按原权重。
    """
    usable = {
        k: w
        for k, w in BASE_WEIGHTS.items()
        if signals.get(k) is not None
    }
    if not usable:
        return 0.0, {}
    total = sum(usable.values())
    norm = {k: w / total for k, w in usable.items()}
    score = 100.0 * sum(signals.get(k) * norm[k] for k in usable)
    return round(score, 2), norm


def layer_for(score: float, manual_override: bool = False, manual_layer: str | None = None) -> str:
    """core / watch。人工校准优先。"""
    if manual_override and manual_layer in ("core", "watch"):
        return manual_layer
    return "core" if score >= CORE_THRESHOLD else "watch"


def layer_reason(
    *,
    segment: str,
    main_product_evidence: str | None = None,
    revenue_share: float | None = None,
    graph_hops: int | None = None,
    concept_hit: bool = False,
    chain_hit: bool = False,
) -> str:
    """生成分层理由。百分比只有在 revenue_share 有来源时才出现。

    只有图谱命中、没有概念命中也没有主营原文支撑时，必须写明“仅图谱命中”。
    """
    parts = [f"所属环节：{segment}"]
    if main_product_evidence:
        parts.append(f"主营证据：{main_product_evidence}")
    if revenue_share is not None:
        parts.append(f"题材相关业务营收占比 {revenue_share:.0%}")
    if graph_hops is not None:
        parts.append(f"图谱关联 {graph_hops} 跳")
    if chain_hit and not concept_hit and not main_product_evidence:
        parts.append("仅图谱命中，无概念板块命中及主营原文支撑")
    return "；".join(parts)


def hop_score(hops: int | None) -> float | None:
    if hops is None:
        return None
    if hops <= 1:
        return 1.0
    if hops == 2:
        return 0.5
    return 0.2
