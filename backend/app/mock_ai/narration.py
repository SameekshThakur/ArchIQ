"""Narration registry used by MockLLMProvider. # MOCK

Each task maps to a Jinja2 template that turns structured facts (computed by the real engines) into prose.
A real LLM would receive the same `task` + `input` and write the prose itself.
"""

from __future__ import annotations

from typing import Any, Callable

from jinja2 import Environment, StrictUndefined

import re


def _mk(trim: bool) -> Environment:
    e = Environment(undefined=StrictUndefined, trim_blocks=trim, lstrip_blocks=True, autoescape=False, keep_trailing_newline=False)
    e.filters["plural"] = lambda n, one, many=None: one if n == 1 else (many or one + "s")
    e.filters["commas"] = lambda xs: ", ".join(str(x) for x in xs)
    e.filters["money"] = lambda k: f"${k / 1000:.1f}M" if k >= 1000 else f"${k:,.0f}k"
    return e


env = _mk(True)  # code / document templates (Terraform, OpenAPI, ADR markdown)
prose_env = _mk(False)  # narration: newlines after block tags are kept; blank lines are collapsed below


def _clean(text: str) -> str:
    return re.sub(r"\n\s*\n+", "\n", text).strip()

Handler = Callable[[dict[str, Any]], tuple[str, float, dict]]
_registry: dict[str, Handler] = {}
_loaded = False


def template(task: str, source: str, confidence: float = 0.9) -> None:
    """Register a pure-template narration task."""
    tpl = prose_env.from_string(source)
    _registry[task] = lambda data: (_clean(tpl.render(**data)), confidence, {})


def handler(task: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _registry[task] = fn
        return fn

    return deco


def render_template(source: str, **ctx: Any) -> str:
    return env.from_string(source).render(**ctx).strip()


def render(task: str, data: dict[str, Any]) -> tuple[str, float, dict]:
    global _loaded
    if not _loaded:
        import app.mock_ai.handlers  # noqa: F401  (registers all templates)

        _loaded = True
    fn = _registry.get(task)
    if not fn:
        return (f"No narration template is registered for task '{task}'.", 0.4, {})
    return fn(data)
