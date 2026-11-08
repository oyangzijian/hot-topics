"""LLM 抽取客户端：可配置、可插拔（2026-11-08 用户授权改造，模型改 Muse）。

包 astock-data 的 extract/pipeline.py 与 revenue_extractor.py 原先写死
Anthropic 客户端 + 一个写死的默认模型名（见 docs/REDESIGN.md），
即写死厂商 + 写死默认模型。移植到本站时一律改走这里：provider 与模型只从
config/llm.yaml 读，Anthropic 只是注册表里的一种可选实现。

模型（2026-11-08 用户定）：Muse——即本助手。
Muse 没有像 Anthropic 那样给后端代码直接调的 API key，所以 muse provider
不在后端发 HTTP 请求、不编造端点或 key：后端只生成抽取任务
（extraction_job），抽取由助手在定时或手动流程里执行；助手输出必须同样过
校验器（app.publish.validator.check_statement：引文须真实存在于原文、
数字/年份/日期须与引文一致、无评价性措辞），校验通过后才能入库——绝不
跳过校验直接入库。

换模型上线前，仍须按 docs/EXTRACTION_EVAL.md 在 30 份以上真实文档上评测
提示词（漏抽率、误抽率、被校验拦截的比例），结果交用户批准。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# 与包 extract/pipeline.py 同款的事实抽取提示词（overview / timeline）。
# 改提示词 = 改抽取行为，必须按 docs/EXTRACTION_EVAL.md 重测 30 份并经用户批准。
PIPELINE_PROMPT = """你是事实抽取器。依据下面的文档，抽取与题材“{theme}”相关的事实陈述。
文档中用 [[p.N]] 标记页码。只输出 JSON，不要解释：
{{"statements":[{{"kind":"overview 或 timeline","date":"YYYY-MM-DD 或 null","text":"中性的事实陈述","page":页码,"quote":"文档中的原句，必须逐字摘录"}}]}}
规则：
1. overview：该题材的定义、范围或文件对其的界定；timeline：有明确日期的事件（发文、发布、披露等），date 必须来自文档。
2. text 只能复述文档明确写出的内容，必须中性，不得评价、预测、推荐，不得使用“龙头”“有望”“看好”等词。
3. quote 必须是文档原文的连续片段，text 中出现的所有数字都必须出现在 quote 中。
4. 最多 {n} 条；文档没有相关内容则输出 {{"statements":[]}}。不得编造。

