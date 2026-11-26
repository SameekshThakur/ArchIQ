"""LLM provider abstraction.

All AI endpoints go through `LLMProvider`. `MockLLMProvider` is a deterministic,
template-driven narrator and `AzureOpenAIProvider` (azure_openai.py) is the real model. The *facts* (findings, impacts, scores) are computed by real rule/graph engines;
the provider turns those structured facts into prose. Both implement the same
two methods and receive the same `LLMRequest`; see README "Using the Azure OpenAI model".
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from app.core.config import get_settings


@dataclass
class LLMRequest:
    task: str  # e.g. "copilot.answer", "adr.render", "review.summary"
    input: dict[str, Any] = field(default_factory=dict)  # structured facts already computed by the engines
    system: str | None = None  # a real provider would prepend this as the system prompt


@dataclass
class LLMResponse:
    text: str
    confidence: float = 0.9
    meta: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def generate(self, req: LLMRequest) -> LLMResponse: ...

    def stream(self, req: LLMRequest) -> AsyncIterator[str]: ...


def _latency(req: LLMRequest, lo: float = 0.6, hi: float = 2.5) -> float:
    """Deterministic 600-2500ms delay derived from the request so repeated calls feel consistent."""
    scale = get_settings().ai_latency
    if scale <= 0:
        return 0.0
    h = int(hashlib.sha1(f"{req.task}:{sorted(req.input.keys())}".encode()).hexdigest()[:6], 16) / 0xFFFFFF
    return (lo + (hi - lo) * h) * scale


class MockLLMProvider:
    """# MOCK: rule/template engine standing in for an LLM. Never calls the network."""

    name = "mock"

    async def generate(self, req: LLMRequest) -> LLMResponse:
        from app.mock_ai import narration  # local import avoids a cycle with the template registry

        await asyncio.sleep(_latency(req))
        text, confidence, meta = narration.render(req.task, req.input)
        return LLMResponse(text=text, confidence=confidence, meta=meta)

    async def stream(self, req: LLMRequest) -> AsyncIterator[str]:  # type: ignore[override]
        from app.mock_ai import narration

        await asyncio.sleep(_latency(req, 0.3, 0.9))
        text, _, _ = narration.render(req.task, req.input)
        # emit token-like chunks (words plus trailing whitespace) with a human-ish cadence
        for chunk in _tokenize(text):
            yield chunk
            await asyncio.sleep(0.012 if get_settings().ai_latency > 0 else 0)


def _tokenize(text: str) -> list[str]:
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch in " \n":
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


_provider: LLMProvider | None = None
provider_note: str | None = None  # why the configured provider is not the one in use, shown by /ai/status


def get_provider() -> LLMProvider:
    global _provider, provider_note
    if _provider is None:
        name = get_settings().provider.lower()
        if name == "mock":
            _provider = MockLLMProvider()
        elif name in ("azure_openai", "azure"):
            try:
                from app.mock_ai.azure_openai import AzureOpenAIProvider

                _provider = AzureOpenAIProvider()
            except Exception as e:  # missing key or package: keep the app usable and say so
                provider_note = f"PROVIDER={name} but it could not start ({e}); using the built-in narrator."
                logging.getLogger("archiq.llm").error(provider_note)
                _provider = MockLLMProvider()
        else:
            raise RuntimeError(f"Unsupported PROVIDER '{name}'. Use 'mock' or 'azure_openai'.")
    return _provider


def reset_provider() -> None:
    """Forget the cached provider (tests, and after settings change)."""
    global _provider, provider_note
    _provider, provider_note = None, None


async def simulate(seconds: float) -> None:
    """Sleep for a simulated AI step, honouring AI_LATENCY=0 for tests."""
    s = get_settings().ai_latency
    if s > 0:
        await asyncio.sleep(seconds * s)
