"""Pydantic 输出模型。公开接口绝不返回后台字段（映射权重、校准记录等）。"""
from __future__ import annotations

from pydantic import BaseModel


class RankItem(BaseModel):
    slug: str
    name: str
    rank: int
    heat_score: float
    change_pct: float | None = None
    up_ratio: float | None = None
    turnover_rate: float | None = None  # 换手率(%)，不是成交额
    leading_company: str | None = None
    leading_code: str | None = None  # 领涨股票代码（供领涨公司点进公司页）
    leading_change: float | None = None
    up_count: int | None = None  # 上涨家数（取领涨板块值）
    down_count: int | None = None  # 下跌家数（取领涨板块值）
    limit_up_count: int | None = None  # 涨停数（成分股近似计数，见方法说明页）
    turnover_amount: float | None = None  # 成分股成交额加总(元）
    main_net_inflow: float | None = None  # 主力净流入（亿元，领涨板块口径；无数据为 null）
    trend: list[float] = []  # 近 5 次快照的热度分（旧→新），用于判断升温/降温
    is_composite: bool = False  # 是否组合题材（由多个概念板块取均值，见方法说明页）
    snapshot_at: str | None = None


class RankResponse(BaseModel):
    items: list[RankItem]  # 全部题材，按热度分降序（保持兼容）
    topics: list[RankItem] = []  # 题材榜（真题材，拆分后重排名）
    styles: list[RankItem] = []  # 风格/行为榜（拆分后重排名）
    updated_at: str | None = None
    stale: bool
    last_success_at: str | None = None
    trade_date: str | None = None  # 数据所属交易日（YYYY-MM-DD）
    fetched_at: str | None = None  # 抓取时间（ISO，+08:00）
    market_status: str = "unknown"  # trading / closed / market_closed
    stale_reason: str | None = None  # stale 时写清原因，否则 None
    heat_formula: str = "v2.1-percentile"  # 当前线上公式；z-score v1.0 待批准，未切换
    source: str = "akshare-concept-board"
    note: str = "热度分是涨跌幅、上涨占比等指标的加权结果，缺失指标不参与计算；主力净流入为领涨概念板块的东财资金流（亿元），缺失时为 null，热度分不含该指标。详细口径见方法说明页。"
