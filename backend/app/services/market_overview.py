"""大盘指数条数据源 — GET /api/market/overview 的拉取与快照逻辑。

数据源（2026-11-08 在 mini 上实测，AKShare 1.20.35，数据为 2026-11-06 周五收盘）：
- 三大指数点位+涨跌幅：stock_zh_index_daily_em（东财指数日线，含 amount 成交额列）。
  stock_zh_index_spot_em 的 268 行里只有上证指数，没有深证成指/创业板指，不可用。
  实测：上证 3649.18/-1.10%、深证 11175.78/-2.57%、创业板 2465.23/-3.96%，
  与 stock_market_fund_flow 尾行收盘价/涨跌幅逐项一致。
- 两市成交额（沪深合计，亿元）：上证指数 amount + 深证成指 amount（同日线接口）。
  2026-11-06：7726.35 + 8851.60 = 16577.94 亿；与沪深个股逐家成交额加总
  16576.01 亿相差 0.01%，口径一致。较昨日：21179.53 亿 -> -21.73%。
- 涨/跌家数、涨停/跌停数：stock_market_activity_legu（乐股）。
  2026-11-06：上涨 716、下跌 4431、涨停 33、跌停 15；上涨/下跌与沪深个股
  逐家计数完全一致，涨停 33 = 涨停池 32 + ST 涨停 1，跌停 15 = 跌停池 15。
  该接口带“统计日期”项（2026-11-06 15:00:00），与指数日线的 trade_date
  对不上时家数置 null，不混发。
- 主力净流入（全市场口径，stock_market_fund_flow）不在本端点返回；
  榜单项的 main_net_inflow 走概念板块口径（见 AKShareClient.fetch_concept_fund_flow）。

失败策略与榜单端点一致：任一格子拉取失败只把该字段置 null，不报 500；
整次拉取失败则保留上一快照文件，端点返回上一快照 + stale=true。
快照以 JSON 文件存（默认与 SQLite 库同目录），不改 DB schema。
热度公式仍是 v2.1，本模块不碰热度分。
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .akshare_client import AKShareClient

CST = timezone(timedelta(hours=8))

# (展示名, 东财指数代码, daily_em symbol)
INDICES = [
    ("上证指数", "000001", "sh000001"),
    ("深证成指", "399001", "sz399001"),
    ("创业板指", "399006", "sz399006"),
]

# 两市成交额 = 上证 amount + 深证 amount（深证成指日线的 amount 即深市成交额）
TURNOVER_SYMBOLS = ("sh000001", "sz399001")


def _round2(x: float | None) -> float | None:
    return round(float(x), 2) if x is not None else None


def _date_str(v) -> str:
    return str(v)[:10]


def default_snapshot_path() -> Path:
    """快照文件默认位置：与 SQLite 库同目录；未配 SQLite 时放当前目录。"""
    env = os.environ.get("MARKET_OVERVIEW_SNAPSHOT_PATH")
    if env:
        return Path(env)
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./hot_topics.db")
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url[len("sqlite:///"):])
        return db_path.parent / "market_overview_snapshot.json"
    return Path("market_overview_snapshot.json")


def fetch_market_overview(client: AKShareClient | None = None,
                          now: datetime | None = None) -> dict:
    """拉取一次大盘指数条数据，返回 overview payload（不含 stale，由端点算）。

    每个格子独立 try/except：失败只置 null。trade_date 取上证日线最新日期；
    上证失败时取其余指数最新日期的最大值；全部失败时为 None。
    """
    client = client or AKShareClient()
    now = (now or datetime.now(CST)).astimezone(CST)
    end = now.strftime("%Y%m%d")
    start = (now - timedelta(days=14)).strftime("%Y%m%d")

    indices: list[dict] = []
    latest_dates: list[str] = []
    amounts: dict[str, tuple[float | None, float | None]] = {}
    for name, code, symbol in INDICES:
        try:
            df = client.fetch_index_daily_em(symbol, start_date=start, end_date=end)
            if df is None or len(df) < 2:
                raise ValueError(f"{symbol} 日线行数不足")
            last = df.iloc[-1]
            prev = df.iloc[-2]
            close = float(last["close"])
            prev_close = float(prev["close"])
            change = (close - prev_close) / prev_close * 100 if prev_close else None
            indices.append({
                "name": name,
                "code": code,
                "value": _round2(close),
                "change_pct": _round2(change),
            })
            latest_dates.append(_date_str(last["date"]))
            amounts[symbol] = (
                float(last["amount"]) if "amount" in df.columns else None,
                float(prev["amount"]) if "amount" in df.columns else None,
            )
        except Exception:
            indices.append({"name": name, "code": code, "value": None, "change_pct": None})

    trade_date = max(latest_dates) if latest_dates else None

    turnover_amount: float | None = None
    turnover_change_pct: float | None = None
    today_total = sum((amounts[s][0] or 0.0) for s in TURNOVER_SYMBOLS
                      if s in amounts and amounts[s][0] is not None)
    today_n = sum(1 for s in TURNOVER_SYMBOLS
                  if s in amounts and amounts[s][0] is not None)
    if today_n == len(TURNOVER_SYMBOLS):
        turnover_amount = _round2(today_total / 1e8)
        prev_total = sum((amounts[s][1] or 0.0) for s in TURNOVER_SYMBOLS
                         if s in amounts and amounts[s][1] is not None)
        prev_n = sum(1 for s in TURNOVER_SYMBOLS
                     if s in amounts and amounts[s][1] is not None)
        if prev_n == len(TURNOVER_SYMBOLS) and prev_total:
            turnover_change_pct = _round2((today_total - prev_total) / prev_total * 100)

    up_count = down_count = limit_up_count = limit_down_count = None
    try:
        df = client.fetch_market_activity()
        activity = {str(r["item"]): r["value"] for _, r in df.iterrows()}
        # 乐股带“统计日期”（如 2026-11-06 15:00:00）：与指数日线的 trade_date
        # 对不上时，家数是旧交易日的数，宁可置 null 也不混着发。
        stat_date = activity.get("统计日期")
        stat_day = str(stat_date)[:10] if stat_date is not None else None
        if stat_day is None or trade_date is None or stat_day == trade_date:
            up_count = int(float(activity["上涨"])) if "上涨" in activity else None
            down_count = int(float(activity["下跌"])) if "下跌" in activity else None
            limit_up_count = int(float(activity["涨停"])) if "涨停" in activity else None
            limit_down_count = int(float(activity["跌停"])) if "跌停" in activity else None
    except Exception:
        pass

    return {
        "trade_date": trade_date,
        "fetched_at": now.isoformat(),
        "stale": False,
        "indices": indices,
        "turnover_amount": turnover_amount,
        "turnover_change_pct": turnover_change_pct,
        "up_count": up_count,
        "down_count": down_count,
        "limit_up_count": limit_up_count,
        "limit_down_count": limit_down_count,
    }


def empty_payload() -> dict:
    """无任何快照时的返回：全部数字字段 null，stale=true，前端显示“未获取”。"""
    return {
        "trade_date": None,
        "fetched_at": None,
        "stale": True,
        "indices": [
            {"name": name, "code": code, "value": None, "change_pct": None}
            for name, code, _ in INDICES
        ],
        "turnover_amount": None,
        "turnover_change_pct": None,
        "up_count": None,
        "down_count": None,
        "limit_up_count": None,
        "limit_down_count": None,
    }


def load_snapshot(path: Path | None = None) -> dict | None:
    path = path or default_snapshot_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "indices" in data:
            return data
    except (OSError, ValueError):
        pass
    return None


def save_snapshot(payload: dict, path: Path | None = None) -> Path:
    path = path or default_snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def overview_response(snapshot: dict | None, now: datetime | None = None) -> dict:
    """端点返回体：有快照返回快照 + 按新鲜度算出的 stale；无快照返回全 null。

    stale 判定复用榜单端点同一规则（monitor.freshness.describe_status）：
    只有交易日该刷新却没刷新才为 True；周末/节假日显示休市，不标过期。
    """
    from ..monitor.freshness import describe_status

    if snapshot is None:
        return empty_payload()
    now = (now or datetime.now(timezone.utc)).astimezone(CST)
    # stale 按 trade_date 判定（不是 fetched_at）：周一早盘拉取仍拿到周五
    # 日线时，fetched_at 是周一、trade_date 是周五，必须标 stale。
    # 无 trade_date（整次拉取一个指数都没拿到）时一律 stale=true。
    trade_date = snapshot.get("trade_date")
    if not trade_date:
        out = dict(snapshot)
        out["stale"] = True
        return out
    try:
        snap_at = datetime.fromisoformat(trade_date + "T15:00:00+08:00")
    except ValueError:
        snap_at = None
    status = describe_status(now, snap_at)
    out = dict(snapshot)
    out["stale"] = status["stale"]
    return out
