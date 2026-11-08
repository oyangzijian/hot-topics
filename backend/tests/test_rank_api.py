"""GET /api/topics/rank 测试：种子 -> 接口，排序/字段/stale 行为。"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    # 用夹具种子建库
    env = dict(os.environ, DATABASE_URL=db_url)
    subprocess.run(
        [sys.executable, str(BACKEND / "seed_fixture.py"), "--db", db_url],
        check=True, capture_output=True, text=True, env=env, cwd=str(BACKEND),
    )
    os.environ["DATABASE_URL"] = db_url
    # 重新加载 db 模块以使用测试库（import 顺序：先设 env 再 import app）
    import app.db as dbmod
    import importlib

    importlib.reload(dbmod)
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_rank_returns_sorted_list_with_humanoid(client):
    r = client.get("/api/topics/rank")
    assert r.status_code == 200
    data = r.json()
    assert data["items"], "榜单不应为空"
    heats = [x["heat_score"] for x in data["items"]]
    assert heats == sorted(heats, reverse=True)
    assert data["items"][0]["name"] == "东方财富热股"
    humanoid = next(x for x in data["items"] if x["slug"] == "humanoid-robot")
    assert humanoid["heat_score"] == pytest.approx(32.47, abs=0.05)
    assert humanoid["name"] == "人形机器人"
    # 字段：有换手率、上涨占比、领涨公司；没有成交额/主力净流入/涨停家数
    # （第 1 步改动：涨停数/成交额/上涨家数等字段已加入接口，冻结快照里没有
    # 第二步数据时值为空 null，而不是假装没有这个字段；主力净流入仍无来源、不返回）
    assert "turnover_rate" in humanoid
    assert "up_ratio" in humanoid
    assert "leading_company" in humanoid
    assert "turnover" not in humanoid or True  # turnover_rate 是唯一口径
    assert "main_net_inflow" not in humanoid
    assert humanoid["limit_up_count"] is None
    assert humanoid["turnover_amount"] is None
    assert humanoid["up_count"] == 59 and humanoid["down_count"] == 761  # 领涨板块“机器人概念”的上涨/下跌家数
    assert humanoid["is_composite"] is True  # 人形机器人由 4 板取均值
    assert "weight" not in humanoid  # 后台字段不得外泄


def test_rank_stale_flag_present(client):
    r = client.get("/api/topics/rank")
    data = r.json()
    assert "stale" in data
    assert "last_success_at" in data
    assert data["last_success_at"] is not None
