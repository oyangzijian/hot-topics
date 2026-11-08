"""管理 API — 修正版规格 v2 §7.2，全部 require_admin，未登录 401。

端点：
POST /api/admin/login | POST /api/admin/logout
GET /api/admin/tasks | POST /api/admin/tasks/{id}/retry
GET/POST/DELETE /api/admin/topic-mapping
PUT /api/admin/layering/{topic_id}/{company_id}
GET/POST/PUT/DELETE /api/admin/institutions
GET /api/admin/data-sources
GET /api/admin/reports | GET /api/admin/reports/{id} | POST /api/admin/reports/{id}/review |
POST /api/admin/reports/{id}/regenerate | DELETE /api/admin/reports/{id}
GET /api/tasks/{id}/stream (SSE)
"""
from __future__ import annotations

import hmac
import json
import os
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ..db import get_db
from ..deps.auth import (
    COOKIE_NAME,
    SESSION_TTL_SECONDS,
    check_admin_credentials,
    make_session_token,
    require_admin,
)
from ..models import (
    Company,
    CompanyTopicLayer,
    InstitutionSource,
    Report,
    ResearchDigest,
    Task,
    Topic,
    TopicConceptMap,
    TopicRankSnapshot,
)
from ..services.report_graph import run_task

router = APIRouter()


class LoginBody(BaseModel):
    email: str
    password: str


class MappingBody(BaseModel):
    topic_slug: str
    concept_name: str
    weight: float = 1.0


class LayeringBody(BaseModel):
    layer: str  # core / watch
    layer_reason: str | None = None


class InstitutionBody(BaseModel):
    institution: str
    title: str
    type: str  # video / report
    language: str | None = None
    frequency: str | None = None
    url: str | None = None
    keywords: list[str] | None = None
    active: bool = True


class ReviewBody(BaseModel):
    action: str  # approve / reject
    note: str | None = None


class IngestReportBody(BaseModel):
    """stockreport 推送入库（docs/ingest_contract.md）。

    topic 是题材名（如“绿色电力”），按 Topic.name 精确匹配，匹配不到
    返回 400，绝不自动新建题材。report_html 存 evidence，不进 content_md
    （前端 Markdown 渲染器不渲染 HTML）。

    upsert 键是 (code, trade_date)：同一家公司同一交易日的报告只存一份，
    题材只作标签（evidence.topics 累积 slug+name），不按题材存多份相同 HTML。
    trade_date 为空时退回按 (company, topic) 查找。
    """

    code: str
    name: str | None = None
    source: str | None = None
    topic: str | None = None
    trade_date: str | None = None
    generated_at: str | None = None
    summary: dict | None = None
    report_html: str


def _check_ingest_token(authorization: str | None):
    """独立 Bearer INGEST_TOKEN（环境变量，每次请求读取）。

    不用管理员 JWT：推送方是无人值守脚本，token 泄露可单独轮换。
    未配置服务端 token 时直接 500（fail closed），不放行。
    """
    expected = os.environ.get("INGEST_TOKEN")
    if not expected:
        raise HTTPException(status_code=500, detail="服务端未配置 INGEST_TOKEN")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少或错误的入库 token")
    if not hmac.compare_digest(authorization[len("Bearer "):], expected):
        raise HTTPException(status_code=401, detail="缺少或错误的入库 token")


