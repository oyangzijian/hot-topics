"""GET /api/market/overview + 榜单项 main_net_inflow 测试。

夹具数全部取自 2026-11-08 在 mini 上的实测（AKShare 1.20.35，
数据为 2026-11-06 周五收盘，2026-11-08 为周日休市）：
- 上证 3649.18/-1.10%、深证 11175.78/-2.57%、创业板 2465.23/-3.96%
  （stock_zh_index_daily_em，与 stock_market_fund_flow 尾行逐项一致）
- 两市成交额 16577.94 亿（上证 amount 7726.35 亿 + 深证 8851.60 亿），
  较昨日 21179.53 亿 -21.73%
- 涨跌家数 716/4431、涨停 33、跌停 15（stock_market_activity_legu；
  与沪深个股逐家计数完全一致）
- 机器人概念主力净流入 -116.30 亿（stock_concept_fund_flow_hist，
  两次调用一致，超大单+大单=主力净流入）

测试不联网：用 stub 的 akshare 模块注入 AKShareClient。
"""
import json
import os
import sys
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

CST = timezone(timedelta(hours=8))

# --- 2026-11-06 实测夹具 ---
DAILY = {
    "sh000001": pd.DataFrame({
        "date": ["2026-11-04", "2026-11-05", "2026-11-06"],
        "open": [3605.39, 3646.57, 3612.15],
        "close": [3686.17, 3689.91, 3649.18],
        "high": [3686.17, 3701.59, 3660.49],
        "low": [3590.80, 3646.57, 3610.20],
        "volume": [599394361, 571291638, 477042561],
        "amount": [9.532652e11, 9.797118e11, 7.726346e11],
    }),
    "sz399001": pd.DataFrame({
        "date": ["2026-11-04", "2026-11-05", "2026-11-06"],
        "open": [10895.80, 11216.81, 11044.56],
        "close": [11335.69, 11471.09, 11175.78],
        "high": [11362.90, 11613.40, 11303.22],
        "low": [10826.83, 11215.48, 11044.56],
        "volume": [682108330, 672558794, 569400962],
        "amount": [1.084429e12, 1.138241e12, 8.851599e11],
    }),
    "sz399006": pd.DataFrame({
        "date": ["2026-11-04", "2026-11-05", "2026-11-06"],
        "open": [2399.46, 2493.73, 2438.72],
        "close": [2544.73, 2566.80, 2465.23],
        "high": [2559.09, 2625.98, 2506.97],
        "low": [2376.28, 2493.67, 2438.72],
        "volume": [228849025, 231283658, 189023618],
        "amount": [5.493295e11, 5.785642e11, 4.440171e11],
    }),
}
ACTIVITY = pd.DataFrame({
    "item": ["上涨", "涨停", "真实涨停", "st st*涨停", "下跌", "跌停",
             "真实跌停", "st st*跌停", "平盘", "停牌", "活跃度", "统计日期"],
    "value": [716.0, 33.0, 29.0, 1.0, 4431.0, 15.0, 12.0, 0.0, 71.0, 6.0,
              "13.71%", "2026-11-06 15:00:00"],
})
FUND_FLOW = pd.DataFrame({
    "日期": ["2026-11-04", "2026-11-05", "2026-11-06"],
    "主力净流入-净额": [8.138984e09, 3.637475e09, -1.163040e10],
    "超大单净流入-净额": [7.075052e09, 3.544988e09, -5.997770e09],
    "大单净流入-净额": [1.063932e09, 9.248768e07, -5.632631e09],
})

SNAPSHOT = {
    "trade_date": "2026-11-06",
    "fetched_at": "2026-11-08T10:00:00+08:00",
    "stale": False,
    "indices": [
        {"name": "上证指数", "code": "000001", "value": 3649.18, "change_pct": -1.1},
        {"name": "深证成指", "code": "399001", "value": 11175.78, "change_pct": -2.57},
        {"name": "创业板指", "code": "399006", "value": 2465.23, "change_pct": -3.96},
    ],
    "turnover_amount": 16577.94,
    "turnover_change_pct": -21.73,
    "up_count": 716,
    "down_count": 4431,
    "limit_up_count": 33,
    "limit_down_count": 15,
}


def _stub_akshare(monkeypatch, fail_symbols=(), fail_activity=False):
    """往 sys.modules 注入 stub akshare；fail_symbols 里的指数日线抛错。"""
    mod = types.ModuleType("akshare")

    def daily_em(symbol, start_date=None, end_date=None):
        if symbol in fail_symbols:
            raise RuntimeError("mocked akshare failure")
        return DAILY[symbol]

    def activity():
        if fail_activity:
            raise RuntimeError("mocked legu failure")
        return ACTIVITY

    def fund_flow_hist(symbol):
        return FUND_FLOW

    mod.stock_zh_index_daily_em = daily_em
    mod.stock_market_activity_legu = activity
    mod.stock_concept_fund_flow_hist = fund_flow_hist
    monkeypatch.setitem(sys.modules, "akshare", mod)
    return mod


