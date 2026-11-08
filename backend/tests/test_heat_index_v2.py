"""热度公式 v1.0（z-score）测试：逻辑与包一致 + 冻结快照对照。

对照值来自 scripts/heat_compare.py 在同一份夹具上的计算结果，
旧分（v2.1）与新分（包公式）都以 2026-11-07 15:00 冻结快照为准。
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent

from app.services.heat_index_v2 import compute_heat, missing_inputs, to_package_metrics
from app.services.heat_score import BoardMetrics, compute_heat_scores, topic_heat_score

CFG = yaml.safe_load(open("/tmp/astock/astock-data/config/heat_weights.yaml", encoding="utf-8"))
FIXTURE = HERE / "fixtures" / "all_concept_boards_20261107.csv"


def _load_boards() -> list[BoardMetrics]:
    boards = []
    with open(FIXTURE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            up, down = int(row["上涨家数"]), int(row["下跌家数"])
            boards.append(BoardMetrics(
                name=row["板块名称"], code=row["板块代码"],
                change_pct=float(row["涨跌幅"]),
                up_ratio=(up / (up + down)) if (up + down) > 0 else None,
                turnover_rate=float(row["换手率"]), market_cap=float(row["总市值"]),
                leading_change=float(row["领涨股票-涨跌幅"]), leading_company=row["领涨股票"],
            ))
    return boards


def test_hotter_theme_ranks_higher():
    keys = CFG["weights"].keys()
    m = {"A": {k: 10.0 for k in keys}, "B": {k: 5.0 for k in keys}, "C": {k: 1.0 for k in keys}}
    h = compute_heat(m, CFG)
    assert h["A"] > h["B"] > h["C"]
    assert all(0 <= v <= 100 for v in h.values())


def test_identical_themes_get_50():
    m = {"A": {k: 3.0 for k in CFG["weights"]}, "B": {k: 3.0 for k in CFG["weights"]}}
    assert compute_heat(m, CFG) == {"A": 50.0, "B": 50.0}


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        compute_heat({"A": {}}, {"weights": {"x": 0.5}})


def test_frozen_snapshot_missing_inputs():
    boards = _load_boards()
    assert missing_inputs(boards) == [
        "limit_up_count", "turnover_share", "net_inflow", "news_heat",
    ]


def test_frozen_snapshot_comparison():
    """冻结快照对照（见 docs/heat_comparison.md）：旧公式榜首 88.73，新公式下
    昨日打二板以上表现冲到 100.0（第 1），东方财富热股掉到 58.9（第 19）；
    人形机器人新旧都是第 21（新 41.77 / 旧 32.47）——换公式不解决均值行口径问题。"""
    boards = _load_boards()
    old = {s["name"]: s["heat_score"] for s in compute_heat_scores(boards)}
    new_board = compute_heat(to_package_metrics(boards), CFG)
    humanoid = ["人形机器人", "机器人概念", "减速器", "机器人执行器"]
    old_h = topic_heat_score([{"heat_score": old[m]} for m in humanoid])
    new_h = round(sum(new_board[m] for m in humanoid) / 4, 2)
    assert old_h == 32.47 and new_h == 41.77
    assert new_board["昨日打二板以上表现"] == 100.0
    assert new_board["东方财富热股"] == 58.9
    assert old["东方财富热股"] == 88.73
