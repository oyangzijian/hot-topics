"""抽取评测计分（纯函数）：docs/EXTRACTION_EVAL.md 的计分口径。

指标定义（与文档一致）：
- 漏抽率 miss_rate = 漏抽的 gold 陈述 / gold 总数。漏抽 = gold 里有、抽取里没有。
- 误抽 false_total = 抽出的陈述不在 gold 中（不管校验是否拦截，都算误抽）。
- 校验拦截率 interception_rate = 误抽中被校验器拦截的 / 误抽总数。
- 漏网 escaped = 误抽中校验通过的条数（校验后仍漏网的错误陈述）。
  上线硬门槛：escaped 必须为 0。
- 收入抽取：按产品名归一化匹配，份额绝对误差逐项报告。

匹配口径：陈述按 (kind, 去空白正文) 精确匹配；收入项按去空白/去标点的
产品名匹配。评测集 gold 由人工标注（见评测文档），计分本身不猜、不模糊匹配。
"""
from __future__ import annotations

import re


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _norm_name(s: str) -> str:
    return re.sub(r"[\s\-_/·,，、（）()]", "", s or "")


def _stmt_key(stmt: dict) -> tuple:
    return (stmt.get("kind"), _norm_text(stmt.get("text") or ""))


def score_statements(
    gold: list[dict],
    extracted: list[dict],
    validator_issues: dict[int, list[str]] | None = None,
) -> dict:
    """给一处文档的事实陈述抽取计分。

    validator_issues: {抽取下标: [问题...]}，空列表表示校验通过；
    未传时不计拦截率（interception_rate/escaped 为 None）。
    """
    validator_issues = validator_issues or {}
    gold_keys = {_stmt_key(g) for g in gold}
    ext_keys = [_stmt_key(e) for e in extracted]
    matched = len(set(ext_keys) & gold_keys)
    missed = len(gold_keys - set(ext_keys))
    false_idx = [i for i, k in enumerate(ext_keys) if k not in gold_keys]
    false_total = len(false_idx)
    intercepted = sum(
        1 for i in false_idx if validator_issues.get(i)
    )
    escaped = false_total - intercepted if validator_issues else None
    per_kind: dict[str, dict] = {}
    for kind in sorted({g.get("kind") for g in gold} | {e.get("kind") for e in extracted}):
        gk = {k for k in gold_keys if k[0] == kind}
        ek = {k for k in ext_keys if k[0] == kind}
        per_kind[str(kind)] = {
            "gold": len(gk),
            "extracted": len(ek),
            "matched": len(gk & ek),
            "missed": len(gk - ek),
        }
    return {
        "gold_total": len(gold_keys),
        "extracted_total": len(ext_keys),
        "matched": matched,
        "missed": missed,
        "miss_rate": (missed / len(gold_keys)) if gold_keys else None,
        "false_total": false_total,
        "validator_intercepted": intercepted if validator_issues else None,
        "escaped": escaped,
        "interception_rate": (
            (intercepted / false_total) if false_total else None
        ),
        "per_kind": per_kind,
    }


def score_revenue(
    gold_items: list[dict], extracted_items: list[dict]
) -> dict:
    """给一处年报的分产品收入抽取计分。

    gold/extracted: [{segment, share}]，share 为 0–1 小数。
    匹配按产品名归一化；份额绝对误差逐项列出。
    """
    gold_map = {_norm_name(g.get("segment") or ""): g for g in gold_items}
    ext_map = {_norm_name(e.get("segment") or ""): e for e in extracted_items}
    matched = sorted(set(gold_map) & set(ext_map))
    errors = []
    for name in matched:
        g = float(gold_map[name].get("share") or 0)
        e = float(ext_map[name].get("share") or 0)
        errors.append(
            {"segment": gold_map[name].get("segment"), "gold_share": g,
             "extracted_share": e, "abs_error": abs(g - e)}
        )
    return {
        "gold_total": len(gold_map),
        "extracted_total": len(ext_map),
        "matched": len(matched),
        "missed_segments": [gold_map[n].get("segment") for n in sorted(set(gold_map) - set(ext_map))],
        "extra_segments": [ext_map[n].get("segment") for n in sorted(set(ext_map) - set(gold_map))],
        "max_abs_error": max((e["abs_error"] for e in errors), default=None),
        "share_errors": errors,
    }


def aggregate_statement_scores(scores: list[dict]) -> dict:
    """多份文档的陈述计分汇总（评测报告用）。"""
    gold = sum(s["gold_total"] for s in scores)
    extracted = sum(s["extracted_total"] for s in scores)
    matched = sum(s["matched"] for s in scores)
    missed = sum(s["missed"] for s in scores)
    false_total = sum(s["false_total"] for s in scores)
    intercepted = sum(s["validator_intercepted"] or 0 for s in scores)
    escaped = sum(s["escaped"] or 0 for s in scores)
    return {
        "docs": len(scores),
        "gold_total": gold,
        "extracted_total": extracted,
        "matched": matched,
        "missed": missed,
        "miss_rate": (missed / gold) if gold else None,
        "false_total": false_total,
        "validator_intercepted": intercepted,
        "escaped": escaped,
        "interception_rate": (intercepted / false_total) if false_total else None,
    }
