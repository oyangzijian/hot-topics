"""榜单拆分：题材榜 / 风格·行为榜。

规则来自 config/topic_filter.yaml（东财概念板块里混有的行为/风格标签），
移植自 stockreport 的 sitegen.split_ranking()，逻辑未改。
榜单拆分本身是展示口径，规则文件改动需人工批准。
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

def _find_config() -> Path:
    """向上查找 config/topic_filter.yaml（仓库根目录或 backend/ 下均可）。"""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        cand = parent / "config" / "topic_filter.yaml"
        if cand.exists():
            return cand
    return here.parents[2] / "config" / "topic_filter.yaml"


CONFIG_PATH = _find_config()


def load_rules(path: Path | None = None) -> dict:
    with open(path or CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_topic(name: str, rules: dict | None = None) -> str:
    """返回「题材」或「风格/行为」。"""
    r = rules or load_rules()
    if name in r.get("style_exact", []) or any(
        re.search(p, name) for p in r.get("style_regex", [])
    ):
        return "风格/行为"
    return "题材"


def split_ranking(rows: list[dict], name_key: str = "name", rules: dict | None = None):
    """把榜单拆成 (题材榜, 风格/行为榜)，各自保持原顺序并重排名次。"""
    r = rules or load_rules()
    a, b = [], []
    for x in rows:
        (b if classify_topic(x[name_key], r) == "风格/行为" else a).append(dict(x))
    for lst in (a, b):
        for i, x in enumerate(lst, 1):
            x["rank"] = i
    return a, b