@router.post("/api/admin/ingest/report")
def ingest_report(
    body: IngestReportBody,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _check_ingest_token(authorization)
    code = (body.code or "").strip().zfill(6)
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=400, detail=f"股票代码无效：{body.code!r}")
    if not body.topic or not body.topic.strip():
        raise HTTPException(status_code=400, detail="缺少 topic（题材名）")
    topic = db.query(Topic).filter_by(name=body.topic.strip()).first()
    if topic is None:
        raise HTTPException(
            status_code=400,
            detail=f"题材不存在：{body.topic}，请先在题材库中建立该题材",
        )
    company = db.query(Company).filter_by(code=code).first()
    if company is None:
        company = Company(code=code, name=(body.name or code).strip(), industry=None)
        db.add(company)
        db.flush()
    elif body.name and body.name.strip() and company.name != body.name.strip():
        # 公司已存在时不覆盖已有名称（人工核验过的名称优先），只补空名。
        if not company.name:
            company.name = body.name.strip()
    trade_date = (body.trade_date or "").strip() or None
    evidence = {
        "report_html": body.report_html,
        "stockreport_summary": body.summary,
        "trade_date": trade_date,
        "generated_at": body.generated_at,
        "source": body.source or "stockreport",
        "topics": [{"slug": topic.slug, "name": topic.name}],
    }
    # upsert 键 (code, trade_date)：同一家公司同一交易日的报告只存一份。
    # trade_date 存在 evidence JSON 里，SQLite 下在 Python 侧比对（单家报告行数很少）。
    report = None
    company_reports = (
        db.query(Report)
        .filter_by(company_id=company.id, report_type="company")
        .order_by(Report.created_at.desc())
        .all()
    )
    if trade_date:
        for r in company_reports:
            if (r.evidence or {}).get("trade_date") == trade_date:
                report = r
                break
    else:
        for r in company_reports:
            if r.topic_id == topic.id:
                report = r
                break
    created = report is None
    if created:
        report = Report(
            topic_id=topic.id,
            company_id=company.id,
            report_type="company",
            status="pending",
            content_md="详见 HTML 报告。",
            evidence=evidence,
        )
        db.add(report)
    else:
        merged = dict(report.evidence or {})
        # 题材只作标签：累积所有推送过的题材（去重），topic_id 保持首次推送的题材不变。
        # 注意：先取旧 topics，再 update（update 会覆盖 topics，需重建）。
        old_topics = [t for t in merged.get("topics", []) if isinstance(t, dict)]
        merged.update(evidence)
        seen = {t.get("slug") for t in old_topics}
        all_topics = list(old_topics)
        for t in evidence["topics"]:
            if t["slug"] not in seen:
                all_topics.append(t)
                seen.add(t["slug"])
        merged["topics"] = all_topics
        report.evidence = merged
        report.content_md = "详见 HTML 报告。"
        report.status = "pending"  # 重推回待审核，走现有审核链路
        report.updated_at = datetime.utcnow()
    db.commit()
    return {
        "ok": True,
        "report_id": report.id,
        "created": created,
        "status": "pending",
        "company": company.name,
        "topic": topic.name,
        "topics": [t["name"] for t in (report.evidence or {}).get("topics", [])],
    }


@router.post("/api/admin/login")
def admin_login(body: LoginBody):
    if not check_admin_credentials(body.email, body.password):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = make_session_token(body.email)
    from fastapi.responses import JSONResponse

    resp = JSONResponse({"ok": True, "email": body.email})
    resp.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("SECURE_COOKIE", "0") == "1",
        path="/",
    )
    return resp


@router.post("/api/admin/logout")
def admin_logout(_admin: str = Depends(require_admin)):
    from fastapi.responses import JSONResponse

    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


def _task_out(t: Task) -> dict:
    return {
        "id": t.id,
        "task_type": t.task_type,
        "status": t.status,
        "progress": t.progress,
        "error": t.error,
        "payload": t.payload,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
    }


