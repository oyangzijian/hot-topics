"""发布闸门—— 直接采用 astock-data 包 astock/publish/gate.py，未改逻辑。
校验全部通过才自动发布，否则进入人工审核队列。
"""
def route(issues: list[str]) -> str:
    return "auto_publish" if not issues else "review"


def diff_changelog(old: dict, new: dict) -> str:
    """用户可读的变更说明（按条数，不暴露内部 ID）。"""
    added = sum(1 for k in new if k not in old)
    changed = sum(1 for k in new if k in old and old[k] != new[k])
    removed = sum(1 for k in old if k not in new)
    parts = [f"{label} {n} 条" for label, n in (("更新", changed), ("新增", added), ("移除", removed)) if n]
    return "；".join(parts) or "无变化"
