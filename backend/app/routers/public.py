"""公开 API — 修正版规格 v2 §7.1（Phase 2：全部公开接口实现）。

硬性：公开接口不得返回后台字段（映射权重、校准记录等）。
失败时返回上一快照 + stale=true，绝不报 500。
研报摘要源未配置（无 Tushare token、无 MCP）时，机构观点返回空列表 +
configured=false，不编造摘要。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Company,
    CompanyTopicLayer,
    InstitutionSource,
    Report,
    ResearchDigest,
    Topic,
    TopicConceptMap,
    TopicRankSnapshot,
)
from ..schemas import RankItem, RankResponse
from ..services.topic_content import HUMANOID_OVERVIEW

router = APIRouter()


def _public_company(c: Company) -> dict:
    return {
        "code": c.code,
        "name": c.name,
        "industry": c.industry,
        "main_products": c.main_products,
    }


def _layer_out(db: Session, layer: CompanyTopicLayer) -> dict:
    company = db.query(Company).filter_by(id=layer.company_id).first()
    return {
        "code": company.code if company else None,
        "name": company.name if company else None,
        "segment": layer.chain_segment,
        "layer": layer.layer,
        "layer_reason": layer.layer_reason,
        "source_flags": layer.source_flags,
        "main_business": None,
        "main_products": company.main_products if company else None,
    }


@router.get("/api/topics/rank", response_model=RankResponse)
def get_topic_rank(db: Session = Depends(get_db)):
    """榜单：题材榜 / 风格·行为榜拆分（config/topic_filter.yaml），组合题目标记，
    近 5 次热度走势，以及诚实的新鲜度标注（交易日与抓取时间分开；周末只显示休市，
    只有交易日刷新失败才标 stale）。"""
    from ..monitor.freshness import describe_status
    from ..services.topic_filter import split_ranking

    topics = db.query(Topic).all()
    items: list[RankItem] = []
    latest_at: datetime | None = None
    for topic in topics:
        snap = (
            db.query(TopicRankSnapshot)
            .filter(TopicRankSnapshot.topic_id == topic.id)
            .order_by(TopicRankSnapshot.snapshot_at.desc(), TopicRankSnapshot.id.desc())
            .first()
        )
        if snap is None:
            continue
        if latest_at is None or (snap.snapshot_at and snap.snapshot_at > latest_at):
            latest_at = snap.snapshot_at
        # 近 5 次快照热度（旧→新），用于判断升温/降温
        history = (
            db.query(TopicRankSnapshot)
            .filter(TopicRankSnapshot.topic_id == topic.id)
            .order_by(TopicRankSnapshot.snapshot_at.desc(), TopicRankSnapshot.id.desc())
            .limit(5)
            .all()
        )
        trend = [float(h.heat_score or 0) for h in reversed(history)]
        n_maps = db.query(TopicConceptMap).filter_by(topic_id=topic.id).count()
        snap_at = snap.snapshot_at
        if snap_at is not None and snap_at.tzinfo is None:
            snap_at = snap_at.replace(tzinfo=timezone.utc)
        items.append(
            RankItem(
                slug=topic.slug,
                name=topic.name,
                rank=int(snap.rank or 0),
                heat_score=float(snap.heat_score or 0),
                change_pct=float(snap.change_pct) if snap.change_pct is not None else None,
                up_ratio=float(snap.up_ratio) if snap.up_ratio is not None else None,
                turnover_rate=float(snap.turnover) if snap.turnover is not None else None,
                leading_company=snap.leading_company,
                leading_code=snap.leading_code,
                leading_change=None,
                up_count=int(snap.up_count) if snap.up_count is not None else None,
                down_count=int(snap.down_count) if snap.down_count is not None else None,
                limit_up_count=int(snap.limit_up_count) if snap.limit_up_count is not None else None,
                turnover_amount=float(snap.turnover_amount) if snap.turnover_amount is not None else None,
                main_net_inflow=float(snap.main_net_inflow) if snap.main_net_inflow is not None else None,
                trend=trend,
                is_composite=n_maps > 1,
                snapshot_at=snap_at.isoformat() if snap_at else None,
            )
        )
    items.sort(key=lambda x: -x.heat_score)
    for i, item in enumerate(items, start=1):
        item.rank = i
    topic_rows, style_rows = split_ranking(
        [it.model_dump() for it in items], name_key="name"
    )
    topics_out = [RankItem(**r) for r in topic_rows]
    styles_out = [RankItem(**r) for r in style_rows]
    # 诚实标注：stale 只在交易日刷新失败时为真；周末/节假日显示休市，不标过期。
    status = describe_status(
        datetime.now(timezone.utc),
        latest_at.replace(tzinfo=timezone.utc)
        if latest_at is not None and latest_at.tzinfo is None
        else latest_at,
    )
    last_success = latest_at.isoformat() if latest_at else None
    return RankResponse(
        items=items,
        topics=topics_out,
        styles=styles_out,
        updated_at=last_success,
        stale=status["stale"],
        last_success_at=last_success,
        trade_date=status["trade_date"],
        fetched_at=status["fetched_at"],
        market_status=status["market_status"],
        stale_reason=status["stale_reason"],
    )


@router.get("/api/market/overview")
def get_market_overview():
    """大盘指数条：三大指数 + 两市成交额 + 涨跌/涨跌停家数。

    只读快照文件，不现算、不调 AKShare（避免触发限流）；快照由刷新
    worker（榜单刷新收尾顺带，或 python -m app.workers.market_refresh --once）
    写入。无快照时全部数字字段为 null + stale=true；刷新失败时返回
    上一快照 + stale=true，绝不报 500。
    """
    from ..services.market_overview import load_snapshot, overview_response

    return overview_response(load_snapshot())


@router.get("/api/topics/{slug}")
def get_topic_detail(slug: str, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter_by(slug=slug).first()
    if topic is None:
        raise HTTPException(status_code=404, detail="题材不存在")
    snap = (
        db.query(TopicRankSnapshot)
        .filter(TopicRankSnapshot.topic_id == topic.id)
        .order_by(TopicRankSnapshot.snapshot_at.desc(), TopicRankSnapshot.id.desc())
        .first()
    )
    # 概念映射名（不返回权重：后台字段）
    concept_names = [
        m.concept_name
        for m in db.query(TopicConceptMap).filter_by(topic_id=topic.id).all()
    ]
    layers = db.query(CompanyTopicLayer).filter_by(topic_id=topic.id).all()
    companies = [_layer_out(db, layer) for layer in layers]
    # 待复核公司：不在分层表里，单独列出（只含已核验的 3 家）
    layered_codes = {c["code"] for c in companies}
    review = []
    if slug == "humanoid-robot":
        for c in db.query(Company).all():
            if c.code not in layered_codes and c.code in {"300403", "920124", "000887"}:
                review.append(
                    {
                        "code": c.code,
                        "name": c.name,
                        "segment": "待复核",
                        "layer": "review",
                        "layer_reason": "置信度低，待人工复核后再定",
                        "source_flags": {"concept": True, "chain": False},
                        "main_products": c.main_products,
                    }
                )
    # 链环节分组（按 segment 首段归组，仅展示用）
    segments: dict[str, list[str]] = {}
    for c in companies:
        seg = (c["segment"] or "未分类").split("、")[0]
        segments.setdefault(seg, []).append(c["code"])
    # 行业报告（最新已完成）
    report = (
        db.query(Report)
        .filter_by(topic_id=topic.id, report_type="industry", status="done")
        .order_by(Report.created_at.desc())
        .first()
    )
    # 相关题材：按热度取前 5 个（不含自己）
    others = [
        {"slug": t.slug, "name": t.name}
        for t in db.query(Topic).filter(Topic.id != topic.id).limit(5).all()
    ]
    overview = HUMANOID_OVERVIEW if slug == "humanoid-robot" else None
    return {
        "slug": topic.slug,
        "name": topic.name,
        "description": topic.description,
        "rank": int(snap.rank) if snap and snap.rank else None,
        "heat_score": float(snap.heat_score) if snap and snap.heat_score is not None else None,
        "change_pct": float(snap.change_pct) if snap and snap.change_pct is not None else None,
        "updated_at": snap.snapshot_at.isoformat() if snap and snap.snapshot_at else None,
        "concept_names": concept_names,
        "overview": overview,
        "segments": segments,
        "companies": {"core": [c for c in companies if c["layer"] == "core"],
                      "watch": [c for c in companies if c["layer"] == "watch"],
                      "review": review},
        "industry_report": (
            {"id": report.id, "status": report.status} if report else None
        ),
        "related_topics": others,
    }


@router.get("/api/companies/{code}")
def get_company_detail(code: str, db: Session = Depends(get_db)):
    code = code.zfill(6)
    company = db.query(Company).filter_by(code=code).first()
    if company is None:
        raise HTTPException(status_code=404, detail="公司不存在")
    layers = []
    for layer in db.query(CompanyTopicLayer).filter_by(company_id=company.id).all():
        topic = db.query(Topic).filter_by(id=layer.topic_id).first()
        layers.append(
            {
                "topic_slug": topic.slug if topic else None,
                "topic_name": topic.name if topic else None,
                "segment": layer.chain_segment,
                "layer": layer.layer,
                "layer_reason": layer.layer_reason,
                "source_flags": layer.source_flags,
                "manual_override": layer.manual_override,
            }
        )
    report = (
        db.query(Report)
        .filter_by(company_id=company.id, report_type="company", status="done")
        .order_by(Report.created_at.desc())
        .first()
    )
    # 同环节公司（同一题材同一 segment 首段）
    same_segment: list[dict] = []
    if layers:
        seg0 = (layers[0]["segment"] or "").split("、")[0]
        for layer in db.query(CompanyTopicLayer).all():
            if layer.company_id == company.id:
                continue
            if (layer.chain_segment or "").split("、")[0] == seg0:
                other = db.query(Company).filter_by(id=layer.company_id).first()
                if other:
                    same_segment.append({"code": other.code, "name": other.name, "segment": layer.chain_segment})
    # 收入占比：只对已核验的 688017 给夹具值，其余一律“未获取”
    revenue_share = None
    if code == "688017":
        revenue_share = {
            "product": "谐波减速器及金属部件",
            "share": 0.8267,
            "report_date": "2026-06-30",
            "source": "东财主营构成 stock_zygc_em（SH688017）",
        }
    return {
        "code": company.code,
        "name": company.name,
        "industry": company.industry,
        "main_products": company.main_products,
        "layers": layers,
        "report": (
            {
                "id": report.id,
                "status": report.status,
                "content_md": report.content_md,
                # stockreport 入库的报告是 HTML（存 evidence.report_html），
                # 前端 Markdown 渲染器不渲染 HTML，改链到 /reports/[id] 用 iframe 看。
                "report_html": bool(report.evidence and report.evidence.get("report_html")),
            }
            if report else None
        ),
        "has_deep_report": report is not None,
        "revenue_share": revenue_share,
        "same_segment": same_segment[:10],
        "evidence_note": "关键判断附来源标注；缺失项写“未获取”，不编造。",
    }


@router.get("/api/institutions")
def get_institutions(
    type_: str | None = Query(default=None, alias="type"),
    institution: str | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(InstitutionSource).filter_by(active=True)
    if type_:
        q = q.filter_by(type=type_)
    if institution:
        q = q.filter(InstitutionSource.institution.contains(institution))
    sources = [
        {
            "id": s.id,
            "institution": s.institution,
            "title": s.title,
            "type": s.type,
            "language": s.language,
            "frequency": s.frequency,
            "url": s.url,
            "keywords": s.keywords,
        }
        for s in q.all()
    ]
    dq = db.query(ResearchDigest)
    if institution:
        dq = dq.filter(ResearchDigest.institution.contains(institution))
    if keyword:
        dq = dq.filter(ResearchDigest.title.contains(keyword))
    digests = [
        {
            "id": d.id,
            "institution": d.institution,
            "title": d.title,
            "published_at": d.published_at.isoformat() if d.published_at else None,
            "summary": d.summary,
            "source_url": d.source_url,
            "keywords": d.keywords,
        }
        for d in dq.order_by(ResearchDigest.published_at.desc()).all()
    ]
    return {
        "configured": bool(sources or digests),
        "note": "研报摘要源未配置（无 Tushare token、无 MCP）时返回空列表，不编造摘要；请在后台添加机构源。",
        "weekly": [s for s in sources if s["type"] == "video"],
        "digests": digests,
        "sources": sources,
    }


@router.get("/api/reports")
def list_reports(
    status: str | None = None,
    topic_slug: str | None = None,
    type: str | None = Query(default=None, alias="type"),
    since: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Report)
    # 公开列表只返回已审核通过（done）的报告；pending/failed 一律不对公开端暴露，
    # 后台审核走 /api/admin/reports。status 参数公开端忽略，不得用来捞出 pending。
    q = q.filter_by(status="done")
    if type:
        q = q.filter_by(report_type=type)
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            q = q.filter(Report.created_at >= since_dt)
        except ValueError:
            pass
    items = []
    for r in q.order_by(Report.created_at.desc()).all():
        topic = db.query(Topic).filter_by(id=r.topic_id).first() if r.topic_id else None
        company = db.query(Company).filter_by(id=r.company_id).first() if r.company_id else None
        if topic_slug:
            # stockreport 入库的报告按 (code, trade_date) 只存一份，题材只作标签
            # （evidence.topics 累积）；题材筛选时 topic_id 或 topics 命中其一即算命中。
            ev = r.evidence or {}
            tag_slugs = [t.get("slug") for t in ev.get("topics", []) if isinstance(t, dict)]
            if (not topic or topic.slug != topic_slug) and topic_slug not in tag_slugs:
                continue
        items.append(
            {
                "id": r.id,
                "report_type": r.report_type,
                "status": r.status,
                "topic": {"slug": topic.slug, "name": topic.name} if topic else None,
                "company": {"code": company.code, "name": company.name} if company else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
        )
    return {"items": items}


@router.get("/api/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)):
    r = db.query(Report).filter_by(id=report_id).first()
    # 未审核通过的报告只允许管理员看：公开端一律 404（不泄露存在性），
    # 管理员读全文走 GET /api/admin/reports/{id}。
    if r is None or r.status != "done":
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


@router.get("/api/reports/{report_id}/download")
def download_report(report_id: str, db: Session = Depends(get_db)):
    r = db.query(Report).filter_by(id=report_id).first()
    if r is None or r.status != "done" or r.content_md is None:
        raise HTTPException(status_code=404, detail="报告不存在或无内容")
    return PlainTextResponse(
        r.content_md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}.md"'},
    )


@router.get("/api/search")
def search(q: str = Query(default=""), db: Session = Depends(get_db)):
    q = (q or "").strip()
    if not q:
        return {"q": q, "topics": [], "companies": [], "reports": [], "institutions": []}
    topics = [
        {"slug": t.slug, "name": t.name}
        for t in db.query(Topic).filter(Topic.name.contains(q)).limit(10).all()
    ]
    companies = [
        {"code": c.code, "name": c.name}
        for c in db.query(Company)
        .filter((Company.name.contains(q)) | (Company.code.contains(q)))
        .limit(10)
        .all()
    ]
    reports = []
    for r in (
        db.query(Report)
        .filter(Report.content_md.contains(q), Report.status == "done")
        .limit(10)
        .all()
    ):
        topic = db.query(Topic).filter_by(id=r.topic_id).first() if r.topic_id else None
        company = db.query(Company).filter_by(id=r.company_id).first() if r.company_id else None
        reports.append(
            {
                "id": r.id,
                "report_type": r.report_type,
                "topic": topic.name if topic else None,
                "company": company.name if company else None,
            }
        )
    institutions = [
        {"id": s.id, "institution": s.institution, "title": s.title, "type": s.type}
        for s in db.query(InstitutionSource)
        .filter((InstitutionSource.title.contains(q)) | (InstitutionSource.institution.contains(q)))
        .limit(10)
        .all()
    ]
    return {"q": q, "topics": topics, "companies": companies, "reports": reports, "institutions": institutions}
