"""LLM 抽取客户端测试：可配置、可插拔，模型默认 Muse。

硬性：
- 默认 provider 必须是 muse；代码里不得写死 claude-sonnet-5-5 这类模型名。
- Muse 没有给后端用的 API key：complete() 必须报 LLMRequiresAssistant，
  绝不编造端点/key；抽取走 extraction_job() 由助手执行。
- Anthropic 只是可选实现：模型与 key 都走配置，缺模型/缺 key 都明确报错。
- 未知 provider 不静默回退，直接报错。
"""
import sys
import types
from pathlib import Path

import pytest
import yaml

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.extract.llm_client import (  # noqa: E402
    AnthropicClient,
    LLMConfig,
    LLMNotConfigured,
    LLMRequiresAssistant,
    MuseClient,
    ManualClient,
    get_llm_client,
    load_llm_config,
)


def test_default_config_is_muse(tmp_path):
    cfg = load_llm_config()
    assert cfg.provider == "muse"
    client = get_llm_client()
    assert isinstance(client, MuseClient)


def test_unknown_provider_errors():
    with pytest.raises(ValueError, match="未知的 LLM provider"):
        get_llm_client(LLMConfig(provider="no-such-provider"))


def test_manual_provider_is_disabled():
    client = get_llm_client(LLMConfig(provider="manual"))
    assert isinstance(client, ManualClient)
    with pytest.raises(LLMNotConfigured, match="抽取已关闭"):
        client.complete([{"role": "user", "content": "hi"}])


def test_muse_complete_refuses_and_points_to_job():
    client = MuseClient(LLMConfig(provider="muse"))
    with pytest.raises(LLMRequiresAssistant) as ei:
        client.complete([{"role": "user", "content": "hi"}])
    assert "不要编造" in str(ei.value) or "编造" in str(ei.value)
    assert "extraction_job" in str(ei.value)


def test_muse_extraction_job_carries_validator_rules():
    client = MuseClient(LLMConfig(provider="muse", extra={"prompt_version": "v1"}))
    job = client.extraction_job(
        {"id": "doc-1", "title": "测试文档", "text": "甲公司 2025 年收入 10 亿元。",
         "url": "https://example.com/doc-1"},
        theme_name="人形机器人",
    )
    assert job["provider"] == "muse"
    assert job["mode"] == "assistant_executed"
    assert job["status"] == "awaiting_assistant"
    assert "人形机器人" in job["prompt"]
    assert "甲公司 2025 年收入 10 亿元" in job["prompt"]
    assert any("引文" in r for r in job["validator_rules"])
    assert any("不得编造" in r for r in job["validator_rules"])
    # 任务里没有 endpoint / api_key 这类字段：不编造调用方式
    assert "endpoint" not in job and "api_key" not in job


def test_anthropic_requires_model_from_config():
    with pytest.raises(LLMNotConfigured, match="模型未配置"):
        AnthropicClient(LLMConfig(provider="anthropic", model=""))


def test_anthropic_requires_key_from_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = AnthropicClient(LLMConfig(provider="anthropic", model="test-model-xyz"))
    with pytest.raises(LLMNotConfigured, match="key 未配置"):
        client.complete([{"role": "user", "content": "hi"}])


def test_anthropic_uses_configured_model_not_hardcoded(monkeypatch):
    """用桩模块证明：模型名只从配置来，代码里没有写死的默认值。"""
    calls: dict = {}

    class FakeMessages:
        def create(self, **kw):
            calls.update(kw)
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text='{"statements":[]}')]
            )

    class FakeAnthropic:
        def __init__(self, api_key=None):
            calls["api_key"] = api_key
            self.messages = FakeMessages()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = FakeAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = AnthropicClient(
        LLMConfig(provider="anthropic", model="test-model-xyz", max_tokens=123)
    )
    out = client.complete([{"role": "user", "content": "hi"}])
    assert out == '{"statements":[]}'
    assert calls["model"] == "test-model-xyz"
    assert calls["max_tokens"] == 123


def test_load_llm_config_from_file(tmp_path):
    p = tmp_path / "llm.yaml"
    p.write_text(
        yaml.safe_dump(
            {"provider": "anthropic",
             "providers": {"anthropic": {"model": "custom-model-1",
                                          "max_tokens": 500,
                                          "api_key_env": "MY_KEY"}}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    cfg = load_llm_config(p)
    assert cfg.provider == "anthropic"
    assert cfg.model == "custom-model-1"
    assert cfg.max_tokens == 500
    assert cfg.api_key_env == "MY_KEY"


def test_no_hardcoded_model_in_client_source():
    src = (BACKEND / "app" / "extract" / "llm_client.py").read_text(encoding="utf-8")
    assert "claude-sonnet" not in src
    assert "claude-3" not in src
