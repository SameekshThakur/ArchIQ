"""Check the Azure OpenAI settings in backend/.env with one small call, and show one real narration.

    cd backend && python scripts/check_llm.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.mock_ai.provider import LLMRequest, get_provider  # noqa: E402


async def main() -> int:
    s = get_settings()
    print(f"PROVIDER={s.provider}  endpoint={s.azure_openai_endpoint or '(not set)'}  deployment={s.azure_openai_deployment}  key={'set' if s.azure_openai_api_key.get_secret_value() else 'NOT SET'}")
    p = get_provider()
    if not hasattr(p, "ping"):
        print("Not using the real model. Set PROVIDER=azure_openai and the AZURE_OPENAI_* values in backend/.env.")
        return 1
    try:
        print("Ping:", await p.ping())
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        return 2
    facts = dict(count=3, filter="critical", target="Oracle 11g", names=["Claims Core", "Policy Admin", "Billing"], critical=2, kind="database", workflows=4, top_path="Claims Core -> Oracle 11g", note="")
    r = await p.generate(LLMRequest(task="copilot.list_dependents", input=facts))
    print("\nSample narration:", r.text, "\n", r.meta)
    return 0


raise SystemExit(asyncio.run(main()))
