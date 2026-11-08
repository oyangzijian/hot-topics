"""内容校验—— 直接采用 astock-data 包 astock/extract/validator.py，未改逻辑。
每条陈述必须有出处，所有数字（含年份）须出现在出处原文里，且不得含评价性措辞。
"""
import re

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def _norm(s: str) -> str:
    return s.replace(",", "").replace("，", "")


def check_statement(stmt: dict, banned: list[str]) -> list[str]:
    """stmt: {text, sources:[{url, page, quote}]}。返回问题列表，空列表表示通过。"""
    issues = []
    text = stmt.get("text", "")
    sources = stmt.get("sources") or []
    for w in banned:
        if w in text:
            issues.append(f"banned_word:{w}")
    if not sources:
        issues.append("no_source")
        return issues
    if any(not s.get("url") or not s.get("quote") for s in sources):
        issues.append("source_incomplete")
    quotes = _norm(" ".join(s.get("quote", "") for s in sources))
    for num in _NUM.findall(_norm(text)):
        bare = num.rstrip("%")
        if num not in quotes and bare not in quotes:
            issues.append(f"number_not_in_source:{num}")
    return issues


def date_in_quote(iso: str, quote: str) -> bool:
    """ISO 日期（YYYY-MM-DD）是否能在引文中找到对应写法。"""
    y, m, d = (int(x) for x in iso.split("-"))
    q = _norm(quote).replace(" ", "")
    forms = [iso, f"{y}年{m}月{d}日", f"{y}年{m:02d}月{d:02d}日", f"{y}/{m}/{d}", f"{y}.{m}.{d}", f"{y}-{m}-{d}"]
    return any(f in q for f in forms)