@pytest.fixture()
def client(monkeypatch):
    from app.services.akshare_client import AKShareClient

    _stub_akshare(monkeypatch)
    return AKShareClient(min_interval=0)


def test_fetch_overview_values_match_measured_20261106(client):
    from app.services.market_overview import fetch_market_overview

    out = fetch_market_overview(client, now=datetime(2026, 11, 8, 15, 0, tzinfo=CST))
    assert out["trade_date"] == "2026-11-06"
    assert out["stale"] is False
    by_name = {i["name"]: i for i in out["indices"]}
    assert by_name["上证指数"]["value"] == pytest.approx(3649.18)
    assert by_name["上证指数"]["change_pct"] == pytest.approx(-1.10, abs=0.01)
    assert by_name["深证成指"]["value"] == pytest.approx(11175.78)
    assert by_name["深证成指"]["change_pct"] == pytest.approx(-2.57, abs=0.01)
    assert by_name["创业板指"]["value"] == pytest.approx(2465.23)
    assert by_name["创业板指"]["change_pct"] == pytest.approx(-3.96, abs=0.01)
    assert out["turnover_amount"] == pytest.approx(16577.94, abs=0.02)
    assert out["turnover_change_pct"] == pytest.approx(-21.73, abs=0.02)
    assert out["up_count"] == 716
    assert out["down_count"] == 4431
    assert out["limit_up_count"] == 33
    assert out["limit_down_count"] == 15


def test_fetch_overview_missing_index_nulls_only_its_cells(monkeypatch):
    from app.services.akshare_client import AKShareClient
    from app.services.market_overview import fetch_market_overview

    _stub_akshare(monkeypatch, fail_symbols={"sz399006"})
    c = AKShareClient(min_interval=0)
    out = fetch_market_overview(c, now=datetime(2026, 11, 8, 15, 0, tzinfo=CST))
    by_name = {i["name"]: i for i in out["indices"]}
    assert by_name["创业板指"]["value"] is None
    assert by_name["创业板指"]["change_pct"] is None
    # 其余格子不受影响；成交额仍可算（只依赖上证+深证）
    assert by_name["上证指数"]["value"] == pytest.approx(3649.18)
    assert out["turnover_amount"] == pytest.approx(16577.94, abs=0.02)
    assert out["trade_date"] == "2026-11-06"


def test_fetch_overview_missing_activity_nulls_counts(monkeypatch):
    from app.services.akshare_client import AKShareClient
    from app.services.market_overview import fetch_market_overview

    _stub_akshare(monkeypatch, fail_activity=True)
    c = AKShareClient(min_interval=0)
    out = fetch_market_overview(c, now=datetime(2026, 11, 8, 15, 0, tzinfo=CST))
    assert out["up_count"] is None
    assert out["down_count"] is None
    assert out["limit_up_count"] is None
    assert out["limit_down_count"] is None
    assert out["trade_date"] == "2026-11-06"  # 指数格子仍在


def test_fetch_overview_activity_date_mismatch_nulls_counts(monkeypatch):
    # 乐股统计日期与指数 trade_date 对不上时，家数是旧交易日的数，置 null 不混发
    from app.services.akshare_client import AKShareClient
    from app.services.market_overview import fetch_market_overview

    mod = _stub_akshare(monkeypatch)
    stale_activity = ACTIVITY.copy()
    stale_activity.loc[stale_activity["item"] == "统计日期", "value"] = "2026-11-05 15:00:00"
    mod.stock_market_activity_legu = lambda: stale_activity
    c = AKShareClient(min_interval=0)
    out = fetch_market_overview(c, now=datetime(2026, 11, 8, 15, 0, tzinfo=CST))
    assert out["up_count"] is None
    assert out["down_count"] is None
    assert out["limit_up_count"] is None
    assert out["limit_down_count"] is None
    assert out["trade_date"] == "2026-11-06"  # 指数格子仍在


def test_fetch_concept_fund_flow_yi_and_repeatable(client):
    # 机器人概念 2026-11-06 主力净流入 -116.30 亿；两次调用一致（缓存/接口稳定）
    assert client.fetch_concept_fund_flow("机器人概念") == pytest.approx(-116.30, abs=0.01)
    assert client.fetch_concept_fund_flow("机器人概念") == pytest.approx(-116.30, abs=0.01)


def test_overview_response_stale_only_on_trading_day():
    from app.services.market_overview import overview_response

    snap = dict(SNAPSHOT)
    # 周日：展示周五快照，不标 stale
    assert overview_response(snap, now=datetime(2026, 11, 8, 10, 0, tzinfo=CST))["stale"] is False
    # 周一交易时段：最新交易日是周一，快照还是周五 -> stale
    assert overview_response(snap, now=datetime(2026, 11, 9, 10, 0, tzinfo=CST))["stale"] is True
    # 无快照：全 null + stale
    out = overview_response(None, now=datetime(2026, 11, 8, 10, 0, tzinfo=CST))
    assert out["stale"] is True
    assert out["trade_date"] is None
    assert all(i["value"] is None for i in out["indices"])
    assert out["turnover_amount"] is None


