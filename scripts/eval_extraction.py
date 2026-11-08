#!/usr/bin/env python3
"""抽取评测跑分脚本（docs/EXTRACTION_EVAL.md 的执行入口）。

用法：
    python scripts/eval_extraction.py --manifest docs/eval_set/manifest.json \\
        --report-out /tmp/eval_report.json

manifest 格式：{"docs": [{"id": ..., "kind": "statements" | "revenue",
"gold": "gold 路径", "output": "抽取输出路径",
"validator_issues": {"1": ["number_not_in_source:..."]}}]}
- kind=statements：gold/output 是 {"statements": [...]}，validator_issues 的 key
  是抽取下标（字符串），值是校验器返回的问题列表。
- kind=revenue：gold/output 是 {"items": [{"segment": ..., "share": ...}]}。
- muse provider：抽取由助手执行，输出 JSON 先落盘，再由本脚本计分；
  anthropic provider：先用 llm_client 跑出输出文件，再计分。本脚本只计分，
  不直接调模型、不入库。

门槛（建议值，需用户批准，见评测文档 §5）：漏网 escaped 必须为 0；
漏抽率 ≤ 20%；收入份额最大绝对误差 ≤ 0.01。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.extract.eval_scorer import (  # noqa: E402
    aggregate_statement_scores,
    score_revenue,
    score_statements,
)

# 建议门槛（需用户批准后才算正式门槛；未批之前报告只呈现数字与“建议”结论）。
MISS_RATE_LIMIT = 0.20
REVENUE_MAX_ABS_ERROR = 0.01


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--report-out", default=None)
    args = ap.parse_args()

    manifest = _load(args.manifest)
    stmt_scores, revenue_scores, per_doc = [], [], []
    for entry in manifest["docs"]:
        gold = _load(entry["gold"])
        output = _load(entry["output"])
        if entry["kind"] == "statements":
            issues = {int(k): v for k, v in (entry.get("validator_issues") or {}).items()}
            s = score_statements(gold.get("statements", []),
                                 output.get("statements", []), issues)
            stmt_scores.append(s)
            per_doc.append({"id": entry["id"], "kind": "statements", **s})
        elif entry["kind"] == "revenue":
            s = score_revenue(gold.get("items", []), output.get("items", []))
            revenue_scores.append(s)
            per_doc.append({"id": entry["id"], "kind": "revenue", **s})
        else:
            raise ValueError(f"未知的评测 kind：{entry['kind']!r}")

    agg = aggregate_statement_scores(stmt_scores) if stmt_scores else None
    rev_max_err = max(
        (s["max_abs_error"] for s in revenue_scores if s["max_abs_error"] is not None),
        default=None,
    )
    escaped = agg["escaped"] if agg else 0
    miss_rate = agg["miss_rate"] if agg else None
    verdict = {
        "escaped_is_zero": escaped == 0,
        "miss_rate_ok": (miss_rate is not None and miss_rate <= MISS_RATE_LIMIT),
        "revenue_error_ok": (
            rev_max_err is None or rev_max_err <= REVENUE_MAX_ABS_ERROR
        ),
    }
    verdict["pass"] = all(verdict.values())
    report = {
        "manifest_docs": len(manifest["docs"]),
        "statement_docs": len(stmt_scores),
        "revenue_docs": len(revenue_scores),
        "aggregate": agg,
        "revenue_max_abs_error": rev_max_err,
        "thresholds_proposed": {
            "miss_rate_limit": MISS_RATE_LIMIT,
            "revenue_max_abs_error": REVENUE_MAX_ABS_ERROR,
            "escaped_must_be_zero": True,
            "note": "建议值，需用户批准后才算正式门槛",
        },
        "verdict": verdict,
        "per_doc": per_doc,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report_out:
        Path(args.report_out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
