"""题材相关业务营收占比（分层 s2）— 修正版规格 v2 §6.2。

重要更正（2026-11-07 晚实测）：stock_zygc_em 不是接口死了，是之前
调用方式错了——代码必须带市场前缀 SH/SZ，裸代码会报 KeyError 'zygcfx'。
实测：
- SH688017 成功 145 行，2026-06-30 谐波减速器及金属部件 82.67%、毛利率 32.79%
- SZ002050 成功，2026-06-30 制冷空调电器零部件 61.80%、汽车零部件 38.20%
- SH601100 成功，2025-12-31 液压油缸 48.02%、液压泵阀及马达 39.53%

规则：
- 取最新报告期、按产品分类（分类类型 == "按产品分类"）；
- 产品名含题材关键词的，收入比例加总为 s2；
- 匹配不到的记缺省（None），不记 0；
- 三花、恒立的产品分类本身太粗，机器人业务拆不出来——匹配不到时如实记缺省。
"""
from __future__ import annotations

import time


def with_market_prefix(code: str) -> str:
    """股票代码 -> AKShare zygc 用的带前缀代码。"""
    code = str(code).strip().zfill(6)
    if code.startswith(("60", "68", "90")):
        return f"SH{code}"
    if code.startswith(("00", "30", "20")):
        return f"SZ{code}"
    if code.startswith(("43", "92", "87")):
        return f"BJ{code}"
    return f"SZ{code}"


def parse_revenue_share(df, keywords: list[str]) -> dict | None:
    """纯函数：从 stock_zygc_em 返回的 DataFrame 里算 s2。

    df 列：报告日期、分类类型、主营构成、收入比例、毛利率。
    返回 None = 匹配不到（缺省），不是 0。
    """
    if df is None or len(df) == 0:
        return None
    prod = df[df["分类类型"] == "按产品分类"]
    if len(prod) == 0:
        return None
    latest = prod["报告日期"].max()
    rows = prod[prod["报告日期"] == latest]
    matched = [
        (str(r["主营构成"]), float(r["收入比例"]))
        for _, r in rows.iterrows()
        if any(kw in str(r["主营构成"]) for kw in keywords)
    ]
    if not matched:
        return None
    return {
        "share": round(sum(v for _, v in matched), 4),
        "matched_products": [name for name, _ in matched],
        "report_date": str(latest),
        "all_products": [str(r["主营构成"]) for _, r in rows.iterrows()],
    }


def fetch_revenue_share(code: str, keywords: list[str], _ak=None) -> dict | None:
    """实时拉取一次 zygc 并算 s2。失败或匹配不到都返回 None（缺省）。"""
    try:
        import akshare as ak  # type: ignore
    except ImportError:
        return None
    try:
        time.sleep(2)  # 限速：东财接口每次调用间隔 >= 2 秒
        df = ak.stock_zygc_em(symbol=with_market_prefix(code))
    except Exception:
        return None
    return parse_revenue_share(df, keywords)
