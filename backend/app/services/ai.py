"""Thin helpers that route every AI-generated sentence through the LLMProvider."""

from __future__ import annotations

from typing import Any

from app.mock_ai.provider import LLMRequest, get_provider
from app.schemas.common import ai_meta

Step = tuple[str, str, int]


async def narrate(task: str, facts: dict[str, Any], steps: list[Step] | None = None, evidence: list[tuple[str, str, str]] | None = None, confidence: float | None = None) -> dict:
    """Return the `ai` envelope: summary text, confidence, evidence chips and the reasoning trace."""
    resp = await get_provider().generate(LLMRequest(task=task, input=facts))
    meta = ai_meta(steps or [], confidence if confidence is not None else resp.confidence, evidence or [])
    meta["summary"] = resp.text
    meta["task"] = task
    meta["provider"] = resp.meta.get("provider", get_provider().name)
    if resp.meta.get("model"):
        meta["model"] = resp.meta["model"]
    return meta


def paginate(rows: list, page: int, page_size: int) -> dict:
    page = max(1, page)
    start = (page - 1) * page_size
    return dict(items=rows[start: start + page_size], total=len(rows), page=page, page_size=page_size)


SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
CRIT_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
