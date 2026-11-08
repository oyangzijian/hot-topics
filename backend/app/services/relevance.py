"""公司与题材的关联度得分—— 直接采用 astock-data 包 astock/compute/relevance_score.py，未改逻辑。
公式与分档全部来自 config/score_rules.yaml。状态：已实现，未接线（现站分层仍走
layering.py 的主营核验规则）；接线需先把 revenue_share / disclosure / patent 三项
输入补齐，见 docs/REDESIGN.md。
"""
def _cap(x: float, full_at: float) -> float:
    return max(0.0, min(1.0, x / full_at)) * 100 if full_at else 0.0


def score_company(f: dict, rules: dict) -> dict:
    """f: revenue_share(0-1 或 None), disclosure_count, chain_role, patent_count"""
    caps, w = rules["caps"], rules["weights"]
    flags = []
    rs = f.get("revenue_share")
    if rs is None:
        flags.append("revenue_share_missing")
        rs = 0.0
    comp = {
        "revenue_share": _cap(rs, caps["revenue_share_full_at"]),
        "disclosure": _cap(f.get("disclosure_count", 0), caps["disclosure_full_at"]),
        "chain_position": float(rules["chain_role_score"].get(f.get("chain_role"), 0)),
        "patent": _cap(f.get("patent_count", 0), caps["patent_full_at"]),
    }
    total = round(sum(comp[k] * w[k] for k in comp), 1)
    t = rules["tiers"]
    tier = "high" if total >= t["high"] else "mid" if total >= t["mid"] else "low"
    return {"total": total, "tier": tier, "components": comp, "flags": flags,
            "rule_version": rules["version"]}
