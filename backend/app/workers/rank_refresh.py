"""榜单刷新 worker — 修正版规格 v2 §5.1。

- 交易时段（周一至周五 9:30-11:30、13:00-15:00，北京时间）每 30 分钟一次（用户定），
  非交易时段不拉取。
- 失败指数退避：1、2、4、8、16 分钟（上限 16 分钟）。
- 失败时保留上一快照：refresh_once() 返回 (ok=False, stale=True)，
  调用方/接口继续返回上一快照 + stale=true + last_success_at，绝不报 500。
"""
from __future__ import annotations

import os
from datetime import datetime, time as dtime, timedelta, timezone

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Base, Topic, TopicConceptMap, TopicRankSnapshot
from ..services.akshare_client import AKShareClient
from ..services.heat_score import compute_heat_scores, topic_heat_score

REFRESH_INTERVAL_MINUTES = int(os.environ.get("RANK_REFRESH_INTERVAL_MINUTES", "30"))
TOP_N_ENRICH = 20  # 第二步只对初榜前 20 个板块补成分股聚合
BACKOFF_MINUTES = [1, 2, 4, 8, 16]

CST = timezone(timedelta(hours=8))
TRADING_WINDOWS = [(dtime(9, 30), dtime(11, 30)), (dtime(13, 0), dtime(15, 0))]


def is_trading_time(now: datetime | None = None) -> bool:
    """是否在 A 股交易时段内。周末直接 False。"""
    now = (now or datetime.now(CST)).astimezone(CST)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return any(start <= t <= end for start, end in TRADING_WINDOWS)


def backoff_minutes(failures: int) -> int:
    """连续失败次数 -> 下次重试等待分钟数，上限 16。"""
    if failures <= 0:
        return 0
    return BACKOFF_MINUTES[min(failures - 1, len(BACKOFF_MINUTES) - 1)]


def refresh_once(db: Session, client: AKShareClient | None = None) -> dict:
    """拉取一次并写入快照。返回 {ok, stale, last_success_at, updated_topics}。

    失败时不写库、不删旧快照，ok=False, stale=True。
    """
    client = client or AKShareClient()
    try:
        boards = client.fetch_concept_boards()
    except Exception as exc:  # noqa: BLE001 - 任何拉取失败都走 stale 路径
        return {"ok": False, "stale": True, "error": str(exc), "updated_topics": 0}

    # 第二步：只对初榜前 TOP_N_ENRICH 个板块补成分股聚合，失败则保持第一步数值
    scored = compute_heat_scores(boards)
    if hasattr(client, "aggregate_board_metrics"):
        by_code = {b.code: b for b in boards}
        for entry in scored[:TOP_N_ENRICH]:
            agg = client.aggregate_board_metrics(entry["code"])
            board = by_code.get(entry["code"])
            if board is None:
                continue
            if "turnover_amount" in agg:
                board.turnover_amount = agg["turnover_amount"]
            if "limit_up_count" in agg:
                board.limit_up_count = agg["limit_up_count"]
        scored = compute_heat_scores(boards)
    by_name = {s["name"]: s for s in scored}
    now = datetime.now(CST)
    updated = 0
    fund_flows: dict[str, float | None] = {}  # 概念名 -> 主力净流入（亿元），同刷新内去重
    topics = db.query(Topic).all()
    for topic in topics:
        mappings = db.query(TopicConceptMap).filter_by(topic_id=topic.id).all()
        mapped = [by_name[m.concept_name] for m in mappings if m.concept_name in by_name]
        if not mapped:
            continue
        weights = [float(m.weight or 1) for m in mappings if m.concept_name in by_name]
        heat = topic_heat_score(mapped, weights)
        # 展示指标取映射板块的加权均值；领涨公司取映射板块中热度最高者的领涨股。
        board_by_name = {b.name: b for b in boards}
        total_w = sum(weights) or 1.0

        def wmean(attr: str) -> float | None:
            vals = [
                (getattr(board_by_name[s["name"]], attr), w)
                for s, w in zip(mapped, weights)
                if getattr(board_by_name[s["name"]], attr) is not None
            ]
            if not vals:
                return None
            return sum(v * w for v, w in vals) / sum(w for _, w in vals)

        best = max(mapped, key=lambda s: s["heat_score"])
        best_board = board_by_name[best["name"]]
        # 主力净流入（亿元，领涨板块口径）：概念板块资金流，非行业口径。
        # 同一刷新内每个概念只拉一次；失败置 null，不影响榜单写入。
        # 热度公式仍是 v2.1，该指标只展示、不参与热度分。
        if best_board.name not in fund_flows:
            fetch_ff = getattr(client, "fetch_concept_fund_flow", None)
            fund_flows[best_board.name] = fetch_ff(best_board.name) if fetch_ff else None
        db.add(
            TopicRankSnapshot(
                topic_id=topic.id,
                rank=0,  # 排名在全部题材算完后统一回填
                heat_score=heat,
                change_pct=wmean("change_pct"),
                turnover=wmean("turnover_rate"),  # v2：存换手率(%)，不是成交额
                main_net_inflow=fund_flows[best_board.name],  # 亿元，领涨板块口径；无数据为 NULL
                # 上涨/下跌家数、涨停数、成交额、领涨代码取映射板块中热度最高者（领涨板块），
                # 不是多板块加总；组合题材的这些数是领涨板块口径，界面不得写成全题材口径。
                limit_up_count=int(best_board.limit_up_count)
                if best_board.limit_up_count is not None
                else None,
                up_ratio=wmean("up_ratio"),
                leading_company=best_board.leading_company,
                leading_code=best_board.leading_code,
                up_count=best_board.up_count,
                down_count=best_board.down_count,
                turnover_amount=best_board.turnover_amount,
                snapshot_at=now,
            )
        )
        updated += 1
    # 回填排名（按 heat 降序）
    snaps = (
        db.query(TopicRankSnapshot)
        .filter(TopicRankSnapshot.snapshot_at == now)
        .order_by(TopicRankSnapshot.heat_score.desc())
        .all()
    )
    for i, snap in enumerate(snaps, start=1):
        snap.rank = i
    db.commit()
    # 顺带刷新大盘指数条快照（同一 30 分钟刷新路径）；指数条失败绝不
    # 影响榜单写入，失败时端点继续返回上一快照 + stale=true。
    try:
        from .market_refresh import refresh_market_overview

        refresh_market_overview(client=client)
    except Exception:
        pass
    return {"ok": True, "stale": False, "last_success_at": now.isoformat(), "updated_topics": updated}


def main() -> None:
    """python -m app.workers.rank_refresh --once：单次拉取（供 cron / 手动触发）。"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not is_trading_time():
        print("非交易时段，跳过拉取（v2 §5.1）")
        return
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=db.get_bind())
        print(refresh_once(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
