import subprocess
import sys
import textwrap

from app.mock_ai.copilot import engine
from app.mock_ai.copilot.suggestions import SUGGESTIONS
from app.mock_ai.generators import blueprints, design
from app.mock_ai.provider import LLMRequest, MockLLMProvider
from app.mock_ai.scoring import debt


def test_every_suggestion_answers_and_narrates():
    import asyncio

    p = MockLLMProvider()
    for q in SUGGESTIONS:
        r = engine.answer(q)
        assert r["intent"] != "unknown", q
        out = asyncio.run(p.generate(LLMRequest(task=f"copilot.{r['intent']}", input=r["facts"])))
        assert len(out.text) > 20 and "{{" not in out.text, q


def test_debt_scores_in_range():
    for s in debt.app_scores().values():
        assert 0 <= s["overall"] <= 100
        assert all(0 <= v <= 100 for v in s["scores"].values())


def test_decision_matrix_ranking_and_sensitivity():
    ev = design.evaluate({})
    assert [r["score"] for r in ev["ranking"]] == sorted((r["score"] for r in ev["ranking"]), reverse=True)
    assert ev["recommendation"]["option"] == ev["ranking"][0]["option"]


def test_every_pattern_has_blueprint_and_zip(store):
    for p in store.patterns:
        assert blueprints.generate(p["id"]) and blueprints.bundle_zip(p["id"])[:2] == b"PK"


def test_results_do_not_depend_on_hash_randomisation():
    code = textwrap.dedent("""
        from app.mock_ai.graph import analysis as G
        from app.mock_ai.rules import assessment
        from app.mock_ai.generators import documents as D
        print(len(G.spofs()), [x['name'] for x in G.spofs()][:4], len(assessment.findings()), len(D.conflicts()), len(D.gaps()))
    """)
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={"PYTHONHASHSEED": str(h), "AI_LATENCY": "0", "PATH": ""}, cwd=".").stdout for h in (1, 7, 99)}
    assert len(outs) == 1 and outs != {""}
