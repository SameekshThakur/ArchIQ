"""AzureOpenAIProvider: grounding, fallback, caching and wiring. A fake client stands in for the network."""

import asyncio
from types import SimpleNamespace

import pytest

from app.mock_ai import provider as prov
from app.mock_ai.azure_openai import AzureOpenAIProvider
from app.mock_ai.provider import LLMRequest

FACTS = dict(count=3, filter="critical", target="Oracle 11g", names=["Claims Core", "Policy Admin", "Billing"], critical=2, kind="database", workflows=4, top_path="Claims Core -> Oracle 11g", note="")
REQ = LLMRequest(task="copilot.list_dependents", input=FACTS)


class FakeClient:
    def __init__(self, text="Three critical applications depend on Oracle 11g.", error=None, finish="stop"):
        self.calls, self.text, self.error, self.finish = [], text, error, finish
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        msg = SimpleNamespace(content=self.text)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=self.finish)], model="gpt-5-mini", usage=SimpleNamespace(total_tokens=321))


def run(coro):
    return asyncio.run(coro)


def test_uses_the_model_text_and_reports_the_provider():
    c = FakeClient("Three critical applications depend on Oracle 11g, and 2 are business-critical.")
    r = run(AzureOpenAIProvider(c).generate(REQ))
    assert r.text.startswith("Three critical") and r.meta["provider"] == "azure_openai" and r.meta["tokens"] == 321
    sent = c.calls[0]
    assert sent["model"] == "gpt-5-mini" and sent["max_completion_tokens"] > 0 and "temperature" not in sent
    user = sent["messages"][1]["content"]
    assert "Oracle 11g" in user and "DRAFT" in user  # facts and the built-in draft are both supplied


def test_error_falls_back_to_the_builtin_narrator():
    p = AzureOpenAIProvider(FakeClient(error=TimeoutError("slow")))
    r = run(p.generate(REQ))
    assert r.meta["provider"] == "mock" and "TimeoutError" in r.meta["fallback"]
    assert "Oracle 11g" in r.text and p.stats["fallbacks"] == 1


def test_empty_answer_falls_back():
    r = run(AzureOpenAIProvider(FakeClient(text="  ", finish="length")).generate(REQ))
    assert r.meta["provider"] == "mock" and "empty" in r.meta["fallback"]


def test_invented_figures_are_rejected():
    r = run(AzureOpenAIProvider(FakeClient("Oracle 11g is used by 47 applications.")).generate(REQ))
    assert r.meta["provider"] == "mock" and "47" in r.meta["fallback"]


def test_numbers_check_can_be_turned_off(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_verify_numbers", False)
    r = run(AzureOpenAIProvider(FakeClient("Oracle 11g is used by 47 applications.")).generate(REQ))
    assert r.meta["provider"] == "azure_openai"


def test_identical_requests_are_cached():
    c = FakeClient()
    p = AzureOpenAIProvider(c)
    a, b = run(p.generate(REQ)), run(p.generate(REQ))
    assert a.text == b.text and len(c.calls) == 1 and p.stats["cached"] == 1
    run(p.generate(LLMRequest(task=REQ.task, input={**FACTS, "count": 2})))
    assert len(c.calls) == 2


def test_fixed_replies_never_call_the_model():
    c = FakeClient()
    r = run(AzureOpenAIProvider(c).generate(LLMRequest(task="copilot.help", input={})))
    assert not c.calls and "dependencies" in r.text


def test_stream_releases_the_checked_answer_in_pieces():
    async def go():
        return [t async for t in AzureOpenAIProvider(FakeClient("Oracle 11g has 3 dependants.")).stream(REQ)]

    toks = run(go())
    assert len(toks) > 2 and "".join(toks) == "Oracle 11g has 3 dependants."


def test_missing_key_keeps_the_app_running_on_the_builtin_narrator(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "provider", "azure_openai")
    prov.reset_provider()
    try:
        p = prov.get_provider()
        assert p.name == "mock" and "could not start" in prov.provider_note
    finally:
        prov.reset_provider()


def test_status_endpoint_never_exposes_the_key(client):
    j = client.get("/api/v1/ai/status").json()
    assert j["active"] == "mock" and j["key_set"] is False and "key" not in {k for k in j if k != "key_set"}
    t = client.post("/api/v1/ai/test").json()
    assert t["ok"] is False
