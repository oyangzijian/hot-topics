"""冻结夹具种子 — 只用于本地开发与测试，不得用于生产冒充实时数据。

来源：
- backend/tests/fixtures/all_concept_boards_20261107.csv（2026-11-07 快照，531 个板块）
- backend/tests/fixtures/scored_26_20261107.csv（修正后：高 17 / 中 6 / 低 3，保留 23 / 待复核 3）

种子内容：
- 题材 humanoid-robot：映射 4 个板块（人形机器人/机器人概念/减速器/机器人执行器，权重均为 1）。
- 另取热度前 20 的板块各建一个单板块题材（slug 为 concept-<板块代码小写>），使首页榜单非空。
  人形机器人题材当天热度只有约 34.24，不在榜首——这是冻结快照的事实。
- 26 家公司全部写入 companies；其中保留的 23 家写入 company_topic_layers
  （置信度高 -> core，中 -> watch）；待复核的 3 家（汉宇集团、南特科技、
  中鼎股份）不写入分层表，待人工复核后再定。
- 夹具里没有汉威科技（300007）和双环传动（002472）；种子会断言这一点，
  一旦出现即失败。

用法：cd backend && python seed_fixture.py [--db sqlite:///./hot_topics.db]
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Base,
    Company,
    CompanyTopicLayer,
    Report,
    Task,
    Topic,
    TopicConceptMap,
    TopicRankSnapshot,
)
from app.services.heat_score import BoardMetrics, compute_heat_scores, topic_heat_score

HERE = Path(__file__).resolve().parent
BOARDS_CSV = HERE / "tests" / "fixtures" / "all_concept_boards_20261107.csv"
SCORED_CSV = HERE / "tests" / "fixtures" / "scored_26_20261107.csv"
SNAPSHOT_AT = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)  # 收盘后快照，UTC

BANNED_NAMES = {"汉威科技", "双环传动"}
BANNED_CODES = {"300007", "002472"}
HUMANOID_MAP = ["人形机器人", "机器人概念", "减速器", "机器人执行器"]


def load_boards() -> list[BoardMetrics]:
    boards: list[BoardMetrics] = []
    with open(BOARDS_CSV, encoding="utf-8-sig") as f:
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
                    leading_code=str(row["领涨股票-代码"]).zfill(6),
                    up_count=up,
                    down_count=down,
                )
            )
    return boards


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="sqlite:///./hot_topics.db")
    args = parser.parse_args()

    boards = load_boards()
    assert len(boards) == 531, f"夹具板块数应为 531，实际 {len(boards)}"
    scored = compute_heat_scores(boards)
    by_name = {s["name"]: s for s in scored}
    board_by_name = {b.name: b for b in boards}

    engine = create_engine(args.db, connect_args={"check_same_thread": False} if args.db.startswith("sqlite") else {})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # 清空种子表（仅本地/测试库）
    for model in (Report, Task, TopicRankSnapshot, CompanyTopicLayer, TopicConceptMap, Company, Topic):
        db.query(model).delete()
    db.commit()

    topics: dict[str, Topic] = {}

    def add_topic(slug: str, name: str, concept_names: list[str]) -> Topic:
        topic = Topic(slug=slug, name=name, description="冻结夹具题材（2026-11-07 快照），非实时数据")
        db.add(topic)
        db.flush()
        topics[slug] = topic
        for cn in concept_names:
            db.add(TopicConceptMap(topic_id=topic.id, concept_name=cn, weight=1))
        return topic

    humanoid = add_topic("humanoid-robot", "人形机器人", HUMANOID_MAP)
    top20 = scored[:20]
    for s in top20:
        add_topic(f"concept-{s['code'].lower()}", s["name"], [s["name"]])

    # 快照：每个题材的热度 = 映射板块加权均值
    snap_rows: list[tuple[Topic, float, BoardMetrics]] = []
    for topic in db.query(Topic).all():
        maps = db.query(TopicConceptMap).filter_by(topic_id=topic.id).all()
        mapped = [by_name[m.concept_name] for m in maps]
        heat = topic_heat_score(mapped, [float(m.weight or 1) for m in maps])
        best = max(mapped, key=lambda x: x["heat_score"])
        best_board = board_by_name[best["name"]]
        snap_rows.append((topic, heat, best_board))
    snap_rows.sort(key=lambda t: -t[1])
    for i, (topic, heat, best_board) in enumerate(snap_rows, start=1):
        db.add(
            TopicRankSnapshot(
                topic_id=topic.id,
                rank=i,
                heat_score=heat,
                change_pct=best_board.change_pct,
                turnover=best_board.turnover_rate,
                main_net_inflow=None,
                limit_up_count=None,  # 冻结快照未跑第二步，无涨停数
                turnover_amount=None,  # 冻结快照未跑第二步，无成交额加总
                up_ratio=best_board.up_ratio,
                leading_company=best_board.leading_company,
                leading_code=best_board.leading_code,
                up_count=best_board.up_count,
                down_count=best_board.down_count,
                snapshot_at=SNAPSHOT_AT,
            )
        )

    # 公司与分层（人形机器人题材）
    with open(SCORED_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 26, f"scored_26 应为 26 行，实际 {len(rows)}"
    assert not any(r["名称"] in BANNED_NAMES or r["代码"] in BANNED_CODES for r in rows), "夹具含禁入公司"
    layered = 0
    for r in rows:
        company = Company(
            code=r["代码"].zfill(6),
            name=r["名称"],
            industry=None,
            main_products=[p for p in (r["产品名称"] or "").split("、") if p][:20] or None,
        )
        db.add(company)
        db.flush()
        if r["结论"] != "保留":
            continue  # 待复核 3 家不进分层表
        layer = "core" if r["置信度"] == "高" else "watch"
        db.add(
            CompanyTopicLayer(
                topic_id=humanoid.id,
                company_id=company.id,
                layer=layer,
                chain_segment=r["环节"],
                layer_score=None,  # 夹具阶段未跑完整分层算法（s2 缺省），不编分数
                layer_reason=f"置信度{r['置信度']}；证据关键词：{r['证据关键词']}；来源：概念板块命中 {r['命中板块数']} 个 + 主营产品原文。{r['备注'] or ''}".strip("；"),
                source_flags={"concept": True, "chain": False},
                manual_override=False,
            )
        )
        layered += 1
    db.commit()

    # 报告种子（Phase 2）：行业报告 1 份 + 定位级公司样本报告 2 份（绿的谐波、兆威机电）。
    # 其余公司只有定位卡片，不生成深度报告。报告经 report_graph 审核（清单外公司即失败）。
    from app.services.report_graph import run_task

    def seed_report(task_type: str, payload: dict) -> None:
        task = Task(task_type=task_type, payload=payload, status="pending", progress=0)
        db.add(task)
        db.commit()
        report = run_task(db, task)
        assert report is not None, f"报告种子生成失败：{payload}（任务错误：{task.error}）"

    seed_report("industry_report", {"report_type": "industry", "topic_slug": "humanoid-robot"})
    seed_report("company_report", {"report_type": "company", "topic_slug": "humanoid-robot", "company_code": "688017"})
    seed_report("company_report", {"report_type": "company", "topic_slug": "humanoid-robot", "company_code": "003021"})
    # 一个已完成的榜单刷新任务（供 /admin/tasks 展示）
    db.add(Task(task_type="rank_refresh", payload={"interval_minutes": 30}, status="done", progress=100))
    db.commit()

    humanoid_heat = next(h for t, h, _ in snap_rows if t.slug == "humanoid-robot")
    humanoid_rank = next(i for i, (t, _, _) in enumerate(snap_rows, start=1) if t.slug == "humanoid-robot")
    print(f"种子完成：题材 {len(snap_rows)} 个，公司 26 家，分层 {layered} 家")
    print(f"人形机器人：热度 {humanoid_heat}，排名 {humanoid_rank}/{len(snap_rows)}（冻结快照，不在榜首）")
    print(f"榜首：{snap_rows[0][0].name} 热度 {snap_rows[0][1]}")


if __name__ == "__main__":
    main()
