"""Azure OpenAI implementation of `LLMProvider`.

The engines still compute every fact. This provider only asks the model to put those facts into words, and it
protects the result in four ways:

* the model is told to use only the supplied facts, and is given the built-in narrator's text as a reference draft;
* any figure in the answer that is not in the facts or the draft rejects the answer (`LLM_VERIFY_NUMBERS`);
* any error, timeout or empty answer falls back to the built-in narrator, so a page never fails because of the model;
* answers are cached per (task, facts), so repeat views are instant and consistent.

Fixed texts (the Copilot help and "did you mean" replies) stay on the built-in narrator: nothing to improve there.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import OrderedDict
from typing import Any, AsyncIterator

from app.core.config import get_settings
from app.mock_ai import narration
from app.mock_ai.provider import LLMRequest, LLMResponse, _tokenize

log = logging.getLogger("archiq.llm")

# Replies that are fixed text, or that report a failure to understand: the template is the right answer.
FIXED_TASKS = {"copilot.help", "copilot.unknown"}

SYSTEM = (
    "You are ArchIQ, an assistant for enterprise architects at an insurance company. "
    "You are given a task name, structured FACTS computed by deterministic engines, and a DRAFT written by a rule-based "
    "narrator. Write the final answer for the architect.\n"
    "Rules:\n"
    "1. Use ONLY the facts. Never invent applications, teams, standards, counts, dates, costs or percentages.\n"
    "2. Every number and every name in your answer must appear in the facts or the draft. Do not add up, average or round figures.\n"
    "3. Keep the draft's meaning and its conclusions. You may reorder, merge sentences and improve the wording.\n"
    "4. Plain, direct language for a busy reader. No headings, no bullet lists unless the draft uses them, no markdown "
    "decoration, no greeting, no mention of facts, drafts or rules.\n"
    "5. About the same length as the draft or shorter. If the facts show a problem, say what to do about it in one sentence."
)

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUM.findall(text)}


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


class AzureOpenAIProvider:
    name = "azure_openai"

    def __init__(self, client: Any | None = None) -> None:
        s = get_settings()
        self.settings = s
        self.deployment = s.azure_openai_deployment
        if client is None:
            from openai import AsyncAzureOpenAI

            key = s.azure_openai_api_key.get_secret_value()
            if not s.azure_openai_endpoint or not key:
                raise RuntimeError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must both be set.")
            client = AsyncAzureOpenAI(
                api_key=key,
                azure_endpoint=s.azure_openai_endpoint,
                api_version=s.azure_openai_api_version,
                timeout=s.llm_timeout,
                max_retries=1,
            )
        self.client = client
        self._cache: OrderedDict[str, LLMResponse] = OrderedDict()
        self._sem = asyncio.Semaphore(max(1, s.llm_concurrency))
        self.stats = {"calls": 0, "ok": 0, "cached": 0, "fallbacks": 0, "last_error": None}

    # ------------------------------------------------------------------ prompt
    def _messages(self, req: LLMRequest, draft: str) -> list[dict[str, str]]:
        user = f"TASK: {req.task}\n\nFACTS (JSON):\n{_canon(req.input)}\n\nDRAFT:\n{draft}\n\nWrite the final answer now."
        return [{"role": "system", "content": req.system or SYSTEM}, {"role": "user", "content": user}]

    def _call_args(self, req: LLMRequest, draft: str) -> dict[str, Any]:
        s = self.settings
        args: dict[str, Any] = dict(model=self.deployment, messages=self._messages(req, draft), max_completion_tokens=s.llm_max_tokens)
        if s.llm_reasoning_effort:
            args["reasoning_effort"] = s.llm_reasoning_effort
        return args

    # ---------------------------------------------------------------- generate
    def _fallback(self, text: str, confidence: float, meta: dict, why: str) -> LLMResponse:
        self.stats["fallbacks"] += 1
        self.stats["last_error"] = why
        log.warning("LLM fallback to built-in narrator: %s", why)
        return LLMResponse(text=text, confidence=confidence, meta={**meta, "provider": "mock", "fallback": why})

    async def generate(self, req: LLMRequest) -> LLMResponse:
        draft, conf, meta = narration.render(req.task, req.input)
        if req.task in FIXED_TASKS:
            return LLMResponse(text=draft, confidence=conf, meta={**meta, "provider": "mock"})

        key = hashlib.sha256(f"{self.deployment}|{req.task}|{_canon(req.input)}".encode()).hexdigest()
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            self.stats["cached"] += 1
            return hit

        self.stats["calls"] += 1
        try:
            async with self._sem:
                r = await asyncio.wait_for(self.client.chat.completions.create(**self._call_args(req, draft)), self.settings.llm_timeout + 5)
            choice = r.choices[0]
            text = (choice.message.content or "").strip()
        except Exception as e:  # network, auth, quota, content filter, timeout: never break the page
            return self._fallback(draft, conf, meta, f"{type(e).__name__}: {str(e)[:160]}")

        if not text:
            return self._fallback(draft, conf, meta, f"empty answer (finish_reason={getattr(choice, 'finish_reason', '?')})")
        if self.settings.llm_verify_numbers:
            extra = _numbers(text) - _numbers(draft) - _numbers(_canon(req.input))
            if extra:
                return self._fallback(draft, conf, meta, f"answer contained figures not in the facts: {sorted(extra)[:5]}")

        usage = getattr(r, "usage", None)
        out = LLMResponse(
            text=text,
            confidence=conf,
            meta={**meta, "provider": self.name, "model": getattr(r, "model", None) or self.deployment, "tokens": getattr(usage, "total_tokens", None)},
        )
        self.stats["ok"] += 1
        self._cache[key] = out
        while len(self._cache) > 512:
            self._cache.popitem(last=False)
        return out

    async def stream(self, req: LLMRequest) -> AsyncIterator[str]:  # type: ignore[override]
        # The answer is checked as a whole before anything is shown, so it is generated first and then released
        # in word-sized pieces. A half-streamed answer could not be withdrawn if it failed the figures check.
        resp = await self.generate(req)
        for chunk in _tokenize(resp.text):
            yield chunk
            await asyncio.sleep(0.008)

    # ------------------------------------------------------------------ status
    async def ping(self, prompt: str = "What is the capital of India? Answer in one word.") -> dict[str, Any]:
        r = await asyncio.wait_for(
            self.client.chat.completions.create(model=self.deployment, messages=[{"role": "user", "content": prompt}], max_completion_tokens=200, reasoning_effort="minimal"),
            self.settings.llm_timeout + 5,
        )
        return {"answer": (r.choices[0].message.content or "").strip(), "model": getattr(r, "model", self.deployment)}
