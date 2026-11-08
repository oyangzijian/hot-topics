"""数据模型 — 修正版规格 v2 §4（字段可增不可缺核心项）。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)


class TopicConceptMap(Base):
    __tablename__ = "topic_concept_map"
    __table_args__ = (UniqueConstraint("topic_id", "concept_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"), nullable=False)
    concept_name: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric, default=1)


class TopicRankSnapshot(Base):
    __tablename__ = "topic_rank_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"), nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer)
    heat_score: Mapped[float | None] = mapped_column(Numeric)
    change_pct: Mapped[float | None] = mapped_column(Numeric)
    turnover: Mapped[float | None] = mapped_column(Numeric)  # v2：此处存换手率(%)，不是成交额
    main_net_inflow: Mapped[float | None] = mapped_column(Numeric)  # v2：无可用来源时为 NULL
    limit_up_count: Mapped[int | None] = mapped_column(Integer)  # v2：无可用来源时为 NULL
    up_ratio: Mapped[float | None] = mapped_column(Numeric)
    leading_company: Mapped[str | None] = mapped_column(Text)
    leading_code: Mapped[str | None] = mapped_column(Text)  # 领涨股票代码（供领涨公司点进公司页）
    up_count: Mapped[int | None] = mapped_column(Integer)  # 上涨家数（取领涨板块值，见 rank_refresh）
    down_count: Mapped[int | None] = mapped_column(Integer)  # 下跌家数（同上）
    turnover_amount: Mapped[float | None] = mapped_column(Numeric)  # 成分股成交额加总(元，第二步）
    snapshot_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[str | None] = mapped_column(Text)
    main_products: Mapped[list | None] = mapped_column(JSON)


class CompanyTopicLayer(Base):
    __tablename__ = "company_topic_layers"
    __table_args__ = (UniqueConstraint("topic_id", "company_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id"), nullable=False)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id"), nullable=False)
    layer: Mapped[str] = mapped_column(Text, nullable=False)  # core / watch
    chain_segment: Mapped[str | None] = mapped_column(Text)
    layer_score: Mapped[float | None] = mapped_column(Numeric)
    layer_reason: Mapped[str | None] = mapped_column(Text)
    source_flags: Mapped[dict | None] = mapped_column(JSON)  # {concept: bool, chain: bool}
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    topic_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("topics.id"))
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("companies.id"))
    report_type: Mapped[str] = mapped_column(Text, nullable=False)  # industry / company
    status: Mapped[str] = mapped_column(Text, default="pending")  # pending/running/done/failed
    content_md: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    task_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)  # rank_refresh/industry_report/...
    payload: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(Text, default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class InstitutionSource(Base):
    __tablename__ = "institution_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    institution: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)  # video / report
    language: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list | None] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ResearchDigest(Base):
    __tablename__ = "research_digests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    institution: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list | None] = mapped_column(JSON)
    topic_ids: Mapped[list | None] = mapped_column(JSON)
