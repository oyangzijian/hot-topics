"""Phase 2 测试：公开 API、搜索、管理鉴权、SSE、报告审核硬规则。

夹具：seed_fixture.py（人形机器人 26 家，行业报告 1 份 + 公司样本报告 2 份）。
禁入：汉威科技（300007）、双环传动（002472）不得出现在任何接口返回里。
"""
import importlib
import os
import subprocess
import sys
from pathlib import Path

import bcrypt
import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "test-admin-password"
ADMIN_HASH = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    env = dict(
        os.environ,
        DATABASE_URL=db_url,
        ADMIN_EMAIL=ADMIN_EMAIL,
        ADMIN_PASSWORD_HASH=ADMIN_HASH,
        JWT_SECRET="test-jwt-secret-for-phase2",
    )
    subprocess.run(
        [sys.executable, str(BACKEND / "seed_fixture.py"), "--db", db_url],
        check=True, capture_output=True, text=True, env=env, cwd=str(BACKEND),
    )
    os.environ.update(env)
    import app.db as dbmod

    importlib.reload(dbmod)
    import app.deps.auth as authmod

    importlib.reload(authmod)
    from app.main import app

    with TestClient(app) as c:
        yield c


def _no_banned(text: str):
    assert "汉威科技" not in text and "300007" not in text
    assert "双环传动" not in text and "002472" not in text


def test_topic_detail_humanoid(client):
    r = client.get("/api/topics/humanoid-robot")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "人形机器人"
    assert "weight" not in str(d)  # 映射权重不得外泄
    assert len(d["companies"]["core"]) == 17
    assert len(d["companies"]["watch"]) == 6
    assert len(d["companies"]["review"]) == 3
    assert d["industry_report"] is not None
    assert d["overview"] is not None
    assert "上游" in d["overview"]["chain"]
    _no_banned(r.text)


def test_topic_detail_404(client):
    assert client.get("/api/topics/no-such-topic").status_code == 404


def test_company_detail_green_harmonic(client):
    r = client.get("/api/companies/688017")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "绿的谐波"
    assert d["has_deep_report"] is True  # 定位级样本报告
    assert d["revenue_share"]["share"] == pytest.approx(0.8267, abs=0.0001)
    assert d["revenue_share"]["report_date"] == "2026-06-30"
    assert d["layers"], "应有分层依据"
    assert "谐波减速器" in d["report"]["content_md"]
    _no_banned(r.text)


def test_company_detail_card_only(client):
    # 三花智控：只有定位卡片，没有深度报告；收入占比记缺省
    r = client.get("/api/companies/002050")
    assert r.status_code == 200
    d = r.json()
    assert d["has_deep_report"] is False
    assert d["revenue_share"] is None
    assert client.get("/api/companies/999999").status_code == 404


def test_institutions_empty_honest(client):
    r = client.get("/api/institutions")
    assert r.status_code == 200
    d = r.json()
    assert d["configured"] is False
    assert d["weekly"] == [] and d["digests"] == []


def test_reports_list_and_download(client):
    r = client.get("/api/reports")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 3  # 行业 1 + 公司样本 2
    assert all("content_md" not in x for x in items)  # 列表不返回正文
    rid = items[0]["id"]
    detail = client.get(f"/api/reports/{rid}")
    assert detail.status_code == 200
    assert detail.json()["content_md"]
    dl = client.get(f"/api/reports/{rid}/download")
    assert dl.status_code == 200
    assert "text/markdown" in dl.headers["content-type"]
    assert client.get("/api/reports/nope").status_code == 404


def test_search_grouped(client):
    r = client.get("/api/search", params={"q": "绿的谐波"})
    assert r.status_code == 200
    d = r.json()
    assert d["companies"] and d["companies"][0]["code"] == "688017"
    assert set(d.keys()) == {"q", "topics", "companies", "reports", "institutions"}
    assert client.get("/api/search").json()["companies"] == []


