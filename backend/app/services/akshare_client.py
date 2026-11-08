"""AKShare 客户端 — 修正版规格 v2 §5.1。

实测教训（2026-11-07）：拉 9 个板块成分股即 502 + 约 5 分钟封禁。
因此：每次调用间隔 >= 2 秒、失败重试、本地缓存；失败时由调用方
返回上一快照，本模块绝不把异常包装成 500 抛给前端。
AKShare 只在调用时才懒加载，未安装时抛 RuntimeError 并注明安装方式。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from .heat_score import BoardMetrics

LIST_TTL_SECONDS = int(os.environ.get("AKSHARE_CACHE_TTL_SECONDS", "300"))
CONS_TTL_SECONDS = int(os.environ.get("CONCEPT_CONS_CACHE_TTL_SECONDS", "3600"))
MIN_INTERVAL_SECONDS = 2.0
MAX_RETRIES = 3

# stock_board_concept_name_em() 实测字段（13 个，2026-11-07，AKShare 1.20.35）
BOARD_COLUMNS = [
    "排名", "板块名称", "板块代码", "最新价", "涨跌额", "涨跌幅", "总市值",
    "换手率", "上涨家数", "下跌家数", "领涨股票", "领涨股票-涨跌幅", "领涨股票-代码",
]


@dataclass
class _CacheEntry:
    at: float
    value: object


class AKShareClient:
    def __init__(self, min_interval: float = MIN_INTERVAL_SECONDS):
        self._list_cache: _CacheEntry | None = None
        self._cons_cache: dict[str, _CacheEntry] = {}
        self._last_call_at = 0.0
        self._min_interval = min_interval

    def _throttle(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last_call_at)
        if wait > 0:
            time.sleep(wait)
        self._last_call_at = time.monotonic()

    def _akshare(self):
        try:
            import akshare as ak  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "未安装 akshare，实时拉取不可用：pip install akshare==1.20.35"
            ) from exc
        return ak

    def fetch_concept_boards(self) -> list[BoardMetrics]:
        """概念板块列表。命中缓存直接返回；失败重试 3 次后抛异常给 worker 做 stale 处理。"""
        now = time.monotonic()
        if self._list_cache and now - self._list_cache.at < LIST_TTL_SECONDS:
            return self._list_cache.value  # type: ignore[return-value]
        ak = self._akshare()
        last_exc: Exception | None = None
        for _ in range(MAX_RETRIES):
            try:
                self._throttle()
                df = ak.stock_board_concept_name_em()
                break
            except Exception as exc:  # noqa: BLE001 - 限流/502 都走同一重试路径
                last_exc = exc
                time.sleep(2.0)
        else:
            raise RuntimeError(f"AKShare 概念板块拉取失败（重试 {MAX_RETRIES} 次）: {last_exc}")
        boards: list[BoardMetrics] = []
        for _, row in df.iterrows():
            up = int(row["上涨家数"])
            down = int(row["下跌家数"])
            boards.append(
                BoardMetrics(
                    name=str(row["板块名称"]),
                    code=str(row["板块代码"]),
                    change_pct=float(row["涨跌幅"]),
                    up_ratio=(up / (up + down)) if (up + down) > 0 else None,
                    turnover_rate=float(row["换手率"]),
                    market_cap=float(row["总市值"]),
                    leading_change=float(row["领涨股票-涨跌幅"]),
                    leading_company=str(row["领涨股票"]),
                    leading_code=str(row["领涨股票-代码"]).zfill(6),
                    up_count=up,
                    down_count=down,
                )
            )
        self._list_cache = _CacheEntry(at=now, value=boards)
        return boards

    def fetch_concept_constituents(self, board_code: str):
        """某板块成分股（缓存 1 小时）。调用方负责控制并发与间隔。"""
        now = time.monotonic()
        hit = self._cons_cache.get(board_code)
        if hit and now - hit.at < CONS_TTL_SECONDS:
            return hit.value
        ak = self._akshare()
        self._throttle()
        df = ak.stock_board_concept_cons_em(symbol=board_code)
        self._cons_cache[board_code] = _CacheEntry(at=now, value=df)
        return df

    def aggregate_board_metrics(self, board_code: str) -> dict:
        """第二步：成分股加总/计数，返回 {turnover_amount, limit_up_count}。

        - 成交额 = 成分股“成交额”列求和（元）。
        - 涨停数 = 涨跌幅达到涨停阈值的成分股数，近似计数：688/300 开头
          的科创/创业板股阈值 19.9%，其余 9.9%。不是交易所官方涨停家数，
          界面上不得写成官方口径。
        任一列缺失或拉取失败时返回空字典，调用方保持第一步数值不变。
        """
        try:
            df = self.fetch_concept_constituents(board_code)
            turnover = float(df["成交额"].sum()) if "成交额" in df.columns else None
            limit_up = None
            if "涨跌幅" in df.columns and "代码" in df.columns:
                limit_up = 0
                for _, row in df.iterrows():
                    code = str(row["代码"])
                    threshold = 19.9 if code.startswith(("688", "300")) else 9.9
                    if float(row["涨跌幅"]) >= threshold:
                        limit_up += 1
            out: dict = {}
            if turnover is not None:
                out["turnover_amount"] = turnover
            if limit_up is not None:
                out["limit_up_count"] = float(limit_up)
            return out
        except Exception:
            return {}