# --- 端点测试：只读快照文件，不调 AKShare ---
@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    snap_path = tmp_path / "market_overview_snapshot.json"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MARKET_OVERVIEW_SNAPSHOT_PATH", str(snap_path))
    import app.db as dbmod
    import importlib

    importlib.reload(dbmod)
    from app.main import app

    with TestClient(app) as c:
        yield c, snap_path


def test_endpoint_returns_snapshot(api_client):
    c, snap_path = api_client
    snap_path.write_text(json.dumps(SNAPSHOT), encoding="utf-8")
    r = c.get("/api/market/overview")
    assert r.status_code == 200
    data = r.json()
    assert data["trade_date"] == "2026-11-06"
    assert data["turnover_amount"] == pytest.approx(16577.94, abs=0.02)
    assert data["up_count"] == 716
    assert data["limit_up_count"] == 33
    assert data["indices"][0] == {"name": "上证指数", "code": "000001",
                                  "value": 3649.18, "change_pct": -1.1}


def test_endpoint_no_snapshot_returns_nulls_not_500(api_client):
    c, _ = api_client
    r = c.get("/api/market/overview")
    assert r.status_code == 200
    data = r.json()
    assert data["stale"] is True
    assert data["trade_date"] is None
    assert all(i["value"] is None for i in data["indices"])
    assert data["turnover_amount"] is None
    assert data["up_count"] is None


def test_endpoint_stale_snapshot_keeps_values(api_client):
    # 旧快照（周五数据）在周一仍返回旧值 + stale=true，不报 500。
    # 用 overview_response 的周一判定覆盖：这里只验端点读快照不断言 stale，
    # stale 的日期逻辑由 test_overview_response_stale_only_on_trading_day 覆盖。
    c, snap_path = api_client
    snap_path.write_text(json.dumps(SNAPSHOT), encoding="utf-8")
    r = c.get("/api/market/overview")
    assert r.status_code == 200
    assert r.json()["indices"][1]["value"] == pytest.approx(11175.78)


# --- 3b：刷新时领涨板块资金流回填 main_net_inflow ---
def test_refresh_fills_main_net_inflow(tmp_path, monkeypatch):
    import app.db as dbmod
    import importlib

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MARKET_OVERVIEW_SNAPSHOT_PATH", str(tmp_path / "snap.json"))
    importlib.reload(dbmod)
    from app.models import Base, Topic, TopicConceptMap, TopicRankSnapshot
    from app.services.heat_score import BoardMetrics
    from app.workers.rank_refresh import refresh_once

    Base.metadata.create_all(bind=dbmod.engine)
    db = dbmod.SessionLocal()
    topic = Topic(slug="humanoid-robot", name="人形机器人")
    db.add(topic)
    db.commit()
    db.add(TopicConceptMap(topic_id=topic.id, concept_name="机器人概念", weight=1))
    db.commit()

    class FakeClient:
        def fetch_concept_boards(self):
            return [BoardMetrics(
                name="机器人概念", code="BK0001", change_pct=-2.0, up_ratio=0.6,
                turnover_rate=3.0, market_cap=1e11, leading_change=5.0,
                leading_company="绿的谐波", leading_code="688017",
                up_count=100, down_count=700)]
        def aggregate_board_metrics(self, code):
            return {}
        def fetch_concept_fund_flow(self, name):
            assert name == "机器人概念"
            return -116.30

    res = refresh_once(db, client=FakeClient())
    assert res["ok"] is True
    snap = db.query(TopicRankSnapshot).filter_by(topic_id=topic.id).first()
    assert snap is not None
    assert float(snap.main_net_inflow) == pytest.approx(-116.30)
    db.close()


def test_refresh_fund_flow_failure_leaves_null(tmp_path, monkeypatch):
    import app.db as dbmod
    import importlib

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MARKET_OVERVIEW_SNAPSHOT_PATH", str(tmp_path / "snap.json"))
    importlib.reload(dbmod)
    from app.models import Base, Topic, TopicConceptMap, TopicRankSnapshot
    from app.services.heat_score import BoardMetrics
    from app.workers.rank_refresh import refresh_once

    Base.metadata.create_all(bind=dbmod.engine)
    db = dbmod.SessionLocal()
    topic = Topic(slug="humanoid-robot", name="人形机器人")
    db.add(topic)
    db.commit()
    db.add(TopicConceptMap(topic_id=topic.id, concept_name="机器人概念", weight=1))
    db.commit()

    class FakeClient:
        def fetch_concept_boards(self):
            return [BoardMetrics(
                name="机器人概念", code="BK0001", change_pct=-2.0, up_ratio=0.6,
                turnover_rate=3.0, market_cap=1e11, leading_change=5.0,
                leading_company="绿的谐波", leading_code="688017",
                up_count=100, down_count=700)]
        def aggregate_board_metrics(self, code):
            return {}
        def fetch_concept_fund_flow(self, name):
            return None  # 资金流拉取失败 -> null，不影响榜单

    res = refresh_once(db, client=FakeClient())
    assert res["ok"] is True
    snap = db.query(TopicRankSnapshot).filter_by(topic_id=topic.id).first()
    assert snap.main_net_inflow is None
    db.close()