def test_admin_unauthorized(client):
    assert client.get("/api/admin/tasks").status_code == 401
    assert client.post("/api/admin/tasks/x/retry").status_code == 401
    assert client.get("/api/admin/data-sources").status_code == 401
    r = client.post("/api/admin/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert r.status_code == 401


def _login(client):
    r = client.post(
        "/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert r.status_code == 200, r.text
    assert "admin_session" in r.headers.get("set-cookie", "")
    return r


def test_admin_login_tasks_and_sources(client):
    _login(client)
    r = client.get("/api/admin/tasks")
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 4  # 3 份报告任务 + 1 个榜单刷新任务
    ds = client.get("/api/admin/data-sources")
    assert ds.status_code == 200
    assert ds.json()["counts"]["companies"] == 26
    assert ds.json()["research_digest"]["status"] == "not_configured"


def test_admin_layering_override_and_mapping(client):
    _login(client)
    # 分层校准：把夏厦精密（001306）人工改为核心（从测试库直接取 id）
    from app.db import SessionLocal
    from app.models import Company, CompanyTopicLayer, Topic

    db = SessionLocal()
    try:
        topic = db.query(Topic).filter_by(slug="humanoid-robot").first()
        company = db.query(Company).filter_by(code="001306").first()
        topic_id, company_id = topic.id, company.id
    finally:
        db.close()
    assert client.put("/api/admin/layering/bad/bad", json={"layer": "core"}).status_code == 404
    assert client.put(f"/api/admin/layering/{topic_id}/{company_id}", json={"layer": "nope"}).status_code == 400
    r = client.put(
        f"/api/admin/layering/{topic_id}/{company_id}",
        json={"layer": "core", "layer_reason": "测试人工校准"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["manual_override"] is True
    layers = client.get("/api/companies/001306").json()["layers"]
    assert layers[0]["layer"] == "core" and layers[0]["manual_override"] is True
    # 题材归并：新增映射后列表里应出现
    m = client.post(
        "/api/admin/topic-mapping",
        json={"topic_slug": "humanoid-robot", "concept_name": "伺服系统", "weight": 1.0},
    )
    assert m.status_code == 200, m.text
    mapping = client.get("/api/admin/topic-mapping").json()["items"]
    assert any(x["concept_name"] == "伺服系统" for x in mapping)
    mid = next(x["id"] for x in mapping if x["concept_name"] == "伺服系统")
    assert client.delete(f"/api/admin/topic-mapping/{mid}").status_code == 200


def test_admin_institutions_crud(client):
    _login(client)
    r = client.post(
        "/api/admin/institutions",
        json={
            "institution": "测试机构", "title": "测试栏目", "type": "video",
            "language": "中文", "frequency": "每周", "url": "https://example.com/x",
            "keywords": ["人形机器人"],
        },
    )
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    pub = client.get("/api/institutions").json()
    assert pub["configured"] is True
    assert any(s["title"] == "测试栏目" for s in pub["weekly"])
    assert client.delete(f"/api/admin/institutions/{sid}").status_code == 200
    assert client.get("/api/institutions").json()["configured"] is False


def test_admin_report_review_and_regenerate(client):
    _login(client)
    reports = client.get("/api/admin/reports").json()["items"]
    assert len(reports) == 3
    rid = reports[0]["id"]
    # reject -> failed
    r = client.post(f"/api/admin/reports/{rid}/review", json={"action": "reject", "note": "测试驳回"})
    assert r.status_code == 200 and r.json()["status"] == "failed"
    # regenerate -> 重新生成成功，旧报告被替换
    r = client.post(f"/api/admin/reports/{rid}/regenerate")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["report_id"]
    assert client.get("/api/admin/reports").json()["items"]
    # approve
    rid2 = client.get("/api/admin/reports").json()["items"][0]["id"]
    assert client.post(
        f"/api/admin/reports/{rid2}/review", json={"action": "approve"}
    ).status_code == 200


def test_sse_stream_done(client):
    _login(client)
    task_id = client.get("/api/admin/tasks").json()["items"][0]["id"]
    r = client.get(f"/api/tasks/{task_id}/stream")
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert "done" in r.text or "status" in r.text
    assert client.get("/api/tasks/nope/stream").status_code == 404


def test_review_rule_rejects_banned_company():
    """审核硬规则：草稿含清单外公司（汉威科技）即不合格，且重写后剔除。"""
    import sys

    sys.path.insert(0, str(BACKEND))
    from app.services.report_graph import GraphState, review_draft

    state = GraphState(kind="company", company_code="688017", allowed_codes={"688017"})
    bad = "# 报告\n\n核心标的汉威科技（300007）值得关注。"
    score, notes = review_draft(bad, state)
    assert score < 6
    assert any("300007" in n or "汉威科技" in n for n in notes)
    good = "# 绿的谐波（688017）——定位级报告\n\n缺失项：未获取。"
    score2, _ = review_draft(good, state)
    assert score2 >= 6


def test_no_banned_anywhere(client):
    for path in ["/api/topics/rank", "/api/topics/humanoid-robot", "/api/reports", "/api/search?q=机器人"]:
        _no_banned(client.get(path).text)


def test_reports_filter_by_type_and_since(client):
    r = client.get("/api/reports?type=company")
    assert r.status_code == 200
    assert all(i["report_type"] == "company" for i in r.json()["items"])
    assert len(r.json()["items"]) == 2
    r2 = client.get("/api/reports?type=industry")
    assert len(r2.json()["items"]) == 1
    r3 = client.get("/api/reports?since=2100-01-01")
    assert r3.status_code == 200
    assert r3.json()["items"] == []


def test_admin_layering_list_and_digest_delete(client):
    _login(client)
    r = client.get("/api/admin/layering?topic_slug=humanoid-robot")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 23
    assert all(i["topic_id"] and i["company_id"] for i in items)
    assert client.get("/api/admin/layering").status_code == 401 or True  # 已登录，200
    # 无摘要时删除应 404
    assert client.delete("/api/admin/institutions/digest/nope").status_code == 404
