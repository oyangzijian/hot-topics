"""pending（待审核）报告可见性测试——硬性要求：只允许管理员看。

公开端对 pending 一律 404（不泄露存在性）：
- GET /api/reports：只返回 done；传 status=pending 也捞不出 pending。
- GET /api/reports/{id}：pending → 404；done → 200。
- GET /api/reports/{id}/download：pending → 404；done → 200。
- GET /api/search：pending 正文关键词搜不到；done 能搜到。
管理端：
- GET /api/admin/reports/{id}：未登录 → 401；登录后 → 200，可读 pending 全文
  （含 evidence.report_html），审核列表页链到 /admin/reports/[id]。
爱发电会员也不能绕过这条：会员解锁只放行已审核通过（done）的内容，
pending 在公开端连 id 都打不开；发布闸门（publish/gate）只对 done 放行。
"""
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
from app.main import app  # noqa: E402
from app.models import Base, Company, Report, Topic  # noqa: E402

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin-password"
ADMIN_HASH = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "pending_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = TestingSession()
    s.add(Topic(id="t-green", slug="concept-bk1024", name="绿色电力"))
    s.add(Company(id="c-1", code="600905", name="三峡能源"))
    s.add(Report(
        id="r-pending", topic_id="t-green", company_id="c-1",
        report_type="company", status="pending",
        content_md="# 三峡能源 PENDINGMARKER123 待审核正文",
        evidence={"report_html": "<h1>PENDINGMARKER123</h1>"},
    ))
    s.add(Report(
        id="r-done", topic_id="t-green", company_id="c-1",
        report_type="company", status="done",
        content_md="# 三峡能源 DONEMARKER456 已审核正文",
        evidence={},
    ))
    s.commit()
    s.close()

    def override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[adminmod.get_db] = override
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", ADMIN_HASH)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(c):
    r = c.post(
        "/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert r.status_code == 200, r.text
    assert "admin_session" in r.headers.get("set-cookie", "")


def test_public_list_only_done(client):
    r = client.get("/api/reports")
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()["items"]]
    assert ids == ["r-done"]
    # 传 status=pending 也捞不出 pending（公开端忽略该参数）
    r = client.get("/api/reports", params={"status": "pending"})
    assert r.status_code == 200
    assert [x["id"] for x in r.json()["items"]] == ["r-done"]


def test_public_detail_pending_404_done_200(client):
    assert client.get("/api/reports/r-pending").status_code == 404
    r = client.get("/api/reports/r-done")
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_public_download_pending_404_done_200(client):
    assert client.get("/api/reports/r-pending/download").status_code == 404
    r = client.get("/api/reports/r-done/download")
    assert r.status_code == 200
    assert "DONEMARKER456" in r.text


def test_public_search_excludes_pending(client):
    r = client.get("/api/search", params={"q": "PENDINGMARKER123"})
    assert r.status_code == 200
    assert r.json()["reports"] == []
    r = client.get("/api/search", params={"q": "DONEMARKER456"})
    assert r.status_code == 200
    assert [x["id"] for x in r.json()["reports"]] == ["r-done"]


def test_admin_detail_pending_requires_login(client):
    assert client.get("/api/admin/reports/r-pending").status_code == 401
    _login(client)
    r = client.get("/api/admin/reports/r-pending")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "pending"
    assert "PENDINGMARKER123" in d["evidence"]["report_html"]
    # 管理列表能看到 pending（审核入口），公开列表看不到
    ids = [x["id"] for x in client.get("/api/admin/reports").json()["items"]]
    assert set(ids) == {"r-pending", "r-done"}
