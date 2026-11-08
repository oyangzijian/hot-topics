"""大盘指数条刷新 worker — 与榜单刷新同一策略：

- 只在交易时段拉取（周一至周五 9:30-11:30、13:00-15:00，北京时间），
  非交易时段跳过；周日跑到的是周五收盘数据。
- 拉取失败不写快照、不删旧快照，返回 {ok: False, stale: True}，
  端点继续返回上一快照 + stale=true，绝不报 500。
- 本 worker 不开定时任务：由部署方决定触发方式（榜单刷新收尾时
  顺带调用一次，或手动 python -m app.workers.market_refresh --once）。
"""
from __future__ import annotations

from pathlib import Path

from ..services.akshare_client import AKShareClient
from ..services.market_overview import (
    default_snapshot_path,
    fetch_market_overview,
    load_snapshot,
    save_snapshot,
)
from .rank_refresh import is_trading_time


def refresh_market_overview(client: AKShareClient | None = None,
                            snapshot_path: Path | None = None) -> dict:
    """拉取一次并写快照。返回 {ok, stale, trade_date, fetched_at}。

    全部指数都失败（trade_date 为 None）视为整次失败，不覆盖旧快照。
    个别格子失败时仍写快照（失败格子为 null），ok=True。
    """
    path = snapshot_path or default_snapshot_path()
    client = client or AKShareClient()
    try:
        payload = fetch_market_overview(client)
    except Exception as exc:  # noqa: BLE001 - 任何拉取失败都走 stale 路径
        return {"ok": False, "stale": True, "error": str(exc)}
    if payload.get("trade_date") is None:
        return {"ok": False, "stale": True, "error": "指数日线全部拉取失败"}
    save_snapshot(payload, path)
    return {
        "ok": True,
        "stale": False,
        "trade_date": payload["trade_date"],
        "fetched_at": payload["fetched_at"],
    }


def main() -> None:
    """python -m app.workers.market_refresh --once：单次拉取（供手动触发）。"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not args.once:
        parser.print_help()
        return
    if not is_trading_time():
        print("非交易时段，跳过拉取")
        return
    print(refresh_market_overview())


if __name__ == "__main__":
    main()