文档标题：{title}
文档正文：
{body}
"""


class LLMNotConfigured(Exception):
    """LLM 抽取未配置（未配 provider、未配模型、或未配 key）。"""


class LLMRequiresAssistant(LLMNotConfigured):
    """muse provider：抽取由助手执行，后端不直接调用模型。

    不要为了“调通”而编一个假的 Muse API 端点或 key：正确做法是取
    extraction_job() 生成的任务，在定时/手动流程里由助手执行，输出过
    校验器后入库。
    """


@dataclass
class LLMConfig:
    provider: str = "muse"
    model: str = ""
    max_tokens: int = 2000
    api_key_env: str = ""
    extra: dict = field(default_factory=dict)


def default_config_path() -> Path:
    # backend/app/extract/llm_client.py -> 仓库根目录 config/llm.yaml
    return Path(__file__).resolve().parents[3] / "config" / "llm.yaml"


def load_llm_config(path: str | Path | None = None) -> LLMConfig:
    """读 config/llm.yaml。provider 与模型只从这里来，代码里不写死模型名。"""
    path = Path(path) if path else default_config_path()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    provider = str(data.get("provider") or "muse")
    section = (data.get("providers") or {}).get(provider) or {}
    return LLMConfig(
        provider=provider,
        model=str(section.get("model") or ""),
        max_tokens=int(section.get("max_tokens") or 2000),
        api_key_env=str(section.get("api_key_env") or ""),
        extra={k: v for k, v in section.items()
               if k not in ("model", "max_tokens", "api_key_env")},
    )


class BaseLLMClient:
    name = "base"

    def __init__(self, config: LLMConfig):
        self.config = config

    def complete(self, messages: list[dict]) -> str:
        raise NotImplementedError


class ManualClient(BaseLLMClient):
    """provider=manual：抽取关闭，不调任何模型。"""
    name = "manual"

    def complete(self, messages: list[dict]) -> str:
        raise LLMNotConfigured("LLM 抽取未配置（provider=manual，抽取已关闭）")


class MuseClient(BaseLLMClient):
    """provider=muse（默认/首选）：抽取由助手执行。

    后端不发请求、不编造端点/key。complete() 直接报错，调用方应改走
    extraction_job() 生成任务，交助手在定时/手动流程里执行。
    """
    name = "muse"

    def complete(self, messages: list[dict]) -> str:
        raise LLMRequiresAssistant(
            "Muse 抽取由助手在定时/手动流程里执行，后端不直接调用模型"
            "（Muse 没有给后端代码用的 API key，不要编造端点或 key）；"
            "请用 extraction_job() 生成抽取任务，助手输出须过校验器后入库。"
        )

    def extraction_job(
        self,
        doc: dict,
        theme_name: str,
        max_statements: int = 10,
        max_chars: int = 60000,
    ) -> dict:
        """生成一份助手可执行的抽取任务（JSON 友好）。

        doc: {title, text, url?, id?}。输出不直接入库：助手按 prompt 执行后，
        每条陈述仍须过 app.publish.validator.check_statement 才能入库。
        """
        body = (doc.get("text") or "")[:max_chars]
        prompt = PIPELINE_PROMPT.format(
            theme=theme_name, n=max_statements,
            title=doc.get("title") or "", body=body,
        )
        return {
            "provider": "muse",
            "mode": "assistant_executed",
            "prompt_version": self.config.extra.get("prompt_version", "v1"),
            "theme": theme_name,
            "doc_id": doc.get("id"),
            "doc_title": doc.get("title"),
            "doc_url": doc.get("url"),
            "prompt": prompt,
            "validator_rules": [
                "每条陈述必须带出处（url + 页码 + 原文引文）",
                "引文必须是文档原文的连续片段，逐字摘录",
                "陈述中的所有数字（含年份）必须出现在引文中",
                "timeline 的日期必须来自文档，且能在引文中找到对应写法",
                "不得含评价性/推荐性措辞（龙头、有望、看好、目标价等）",
                "找不到相关内容时输出空列表，不得编造",
            ],
            "status": "awaiting_assistant",
        }


class AnthropicClient(BaseLLMClient):
    """provider=anthropic：可选实现。模型与 key 都走配置，不写死默认值。"""
    name = "anthropic"

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        if not config.model:
            raise LLMNotConfigured(
                "anthropic 模型未配置：请在 config/llm.yaml 的 "
                "providers.anthropic.model 里填模型名（代码里不写死默认值）"
            )

    def complete(self, messages: list[dict]) -> str:
        api_key = os.environ.get(self.config.api_key_env or "ANTHROPIC_API_KEY", "")
        if not api_key:
            raise LLMNotConfigured(
                f"Anthropic key 未配置：请设置环境变量 "
                f"{self.config.api_key_env or 'ANTHROPIC_API_KEY'}"
            )
        import anthropic  # 懒加载：不用 anthropic 时不要求装这个包

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            messages=messages,
        )
        return msg.content[0].text


PROVIDERS: dict[str, type[BaseLLMClient]] = {
    "muse": MuseClient,
    "manual": ManualClient,
    "anthropic": AnthropicClient,
}


def get_llm_client(
    config: LLMConfig | None = None, path: str | Path | None = None
) -> BaseLLMClient:
    """按配置取客户端。未知 provider 直接报错，不静默回退到别的模型。"""
    cfg = config or load_llm_config(path)
    cls = PROVIDERS.get(cfg.provider)
    if cls is None:
        raise ValueError(
            f"未知的 LLM provider：{cfg.provider!r}，可用：{sorted(PROVIDERS)}"
        )
    return cls(cfg)


def pipeline_prompt(theme_name: str, max_statements: int, title: str, body: str) -> str:
    """生成事实抽取提示词（与 PIPELINE_PROMPT 同款，供评测脚本复用）。"""
    return PIPELINE_PROMPT.format(
        theme=theme_name, n=max_statements, title=title, body=body[:60000]
    )
