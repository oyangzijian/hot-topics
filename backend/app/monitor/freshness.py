"""数据新鲜度检查—— 直接采用 astock-data 包 astock/monitor/freshness.py，未改逻辑（纯函数）。
下方 describe_status() 是本站的诚实标注：交易日与抓取时间分开写，周末显示休市，
只有交易日刷新失败才标 stale。
"""
from datetime import datetime, time, timedelta, timezone

CN = timezone(timedelta(hours=8))


def is_trading_time(now: datetime, holidays: set[str] | None = None) -> bool:
    now = now.astimezone(CN)
    if now.weekday() >= 5 or (holidays and now.strftime("%Y-%m-%d") in holidays):
        return False
    t = now.time()
    return time(9, 30) <= t <= time(11, 30) or time(13, 0) <= t <= time(15, 0)


def check(now: datetime, last_updated: dict[str, datetime], cfg: dict,
          holidays: set[str] | None = None) -> list[dict]:
    alerts = []
    for name, rule in cfg["freshness"].items():
        if rule.get("trading_only") and not is_trading_time(now, holidays):
            continue
        last = last_updated.get(name)
        age = None if last is None else (now - last).total_seconds()
        if age is None or age > rule["max_age"]:
            alerts.append({"dataset": name, "age_seconds": age, "max_age": rule["max_age"]})
    return alerts


def describe_status(now: datetime, snapshot_at: datetime | None,
                    holidays: set[str] | None = None) -> dict:
    """诚实标注：返回前端状态条要显示的三样东西。

    - trade_date：数据所属交易日（快照日期；无快照为 None）。
    - fetched_at：抓取时间（快照时间，ISO +08:00）。
    - market_status：trading（交易时段）/ closed（已收盘）/ market_closed（休市：周末或节假日）。
    - stale：只有“交易日该刷新却没刷新”才为 True；周末/节假日永不标 stale。
    - stale_reason：stale 为 True 时写清原因，否则 None。
    """
    now_cn = now.astimezone(CN)
    snap_cn = snapshot_at.astimezone(CN) if snapshot_at is not None else None
    if is_trading_time(now, holidays):
        market_status = "trading"
    elif now_cn.weekday() < 5 and not (holidays and now_cn.strftime("%Y-%m-%d") in holidays) \
            and (time(11, 30) <= now_cn.time() <= time(13, 0) or now_cn.time() >= time(15, 0)):
        market_status = "closed"
    else:
        market_status = "market_closed"
    trade_date = snap_cn.date().isoformat() if snap_cn else None
    stale, reason = False, None
    if snap_cn is None:
        stale, reason = True, "暂无快照"
    elif market_status in ("trading", "closed"):
        # 交易日：快照所属日期应为最近一个交易日；否则视为刷新失败
        d = now_cn.date()
        while d.weekday() >= 5 or (holidays and d.isoformat() in holidays):
            d -= timedelta(days=1)
        if snap_cn.date() < d:
            stale = True
            reason = f"最近交易日（{d.isoformat()}）刷新失败，展示上一快照"
    return {"trade_date": trade_date,
            "fetched_at": snap_cn.isoformat() if snap_cn else None,
            "market_status": market_status, "stale": stale, "stale_reason": reason}
