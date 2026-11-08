"""入库端点测试：POST /api/admin/ingest/report（stockreport 推送）。

- 鉴权：独立 Bearer INGEST_TOKEN，无 token / 错 token → 401。
- 题材按 Topic.name 精确匹配，匹配不到 → 400，不自动新建题材。
- 按 (company, topic, report_type=company) upsert：新建公司 + 报告 status=pending，
  重推同一家不产生重复报告；report_html 进 evidence，content_md 只留占位句。
- 管理列表不回传 report_html（只给 has_html_report），详情才返回完整 evidence。
"""
import os
import sys
from pathlib import Path

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import app.routers.admin as adminmod  # noqa: E402
from app.db import get_db as _real_get_db  # noqa: E402,F401  (import 占位，保证模块已加载)
from app.main import app  # noqa: E402
from app.models import Base, Company, Report, Topic  # noqa: E402

TOKEN = "test-ingest-token-abc"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin-test-pass"
ADMIN_HASH = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()

BODY = {
    "code": "600905",
    "name": "三峡能源",
    "source": "stockreport",
    "topic": "绿色电力",
    "trade_date": "2026-11-06",
    "generated_at": "2026-11-08T16:30:00+08:00",
    "summary": {"label": "2026Q3", "np": 1.1, "gm": 0.3008},
    "report_html": "<!doctype html><html><body><h1>三峡能源</h1></body></html>",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "ingest_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = TestingSession()
    s.add(Topic(id="t-green", slug="concept-bk1024", name="绿色电力"))
    s.add(Topic(id="t-topcon", slug="concept-bk1097", name="TOPCon电池"))
    s.commit()
    s.close()

    def override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    # 端点实际用的 get_db 对象是 admin 路由模块里 import 进来的那个，
    # 用它做 override key，不受其他测试文件 reload app.db 的影响。
    app.dependency_overrides[adminmod.get_db] = override
    monkeypatch.setenv("INGEST_TOKEN", TOKEN)
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", ADMIN_HASH)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    with TestClient(app) as c:
        yield c, TestingSession
    app.dependency_overrides.clear()


def _auth(c):
    return {"Authorization": f"Bearer {TOKEN}"}


def test_ingest_no_token_401(client):
    c, _ = client
    assert c.post("/api/admin/ingest/report", json=BODY).status_code == 401


def test_ingest_wrong_token_401(client):
    c, _ = client
    r = c.post(
        "/api/admin/ingest/report",
        json=BODY,
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401


def test_ingest_unknown_topic_400(client):
    c, _ = client
    body = dict(BODY, topic="不存在的题材")
    r = c.post("/api/admin/ingest/report", json=body, headers=_auth(c))
    assert r.status_code == 400
    assert "不存在的题材" in r.json()["detail"]


def test_ingest_creates_pending_report_and_upserts(client):
    c, Session = client
    r = c.post("/api/admin/ingest/report", json=BODY, headers=_auth(c))
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and d["created"] is True and d["status"] == "pending"
    report_id = d["report_id"]

    s = Session()
    company = s.query(Company).filter_by(code="600905").first()
    assert company is not None and company.name == "三峡能源"
    assert company.industry is None
    reports = s.query(Report).filter_by(company_id=company.id).all()
    assert len(reports) == 1
    rep = reports[0]
    assert rep.id == report_id
    assert rep.report_type == "company" and rep.status == "pending"
    assert rep.content_md == "详见 HTML 报告。"
    assert rep.evidence["report_html"] == BODY["report_html"]
    assert rep.evidence["stockreport_summary"] == BODY["summary"]
    assert rep.evidence["trade_date"] == "2026-11-06"
    s.close()

    # 重推同一家：不产生重复报告，同一 id，仍为 pending。
    r2 = c.post("/api/admin/ingest/report", json=BODY, headers=_auth(c))
    assert r2.status_code == 200
    assert r2.json()["created"] is False
    assert r2.json()["report_id"] == report_id
    s = Session()
    assert s.query(Report).count() == 1
    s.close()

    # pending 只允许管理员看：公开详情/下载/列表一律不暴露（404 或空列表，
    # 不泄露存在性）；管理员详情 200，返回完整 evidence（含 report_html）。
    # 公司页在未审核前仍不显示（只认 done）。
    assert c.get(f"/api/reports/{report_id}").status_code == 404
    assert c.get(f"/api/reports/{report_id}/download").status_code == 404
    assert c.get("/api/reports").json()["items"] == []
    login = c.post(
        "/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    r3 = c.get(f"/api/admin/reports/{report_id}")
    assert r3.status_code == 200
    assert r3.json()["evidence"]["report_html"] == BODY["report_html"]
    assert c.get("/api/companies/600905").json()["report"] is None


def test_ingest_missing_html_422(client):
    c, _ = client
    body = {k: v for k, v in BODY.items() if k != "report_html"}
    assert c.post("/api/admin/ingest/report", json=body, headers=_auth(c)).status_code == 422


def test_ingest_dedup_by_code_and_trade_date_across_topics(client):
    """upsert 键是 (code, trade_date)：同一家同一交易日换题材重推不产生新行，
    题材只累积进 evidence.topics；两个题材的公开列表都能筛到这份报告。"""
    c, Session = client
    r1 = c.post("/api/admin/ingest/report", json=BODY, headers=_auth(c))
    assert r1.status_code == 200 and r1.json()["created"] is True
    rid = r1.json()["report_id"]

    body2 = dict(BODY, topic="TOPCon电池")
    r2 = c.post("/api/admin/ingest/report", json=body2, headers=_auth(c))
    assert r2.status_code == 200
    assert r2.json()["created"] is False
    assert r2.json()["report_id"] == rid
    assert set(r2.json()["topics"]) == {"绿色电力", "TOPCon电池"}

    s = Session()
    assert s.query(Report).count() == 1
    rep = s.query(Report).filter_by(id=rid).first()
    assert {t["slug"] for t in rep.evidence["topics"]} == {"concept-bk1024", "concept-bk1097"}
    # topic_id 保持首次推送的题材不变
    assert rep.topic_id == "t-green"
    s.close()

    # pending 时公开列表筛不到（两个题材都为空，不泄露存在性）；
    # 管理员审核通过后，两个题材的公开列表都能筛到。
    for slug in ("concept-bk1024", "concept-bk1097"):
        items = c.get("/api/reports", params={"topic_slug": slug}).json()["items"]
        assert items == []
    login = c.post(
        "/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    rv = c.post(f"/api/admin/reports/{rid}/review", json={"action": "approve"})
    assert rv.status_code == 200 and rv.json()["status"] == "done"
    for slug in ("concept-bk1024", "concept-bk1097"):
        items = c.get("/api/reports", params={"topic_slug": slug}).json()["items"]
        assert [i["id"] for i in items] == [rid]


def test_admin_list_needs_attention(client):
    c, _ = client
    # 干净推送：不高亮
    c.post("/api/admin/ingest/report", json=BODY, headers=_auth(c))
    login = c.post(
        "/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200

    def _item():
        r = c.get("/api/admin/reports")
        assert r.status_code == 200
        return [i for i in r.json()["items"] if i.get("company") == "三峡能源"][0]

    assert _item()["needs_attention"] is False

    # summary.critical_fail > 0 → 高亮
    bad = dict(BODY, summary={"label": "2026Q3", "np": 1.1, "gm": 0.3, "critical_fail": 2})
    c.post("/api/admin/ingest/report", json=bad, headers=_auth(c))
    assert _item()["needs_attention"] is True

    # 报告顶部红色横幅（即使 summary 里 critical_fail 回 0）→ 也高亮
    banner = dict(
        BODY,
        summary={"label": "2026Q3", "np": 1.1, "gm": 0.3, "critical_fail": 0},
        report_html="<html><body><div>⚠ 关键校验未通过（1 项），请勿直接使用本报告</div></body></html>",
    )
    c.post("/api/admin/ingest/report", json=banner, headers=_auth(c))
    assert _item()["needs_attention"] is True


def test_admin_list_strips_report_html(client):
    c, _ = client
    c.post("/api/admin/ingest/report", json=BODY, headers=_auth(c))
    login = c.post(
        "/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    r = c.get("/api/admin/reports")
    assert r.status_code == 200
    item = [i for i in r.json()["items"] if i.get("company") == "三峡能源"][0]
    assert item["status"] == "pending"
    assert item["has_html_report"] is True
    assert "report_html" not in item["evidence"]
    assert item["evidence"]["stockreport_summary"] == BODY["summary"]
