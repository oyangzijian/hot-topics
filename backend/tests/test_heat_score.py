"""热度分测试 — 修正版规格 v2 §11 验收 #2（冻结快照确定性测试）。

v2.1 两步走：冻结夹具只有概念列表一步的指标（成分股成交额/涨停数缺失），
权重按可用指标归一化（分母 0.70）。预期值已按新权重重算。


夹具：tests/fixtures/all_concept_boards_20261107.csv（2026-11-07，531 个板块）。
预期值由原型实算得出，不是拍脑袋的数：
- 第 1 名：东方财富热股，heat ≈ 88.42
- 人形机器人题材（4 板块均值）≈ 32.47，当天不在榜首
- 单板块：人形机器人 34.09 / 机器人概念 37.94 / 减速器 35.16 / 机器人执行器 22.69
"""
import csv
from pathlib import Path

import pytest

from app.services.heat_score import BoardMetrics, compute_heat_scores, topic_heat_score

FIXTURE = Path(__file__).parent / "fixtures" / "all_concept_boards_20261107.csv"


def load_boards() -> list[BoardMetrics]:
    boards = []
    with open(FIXTURE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            up, down = int(row["上涨家数"]), int(row["下跌家数"])
            boards.append(
                BoardMetrics(
                    name=row["板块名称"],
                    code=row["板块代码"],
                    change_pct=float(row["涨跌幅"]),
                    up_ratio=(up / (up + down)) if (up + down) > 0 else None,
                    turnover_rate=float(row["换手率"]),
                    market_cap=float(row["总市值"]),
                    leading_change=float(row["领涨股票-涨跌幅"]),
                    leading_company=row["领涨股票"],
                )
            )
    return boards


def test_fixture_has_531_boards():
    assert len(load_boards()) == 531


def test_top_board_is_dongfangcaifortune_hot():
    scored = compute_heat_scores(load_boards())
    assert scored[0]["name"] == "东方财富热股"
    assert scored[0]["heat_score"] == pytest.approx(88.73, abs=0.05)
    # 降序
    heats = [s["heat_score"] for s in scored]
    assert heats == sorted(heats, reverse=True)
    assert all(0 <= h <= 100 for h in heats)


def test_humanoid_single_boards():
    scored = compute_heat_scores(load_boards())
    by_name = {s["name"]: s["heat_score"] for s in scored}
    assert by_name["人形机器人"] == pytest.approx(34.09, abs=0.05)
    assert by_name["机器人概念"] == pytest.approx(37.94, abs=0.05)
    assert by_name["减速器"] == pytest.approx(35.16, abs=0.05)
    assert by_name["机器人执行器"] == pytest.approx(22.69, abs=0.05)


def test_humanoid_topic_heat_is_mean_of_four_mapped_boards():
    scored = compute_heat_scores(load_boards())
    by_name = {s["name"]: s for s in scored}
    mapped = [by_name[n] for n in ["人形机器人", "机器人概念", "减速器", "机器人执行器"]]
    assert topic_heat_score(mapped) == pytest.approx(32.47, abs=0.05)
    # 当天人形机器人不在榜首（验收 #2 不再断言它是第 1）
    assert topic_heat_score(mapped) < scored[0]["heat_score"]


def test_up_ratio_for_humanoid_board():
    boards = load_boards()
    humanoid = next(b for b in boards if b.name == "人形机器人")
    assert humanoid.up_ratio == pytest.approx(18 / (18 + 314), abs=1e-6)


def test_deterministic_twice():
    boards = load_boards()
    assert compute_heat_scores(boards) == compute_heat_scores(load_boards())


def test_missing_metric_renormalises_and_stays_in_range():
    boards = load_boards()
    for b in boards:
        b.up_ratio = None  # 模拟上涨/下跌家数缺失
    scored = compute_heat_scores(boards)
    assert all(0 <= s["heat_score"] <= 100 for s in scored)
    # 权重归一化后仍有区分度
    assert scored[0]["heat_score"] != scored[-1]["heat_score"]


def test_empty_input():
    assert compute_heat_scores([]) == []
    assert topic_heat_score([]) == 0.0
