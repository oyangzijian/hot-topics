"""报告生成图 — LangGraph 简版（无 LLM 密钥时用模板化确定性生成）。

节点：plan → retrieve → write → review（不合格最多重写 2 次）→ finalize。
硬性审核规则（修正版规格 v2 §6.3，代码化）：
- 报告中出现的公司（按代码/名称匹配）必须在输入清单或图谱中找到；
  清单外公司作核心标的 → 审核不通过，触发重写（剔除违规句），最多 2 次。
- 每个关键判断附来源标注；不虚构财务数据，缺失写“未获取”。
- 只给绿的谐波、兆威机电写定位级样本报告；其余公司不生成“深度报告”，
  只返回定位卡片（调用方负责展示，不谎称深度报告）。

LangGraph 本身未作为硬依赖引入（本机无 LLM 密钥，引入也跑不起来）：
本模块按同一状态图结构实现为纯函数节点，待 LLM 接入时把 write/review
节点换成 LangGraph 节点即可，状态字段与节点名保持一致。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import Company, CompanyTopicLayer, Report, Task, Topic
from .topic_content import COMPANY_REPORTS, industry_report_md

MAX_REWRITE = 2
BANNED_CODES = {"300007", "002472"}  # 汉威科技、双环传动：不在实测名单里
BANNED_NAMES = {"汉威科技", "双环传动"}


@dataclass
class GraphState:
    kind: str  # industry / company
    topic_slug: str | None = None
    company_code: str | None = None
    allowed_codes: set[str] = field(default_factory=set)
    allowed_names: set[str] = field(default_factory=set)
    draft: str = ""
    review_score: int | None = None
    review_notes: list[str] = field(default_factory=list)
    rewrites: int = 0


def _find_violations(draft: str, state: GraphState) -> list[str]:
    """找出草稿中作为核心标的出现的清单外公司。返回违规描述列表。"""
    violations: list[str] = []
    for code in BANNED_CODES:
        if code in draft:
            violations.append(f"清单外公司代码 {code} 出现在报告中")
    for name in BANNED_NAMES:
        if name in draft:
            violations.append(f"清单外公司 {name} 出现在报告中")
    # 6 位代码：凡在草稿中出现、又不在允许清单里的，一律违规
    for code in set(re.findall(r"\b\d{6}\b", draft)):
        if code not in state.allowed_codes:
            violations.append(f"清单外公司代码 {code} 出现在报告中")
    return violations


def review_draft(draft: str, state: GraphState) -> tuple[int, list[str]]:
    """review 节点：10 分制。违规扣分；有违规即不合格（<6 分）。"""
    violations = _find_violations(draft, state)
    notes = list(violations)
    if "未获取" not in draft and "未" not in draft:
        notes.append("报告未标注任何缺失项，可疑：请确认缺失项是否如实写了“未获取”")
    score = 10 if not violations else 3
    return score, notes


def _strip_violating_lines(draft: str, violations: list[str]) -> str:
    lines = draft.splitlines()
    bad_tokens: set[str] = set()
    for v in violations:
        m = re.search(r"(\d{6})", v)
        if m:
            bad_tokens.add(m.group(1))
        for name in BANNED_NAMES:
            if name in v:
                bad_tokens.add(name)
    kept = [ln for ln in lines if not any(t in ln for t in bad_tokens)]
    return "\n".join(kept)


def plan(state: GraphState) -> GraphState:
    return state


def retrieve(db: Session, state: GraphState) -> GraphState:
    """retrieve 节点：从 DB 取输入清单（题材公司分层），不联网、不编造。"""
    if state.topic_slug:
        topic = db.query(Topic).filter_by(slug=state.topic_slug).first()
        if topic is not None:
            layers = (
                db.query(CompanyTopicLayer)
                .filter_by(topic_id=topic.id)
                .all()
            )
            for layer in layers:
                company = db.query(Company).filter_by(id=layer.company_id).first()
                if company:
                    state.allowed_codes.add(company.code)
                    state.allowed_names.add(company.name)
    if state.company_code:
        company = db.query(Company).filter_by(code=state.company_code).first()
        if company:
            state.allowed_codes.add(company.code)
            state.allowed_names.add(company.name)
    return state


def write(state: GraphState, db: Session) -> GraphState:
    """write 节点：模板化生成，只用 retrieve 到的证据。"""
    if state.kind == "industry":
        topic = db.query(Topic).filter_by(slug=state.topic_slug).first()
        name = topic.name if topic else (state.topic_slug or "")
        state.draft = industry_report_md(name) or f"# {name}行业报告\n\n暂无已核验的行业报告内容：未获取。"
        return state
    if state.kind == "company":
        code = (state.company_code or "").zfill(6)
        if code in COMPANY_REPORTS:
            state.draft = COMPANY_REPORTS[code]
            return state
        company = db.query(Company).filter_by(code=code).first()
        cname = company.name if company else code
        state.draft = (
            f"# {cname}（{code}）——定位卡片\n\n"
            "本公司暂无完整深度报告，只有定位卡片与分层依据。\n\n"
            "## 分层依据\n\n"
            "见公司页“分层依据”一栏（置信度、证据关键词、来源标注）。\n\n"
            "## 缺失项\n\n"
            "- 收入占比（按产品拆分）：未获取\n"
            "- 客户验证进度、量产时间：未获取\n\n"
            "定位卡片不是深度报告；不是投资建议。\n"
        )
        return state
    state.draft = ""
    return state


def run_report_graph(db: Session, state: GraphState) -> GraphState:
    """plan → retrieve → write → review（≤2 次重写）→ finalize（由调用方写库）。"""
    state = plan(state)
    state = retrieve(db, state)
    state = write(state, db)
    while True:
        score, notes = review_draft(state.draft, state)
        state.review_score = score
        state.review_notes = notes
        if score >= 6 or state.rewrites >= MAX_REWRITE:
            break
        state.draft = _strip_violating_lines(state.draft, notes)
        state.rewrites += 1
        # 重写后用模板重新生成一次（模板只用允许清单，第二次即干净）
        state = write(state, db)
        if state.rewrites >= MAX_REWRITE:
            score, notes = review_draft(state.draft, state)
            state.review_score = score
            state.review_notes = notes
            break
    return state


def run_task(db: Session, task: Task) -> Report | None:
    """执行一个报告任务：跑图 → 写 reports 行 → 更新任务状态。返回报告或 None。"""
    from datetime import datetime

    task.status = "running"
    task.progress = 10
    task.started_at = datetime.utcnow()
    db.commit()
    payload = task.payload or {}
    kind = payload.get("report_type", "industry")
    state = GraphState(
        kind=kind,
        topic_slug=payload.get("topic_slug"),
        company_code=payload.get("company_code"),
    )
    state = run_report_graph(db, state)
    task.progress = 80
    if (state.review_score or 0) < 6:
        task.status = "failed"
        task.error = "审核未通过：" + "；".join(state.review_notes)
        task.progress = 100
        task.finished_at = datetime.utcnow()
        db.commit()
        return None
    topic_id = None
    company_id = None
    if state.topic_slug:
        topic = db.query(Topic).filter_by(slug=state.topic_slug).first()
        topic_id = topic.id if topic else None
    if state.company_code:
        company = db.query(Company).filter_by(code=state.company_code).first()
        company_id = company.id if company else None
    report = Report(
        topic_id=topic_id,
        company_id=company_id,
        report_type=kind,
        status="done",
        content_md=state.draft,
        evidence={
            "review_score": state.review_score,
            "review_notes": state.review_notes,
            "rewrites": state.rewrites,
            "allowed_codes": sorted(state.allowed_codes),
        },
        task_id=task.id,
    )
    db.add(report)
    task.status = "done"
    task.progress = 100
    task.finished_at = datetime.utcnow()
    db.commit()
    return report
