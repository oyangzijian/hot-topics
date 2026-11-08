"""新旧热度分对照：冻结快照 2026-11-07 15:00，同一批 21 个题材、两种公式。

旧 = 现站 v2.1 百分位加权（7 指标，缺失归一化）；新 = 包 heat 1.0 z-score 公式。
包公式 6 项指标里冻结快照只有 2 项（pct_change、up_ratio）；其余 4 项按包代码
compute_heat 的处理（m.get(name, 0.0)）记 0.0，全样本同为 0 时 z=0、无贡献。

用法（仓库根目录）：python scripts/heat_compare.py
输出：终端表格 + docs/heat_comparison.md 使用的数据（见 compare.json）。
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import yaml  # noqa: E402

from app.services.heat_index_v2 import compute_heat, missing_inputs, to_package_metrics  # noqa: E402
from app.services.heat_score import BoardMetrics, compute_heat_scores, topic_heat_score  # noqa: E402

CSV = ROOT / "backend" / "tests" / "fixtures" / "all_concept_boards_20261107.csv"
CFG = yaml.safe_load(open(ROOT / "config" / "heat_weights.yaml", encoding="utf-8"))
HUMANOID = ["人形机器人", "机器人概念", "减速器", "机器人执行器"]


def main() -> None:
    boards: list[BoardMetrics] = []
    with open(CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            up, down = int(row["上涨家数"]), int(row["下跌家数"])
            boards.append(BoardMetrics(
                name=row["板块名称"], code=row["板块代码"],
                change_pct=float(row["涨跌幅"]),
                up_ratio=(up / (up + down)) if (up + down) > 0 else None,
                turnover_rate=float(row["换手率"]), market_cap=float(row["总市值"]),
                leading_change=float(row["领涨股票-涨跌幅"]), leading_company=row["领涨股票"],
            ))
    print(f"boards: {len(boards)}; 缺失输入: {missing_inputs(boards)}")
    old = {s["name"]: s["heat_score"] for s in compute_heat_scores(boards)}
    new_board = compute_heat(to_package_metrics(boards), CFG)
    topics = [("人形机器人", HUMANOID)] + [
        (s["name"], [s["name"]]) for s in compute_heat_scores(boards)[:20]
    ]
    rows = []
    for name, maps in topics:
        rows.append({
            "topic": name, "boards": len(maps),
            "old": topic_heat_score([{"heat_score": old[m]} for m in maps]),
            "new": round(sum(new_board[m] for m in maps) / len(maps), 2),
        })
    for i, r in enumerate(sorted(rows, key=lambda x: -x["old"]), 1):
        r["rank_old"] = i
    for i, r in enumerate(sorted(rows, key=lambda x: -x["new"]), 1):
        r["rank_new"] = i
    print(f"{'题材':<12} {'板数':<4} {'旧分':>7} {'旧排名':>6} {'新分':>7} {'新排名':>6} {'排名变化':>8}")
    for r in sorted(rows, key=lambda x: x["rank_old"]):
        print(f"{r['topic']:<12} {r['boards']:<4} {r['old']:>7.2f} {r['rank_old']:>6} "
              f"{r['new']:>7.2f} {r['rank_new']:>6} {r['rank_old'] - r['rank_new']:>+8}")
    print(f"旧分区间: {min(r['old'] for r in rows):.2f}–{max(r['old'] for r in rows):.2f}；"
          f"新分区间: {min(r['new'] for r in rows):.2f}–{max(r['new'] for r in rows):.2f}")
    json.dump(rows, open(ROOT / "docs" / "heat_comparison.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
