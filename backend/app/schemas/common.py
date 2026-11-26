from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Evidence(BaseModel):
    kind: str  # asset | document | rule | finding | standard | integration
    id: str
    label: str


class TraceStep(BaseModel):
    label: str
    detail: str | None = None
    duration_ms: int = 0


class AIMeta(BaseModel):
    """Attached to every AI output: powers the 'AI-generated · confidence 0.91 · view evidence' footer."""

    confidence: float
    evidence: list[Evidence] = Field(default_factory=list)
    reasoning_steps: list[TraceStep] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    provider: str = "mock"
    summary: str | None = None
    task: str | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Health(BaseModel):
    status: str
    version: str
    provider: str
    seeded_entities: dict[str, int]


Json = dict[str, Any]


def ai_meta(steps: list[tuple[str, str, int]], confidence: float, evidence: list[tuple[str, str, str]]) -> dict:
    return AIMeta(
        confidence=round(confidence, 2),
        evidence=[Evidence(kind=k, id=i, label=l) for k, i, l in evidence],
        reasoning_steps=[TraceStep(label=a, detail=b, duration_ms=c) for a, b, c in steps],
    ).model_dump()
