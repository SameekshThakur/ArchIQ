"""The Northwind Assurance story facts from the brief must hold in the seeded data and the engines built on it."""

from app.mock_ai.copilot import engine
from app.mock_ai.generators import documents as docs
from app.mock_ai.graph import analysis as G
from app.mock_ai.rules import assessment, drift


def test_exactly_17_direct_db_integrations(store):
    assert sum(1 for i in store.integrations if i["style"] == "direct_db") == 17
    assert assessment.findings()[0]["title"] == "17 direct DB integrations should move behind APIs/events"


def test_oracle_12c_used_by_9_apps_4_supporting_claims(store):
    r = engine.answer("Show all applications dependent on Oracle 12c that support Claims.")
    assert r["intent"] == "list_dependents"
    assert r["facts"]["count"] == 4
    keys = {store.by_id[row["name"]["id"]]["key"] for row in r["cards"][0]["rows"]}
    assert keys == {"GWCC", "CIP", "FSE", "CPH"}
    assert all(p["nodes"][1]["name"] == "Policy Master DB" for p in r["cards"][1]["paths"])  # every result carries its path
    total = engine.answer("Which applications depend on Oracle 12c?")
    assert total["facts"]["count"] == 9


def test_customer_api_v2_14_apps_6_workflows():
    imp = G.impact("API-0002")
    assert len(imp["direct_apps"]) == 14
    assert len(imp["workflows"]) == 6
    r = engine.answer("What is the impact of changing Customer API v2?")
    assert r["headline"] == "Changing Customer API impacts 14 applications and 6 workflows."


def test_sap_mulesoft_salesforce_snowflake_chain():
    names = [n["name"] for n in G.story_chain()]
    assert names == ["SAP S/4HANA Finance", "MuleSoft Anypoint", "Salesforce CRM", "Snowflake Data Cloud"]


def test_drift_story_and_standard_headlines():
    d = drift.items()[0]
    assert d["summary"] == "Approved design says private endpoint; deployed environment uses public endpoint."
    assert d["standard_id"] == "STD-SEC-014"
    assert engine.answer("Is Azure OpenAI approved?")["headline"] == "Azure OpenAI is approved; direct public endpoint violates policy."


def test_three_customer_master_systems_and_spofs(store):
    assert engine.answer("Which systems act as the customer master?")["facts"]["names"] and len(engine.answer("customer master systems")["facts"]["names"]) == 3
    assert len(G.spofs()) >= 5


def test_modernization_waves():
    from app.mock_ai.generators import modernization

    assert [w["name"] for w in modernization.plan("balanced")["waves"]] == ["Wave 1: APIs", "Wave 2: Data decoupling", "Wave 3: Agentification"]


def test_undocumented_policy_admin_oracle_link_is_top_gap():
    g = docs.gaps()[0]
    assert (g["app"], g["target"]) == ("Policy Admin Core", "Policy Master DB")
    assert any(c["subject"] == "Policy Admin Core" for c in docs.conflicts())


def test_counts(store):
    assert len(store.apps) == 69 and len(store.dbs) >= 45 and len(store.documents) == 60 and len(store.standards) >= 40