@router.get("/api/admin/tasks")
def list_tasks(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    return {"items": [_task_out(t) for t in db.query(Task).order_by(Task.created_at.desc()).all()]}


@router.post("/api/admin/tasks/{task_id}/retry")
def retry_task(task_id: str, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    task = db.query(Task).filter_by(id=task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.task_type in ("industry_report", "company_report"):
        report = run_task(db, task)
        return {"task": _task_out(task), "report_id": report.id if report else None}
    # rank_refresh 等非报告任务：重置为 pending，由 worker 下次执行
    task.status = "pending"
    task.progress = 0
    task.error = None
    db.commit()
    return {"task": _task_out(task), "report_id": None}


@router.get("/api/tasks/{task_id}/stream")
async def task_stream(task_id: str, db: Session = Depends(get_db)):
    """SSE：推送 status/progress/done/error。任务已结束时立即发 done。

    注意：依赖注入的 Session 在首个事件后即关闭，因此轮询时每次
    用新的 SessionLocal 查任务状态，不复用请求级 Session。
    """
    import asyncio

    from ..db import SessionLocal

    task = db.query(Task).filter_by(id=task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def events():
        for _ in range(20):  # 最多轮询 10 秒
            session = SessionLocal()
            try:
                current = session.query(Task).filter_by(id=task_id).first()
                if current is None:
                    return
                payload = {
                    "status": current.status,
                    "progress": current.progress,
                    "error": current.error,
                }
            finally:
                session.close()
            yield {"event": "status", "data": json.dumps(payload, ensure_ascii=False)}
            if payload["status"] in ("done", "failed"):
                yield {
                    "event": "done" if payload["status"] == "done" else "error",
                    "data": json.dumps(payload, ensure_ascii=False),
                }
                return
            await asyncio.sleep(0.5)

    return EventSourceResponse(events())


@router.get("/api/admin/topic-mapping")
def list_mapping(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    items = []
    for m in db.query(TopicConceptMap).all():
        topic = db.query(Topic).filter_by(id=m.topic_id).first()
        items.append(
            {
                "id": m.id,
                "topic_slug": topic.slug if topic else None,
                "topic_name": topic.name if topic else None,
                "concept_name": m.concept_name,
                "weight": float(m.weight or 1),
            }
        )
    return {"items": items}


@router.post("/api/admin/topic-mapping")
def add_mapping(body: MappingBody, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    topic = db.query(Topic).filter_by(slug=body.topic_slug).first()
    if topic is None:
        raise HTTPException(status_code=404, detail="题材不存在")
    existing = (
        db.query(TopicConceptMap)
        .filter_by(topic_id=topic.id, concept_name=body.concept_name)
        .first()
    )
    if existing:
        existing.weight = body.weight
        db.commit()
        return {"ok": True, "id": existing.id, "updated": True}
    m = TopicConceptMap(topic_id=topic.id, concept_name=body.concept_name, weight=body.weight)
    db.add(m)
    db.commit()
    return {"ok": True, "id": m.id, "updated": False}


@router.delete("/api/admin/topic-mapping/{mapping_id}")
def delete_mapping(mapping_id: str, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    m = db.query(TopicConceptMap).filter_by(id=mapping_id).first()
    if m is None:
        raise HTTPException(status_code=404, detail="映射不存在")
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.get("/api/admin/layering")
def list_layering(
    topic_slug: str | None = None,
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    """分层列表（含 topic_id/company_id，供后台校准表单用）。"""
    q = db.query(CompanyTopicLayer)
    if topic_slug:
        topic = db.query(Topic).filter_by(slug=topic_slug).first()
        if topic is None:
            raise HTTPException(status_code=404, detail="题材不存在")
        q = q.filter_by(topic_id=topic.id)
    items = []
    for layer in q.all():
        company = db.query(Company).filter_by(id=layer.company_id).first()
        topic = db.query(Topic).filter_by(id=layer.topic_id).first()
        items.append(
            {
                "topic_id": layer.topic_id,
                "topic_slug": topic.slug if topic else None,
                "company_id": layer.company_id,
                "code": company.code if company else None,
                "name": company.name if company else None,
                "segment": layer.chain_segment,
                "layer": layer.layer,
                "layer_reason": layer.layer_reason,
                "manual_override": layer.manual_override,
            }
        )
    return {"items": items}


@router.put("/api/admin/layering/{topic_id}/{company_id}")
def calibrate_layer(
    topic_id: str, company_id: str, body: LayeringBody,
    db: Session = Depends(get_db), _admin: str = Depends(require_admin),
):
    if body.layer not in ("core", "watch"):
        raise HTTPException(status_code=400, detail="layer 只能是 core 或 watch")
    layer = (
        db.query(CompanyTopicLayer)
        .filter_by(topic_id=topic_id, company_id=company_id)
        .first()
    )
    if layer is None:
        raise HTTPException(status_code=404, detail="分层记录不存在")
    layer.layer = body.layer
    layer.manual_override = True
    if body.layer_reason:
        layer.layer_reason = body.layer_reason
    db.commit()
    return {"ok": True, "layer": layer.layer, "manual_override": True}


@router.get("/api/admin/institutions")
def list_institutions_admin(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    return {
        "sources": [
            {
                "id": s.id, "institution": s.institution, "title": s.title, "type": s.type,
                "language": s.language, "frequency": s.frequency, "url": s.url,
                "keywords": s.keywords, "active": s.active,
            }
            for s in db.query(InstitutionSource).all()
        ],
        "digests": [
            {
                "id": d.id, "institution": d.institution, "title": d.title,
                "published_at": d.published_at.isoformat() if d.published_at else None,
                "summary": d.summary, "source_url": d.source_url, "keywords": d.keywords,
            }
            for d in db.query(ResearchDigest).order_by(ResearchDigest.published_at.desc()).all()
        ],
    }


@router.post("/api/admin/institutions")
def add_institution(body: InstitutionBody, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    if body.type not in ("video", "report"):
        raise HTTPException(status_code=400, detail="type 只能是 video 或 report")
    s = InstitutionSource(
        institution=body.institution, title=body.title, type=body.type,
        language=body.language, frequency=body.frequency, url=body.url,
        keywords=body.keywords, active=body.active,
    )
    db.add(s)
    db.commit()
    return {"ok": True, "id": s.id}


@router.delete("/api/admin/institutions/{source_id}")
def delete_institution(source_id: str, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    s = db.query(InstitutionSource).filter_by(id=source_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="机构源不存在")
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.delete("/api/admin/institutions/digest/{digest_id}")
def delete_digest(digest_id: str, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    d = db.query(ResearchDigest).filter_by(id=digest_id).first()
    if d is None:
        raise HTTPException(status_code=404, detail="研报摘要不存在")
    db.delete(d)
    db.commit()
    return {"ok": True}


@router.get("/api/admin/data-sources")
def data_sources(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    latest = db.query(TopicRankSnapshot).order_by(TopicRankSnapshot.snapshot_at.desc()).first()
    return {
        "akshare_concept_board": {
            "status": "ok" if latest else "no_snapshot",
            "last_success_at": latest.snapshot_at.isoformat() if latest and latest.snapshot_at else None,
            "refresh_interval_minutes": int(os.environ.get("RANK_REFRESH_INTERVAL_MINUTES", "30")),
            "note": "概念列表缓存 5 分钟，成分股缓存 1 小时；失败返回上一快照 + stale",
        },
        "lazy_graph": {"status": "ok", "note": "东财概念 + 同花顺主营 zyjs + zygc（带 SH/SZ 前缀）；ChainKnowledgeGraph 只做辅助"},
        "research_digest": {
            "status": "not_configured",
            "note": "研报摘要源未配置：无 Tushare token、无 MCP。s2 不依赖 Tushare。",
        },
        "counts": {
            "topics": db.query(Topic).count(),
            "companies": db.query(Company).count(),
            "layers": db.query(CompanyTopicLayer).count(),
            "reports": db.query(Report).count(),
            "tasks": db.query(Task).count(),
        },
    }


@router.get("/api/admin/reports")
def list_reports_admin(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    items = []
    for r in db.query(Report).order_by(Report.created_at.desc()).all():
        topic = db.query(Topic).filter_by(id=r.topic_id).first() if r.topic_id else None
        company = db.query(Company).filter_by(id=r.company_id).first() if r.company_id else None
        # 列表不回传 report_html（可达数百 KB）：只给摘要 + 是否有 HTML 报告。
        # 详情页 GET /api/reports/{id} 才返回完整 evidence。
        evidence = dict(r.evidence or {})
        has_html = bool(evidence.pop("report_html", None))
        # 审核高亮：summary.critical_fail > 0，或报告顶部有红色“关键校验未通过”横幅
        # （stockreport 模板原话），审核人不要直接通过。
        summary = evidence.get("stockreport_summary") or {}
        critical_fail = summary.get("critical_fail") if isinstance(summary, dict) else 0
        needs_attention = bool(
            (isinstance(critical_fail, (int, float)) and critical_fail > 0)
            or "关键校验未通过" in (r.evidence or {}).get("report_html", "")
        )
        items.append(
            {
                "id": r.id, "report_type": r.report_type, "status": r.status,
                "topic": topic.name if topic else None,
                "company": company.name if company else None,
                "evidence": evidence,
                "has_html_report": has_html,
                "needs_attention": needs_attention,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return {"items": items}


@router.get("/api/admin/reports/{report_id}")
def get_report_admin(
    report_id: str, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
):
    """后台报告详情：管理员读全文（含 evidence.report_html），用于审核 pending 报告。
    公开端 GET /api/reports/{id} 只返回 done 的报告。"""
    r = db.query(Report).filter_by(id=report_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    topic = db.query(Topic).filter_by(id=r.topic_id).first() if r.topic_id else None
    company = db.query(Company).filter_by(id=r.company_id).first() if r.company_id else None
    return {
        "id": r.id,
        "report_type": r.report_type,
        "status": r.status,
        "topic": {"slug": topic.slug, "name": topic.name} if topic else None,
        "company": {"code": company.code, "name": company.name} if company else None,
        "content_md": r.content_md,
        "evidence": r.evidence,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.post("/api/admin/reports/{report_id}/review")
def review_report(report_id: str, body: ReviewBody, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    r = db.query(Report).filter_by(id=report_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action 只能是 approve 或 reject")
    if body.action == "approve":
        r.status = "done"
        db.commit()
        return {"ok": True, "status": "done"}
    # reject：审核不通过，状态改为 failed，等待重新生成（最多重写 2 次由图内控制）
    r.status = "failed"
    db.commit()
    return {"ok": True, "status": "failed", "note": body.note}


@router.post("/api/admin/reports/{report_id}/regenerate")
def regenerate_report(report_id: str, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    r = db.query(Report).filter_by(id=report_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    topic = db.query(Topic).filter_by(id=r.topic_id).first() if r.topic_id else None
    company = db.query(Company).filter_by(id=r.company_id).first() if r.company_id else None
    task = Task(
        task_type="industry_report" if r.report_type == "industry" else "company_report",
        payload={
            "report_type": r.report_type,
            "topic_slug": topic.slug if topic else None,
            "company_code": company.code if company else None,
        },
        status="pending",
        progress=0,
    )
    db.add(task)
    db.commit()
    report = run_task(db, task)
    if report is not None:
        db.delete(r)
        db.commit()
        return {"ok": True, "task": _task_out(task), "report_id": report.id}
    return {"ok": False, "task": _task_out(task), "report_id": None}


@router.delete("/api/admin/reports/{report_id}")
def delete_report(report_id: str, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    r = db.query(Report).filter_by(id=report_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    db.delete(r)
    db.commit()
    return {"ok": True}
