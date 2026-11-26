"""Blueprint Intelligence Studio: catalogue, requirement reading, ranking, build, validation, gaps, export and governance hand-off."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.mock_ai.generators import studio_catalog as cat
from app.mock_ai.generators import studio_export as export
from app.mock_ai.rules import standards as std
from app.mock_ai.rules import studio as engine
from app.mock_ai.rules import studio_requirements as reqs
from app.repositories import persist

RAG_TEXT = ("We need an AI assistant for claims adjusters that answers questions about policy wordings and claim files stored in SharePoint, with citations back to the source document. "
            "Use Azure OpenAI. 99.9% availability, RTO of 4 hours, RPO 15 minutes. Response time under 2.5 seconds for about 40 requests per second. "
            "Customer PII so GDPR applies. Internal adjusters only. Data must stay in the EU.")
LEGACY_TEXT = "Replace the Claims Mainframe Core incrementally. We will migrate the legacy mainframe features to new microservices while Claims Payments Hub keeps running side by side."
KINDS = ("studio_design", "arb_submission")
API = "/api/v1/studio"


@pytest.fixture(autouse=True)
def _clean():
    def wipe():
        for kind in KINDS:
            for row in persist.list_items(kind, 1000):
                persist.delete_item(kind, row["id"])

    wipe()
    yield
    wipe()


def _create(client, text=RAG_TEXT, **kw):
    r = client.post(f"{API}/designs", json=dict(text=text, **kw))
    assert r.status_code == 200, r.text
    return r.json()


def _gap(d, gid):
    return next((g for g in d["validation"]["gaps"] if g["id"] == gid), None)


# ------------------------------------------------------------------ catalogue
def test_all_twelve_blueprints_become_graphs():
    from app.mock_ai.generators.blueprints import BLUEPRINTS

    assert len(BLUEPRINTS) == 12
    for pid in BLUEPRINTS:
        g = cat.blueprint_graph(pid)
        assert len(g["nodes"]) >= 3 and len(g["edges"]) >= 2, pid
        assert all(n["role"] in cat.ROLE_LABEL for n in g["nodes"]), pid
        ids = {n["id"] for n in g["nodes"]}
        assert all(e["source"] in ids and e["target"] in ids for e in g["edges"]), pid


def test_the_estate_is_recognised_by_exact_name_only():
    g = cat.blueprint_graph("PAT-003")
    core = next(n for n in g["nodes"] if n.get("estate_id") == "APP-002")
    assert core["name"] == "Claims Mainframe Core" and core["role"] == "external"
    # a node that merely sounds like an application is not linked
    assert all(n.get("estate_id") is None for n in cat.blueprint_graph("PAT-011")["nodes"])


def test_catalog_endpoint_lists_every_choice(client):
    c = client.get(f"{API}/catalog").json()
    assert len(c["blueprints"]) == 12 and {x["id"] for x in c["clouds"]} == {"azure", "aws", "gcp", "hybrid"}
    assert {"aks_cluster", "key_vault"} <= set(c["prop_schema"]) and c["approved_regions"]
    assert all(b["defaults"]["cloud"] == "azure" for b in c["blueprints"])


# ------------------------------------------------------------------ requirements
def test_requirements_are_read_with_evidence():
    r = reqs.extract(RAG_TEXT)
    assert r["nfr"] == dict(availability="99.9", rto_hours=4, rpo_minutes=15, latency_ms=2500, throughput_tps=40, compliance=["GDPR"])
    assert r["tier"] == "tier2" and r["exposure"] == "internal" and r["classification"] == "confidential" and r["residency"]
    f = next(x for x in r["facts"] if x["key"] == "availability")
    assert "99.9% availability" in f["evidence"], "a decimal point must not split the sentence"
    assert r["hints"]["cloud"]["value"] == "azure" and r["hints"]["llm"]["value"] == "azure_openai"


def test_nothing_is_invented_when_the_text_is_silent():
    r = reqs.extract("Build a thing for the business that does stuff for people every day.")
    assert r["nfr"] == {} and r["tier"] is None and r["exposure"] is None and r["classification"] is None and not r["hints"]
    assert set(r["nfr_missing"]) == {"availability", "rto_hours", "rpo_minutes", "latency_ms", "throughput_tps", "compliance"}


def test_estate_systems_named_in_the_text_are_linked():
    r = reqs.extract(LEGACY_TEXT)
    assert {s["id"] for s in r["systems"]} == {"APP-002", "APP-005"}


# ------------------------------------------------------------------ recommendation
def test_rag_text_recommends_rag_with_reasons_and_alternatives():
    rec = reqs.recommend(reqs.extract(RAG_TEXT))
    top = rec["recommended"]
    assert top["id"] == "PAT-005" and top["rationale"] and all(m["evidence"] for m in top["rationale"] if m["term"])
    assert len(rec["alternatives"]) == 3 and all(a["why_not"] and a["choose_when"] for a in rec["alternatives"])
    s1, s2 = rec["ranked"][0]["score"], rec["ranked"][1]["score"]
    assert top["confidence"] == round(0.2 + 0.5 * min(1.0, s1 / 12) + 0.3 * ((s1 - s2) / s1), 2), "the confidence is a formula, not a guess"


def test_legacy_text_recommends_strangler_fig_and_suggests_an_acl():
    rec = reqs.recommend(reqs.extract(LEGACY_TEXT))
    assert rec["recommended"]["id"] == "PAT-003"
    assert any(c["id"] == "PAT-009" for c in rec["combine"])


def test_a_vague_text_gets_no_recommendation():
    rec = reqs.recommend(reqs.extract("We would like a new system for the business that is good."))
    assert rec["recommended"] is None and rec["needs_more_detail"] and rec["message"]


def test_the_ranking_is_repeatable():
    a = reqs.recommend(reqs.extract(RAG_TEXT))
    b = reqs.recommend(reqs.extract(RAG_TEXT))
    assert [(r["id"], r["score"]) for r in a["ranked"]] == [(r["id"], r["score"]) for r in b["ranked"]]


# ------------------------------------------------------------------ build
def _sel(pid, **over):
    s = cat.default_selections(pid)
    s.update(over)
    return s


def test_choices_change_the_components():
    az = engine.build("PAT-005", _sel("PAT-005", posture=[]))
    llm = next(n for n in az["nodes"] if n["role"] == "ai_llm")
    assert (llm["type"], llm["technology"]) == ("azure_openai", "Azure OpenAI")
    aws = engine.build("PAT-005", _sel("PAT-005", cloud="aws", deployment="eks", llm="bedrock", posture=[]))
    assert next(n for n in aws["nodes"] if n["role"] == "ai_llm")["type"] == "x_llm"
    assert next(n for n in aws["nodes"] if n["role"] == "compute")["technology"] == "Python 3.11"
    none = engine.build("PAT-005", _sel("PAT-005", llm="none", posture=[]))
    assert not any(n["role"] == "ai_llm" for n in none["nodes"]) and none["notes"]


def test_nothing_is_assumed_beyond_platform_defaults_and_choices():
    arch = engine.build("PAT-005", _sel("PAT-005", posture=[], classification=None))
    idx = next(n for n in arch["nodes"] if n["role"] == "ai_search")
    assert idx["props"]["public_network_access"] is True and idx["prop_origin"]["public_network_access"] == "Azure platform default"
    db = next(n for n in arch["nodes"] if n["role"] == "database")
    assert "data_classification" not in db["props"] and "backup" not in db["props"]
    llm = next(n for n in arch["nodes"] if n["role"] == "ai_llm")
    assert llm["props"]["public_network_access"] is False, "the blueprint's own diagram says 'private endpoint'"
    assert llm["prop_origin"]["public_network_access"] == "stated in the blueprint diagram"


def test_controls_set_the_properties_they_promise():
    arch = engine.build("PAT-005", _sel("PAT-005", posture=["private_endpoints", "tls12", "key_vault_secrets", "managed_identity"]))
    idx = next(n for n in arch["nodes"] if n["role"] == "ai_search")
    assert idx["props"]["public_network_access"] is False and idx["props"]["tls_min"] == "1.2"
    assert any(n["id"] == "KV-CTL" and n["origin"] == "control" for n in arch["nodes"]), "secrets in Key Vault adds the vault"
    assert next(n for n in arch["nodes"] if n["role"] == "compute")["props"]["secrets_store"] == "key_vault"


def test_edits_are_replayed_over_the_choices():
    ops = [dict(op="add_node", id="CACHE1", role="database", name="Session cache"), dict(op="add_edge", source="ORCH", target="CACHE1", label="sessions"),
           dict(op="update_node", id="IDX", name="Policy index", props=dict(tls_min="1.3")), dict(op="remove_node", id="AUD"), dict(op="move_node", id="ORCH", x=500, y=40)]
    arch = engine.build("PAT-005", _sel("PAT-005", posture=["tls12"]), ops)
    by = {n["id"]: n for n in arch["nodes"]}
    assert "CACHE1" in by and "AUD" not in by and by["IDX"]["name"] == "Policy index"
    assert by["IDX"]["props"]["tls_min"] == "1.3" and by["IDX"]["prop_origin"]["tls_min"] == "edited", "an edit wins over a control"
    assert by["ORCH"]["pos"] == dict(x=500.0, y=40.0)
    assert any(e["source"] == "ORCH" and e["target"] == "CACHE1" for e in arch["edges"])
    assert not any("AUD" in (e["source"], e["target"]) for e in arch["edges"])
    changed = engine.build("PAT-005", _sel("PAT-005", cloud="aws", deployment="eks", posture=["tls12"]), ops)
    assert next(n for n in changed["nodes"] if n["id"] == "CACHE1")["type"] == "x_database", "an added node follows the cloud that was chosen later"


def test_edits_that_no_longer_apply_are_reported_not_hidden():
    arch = engine.build("PAT-005", _sel("PAT-005"), [dict(op="remove_node", id="NOPE"), dict(op="add_edge", source="ORCH", target="ORCH")])
    assert len(arch["skipped_ops"]) == 2 and all(x["reason"] for x in arch["skipped_ops"])


def test_bad_inputs_are_rejected_with_a_reason():
    from app.core.errors import BadRequest

    with pytest.raises(BadRequest):
        engine.normalise_selections(dict(cloud="mars"), "PAT-005")
    with pytest.raises(BadRequest):
        engine.build("PAT-005", _sel("PAT-005"), [dict(op="explode")])
    with pytest.raises(BadRequest):
        engine.build("PAT-005", _sel("PAT-005"), [dict(op="add_node", id="bad id!", role="compute")])
    with pytest.raises(BadRequest):
        engine.clean_nfr(dict(availability="150"))


# ------------------------------------------------------------------ validation
def test_validation_is_the_existing_engines_not_a_new_score():
    arch = engine.build("PAT-005", _sel("PAT-005"))
    val = engine.validate(arch, dict(availability="99.9"), "tier2", [], "t", "Claims")
    direct = std.check_design(dict(name="t", components=engine.components_of(arch), format="json"))
    assert [(r["standard_id"], r["status"]) for r in val["standards"]["results"]] == [(r["standard_id"], r["status"]) for r in direct["results"]]
    from app.mock_ai.rules import review

    rv = review.review(dict(id="X", title="t", domain="Claims", tier="tier2", nfr=dict(availability="99.9"), components=engine.components_of(arch), linked_apps=[], summary="", stage="draft"))
    assert val["readiness"] == rv["readiness"] and val["engine_verdict"] == rv["verdict"]


def test_turning_a_control_off_creates_a_critical_gap_with_a_working_fix():
    on = engine.validate(engine.build("PAT-005", _sel("PAT-005", posture=["private_endpoints"])), {}, "tier2", [], "t", "c")
    off = engine.validate(engine.build("PAT-005", _sel("PAT-005", posture=[])), {}, "tier2", [], "t", "c")
    assert not any(g["id"] == "std:STD-SEC-014" for g in on["gaps"])
    g = next(g for g in off["gaps"] if g["id"] == "std:STD-SEC-014")
    assert g["severity"] == "critical" and g["fix"]["posture_add"] == ["private_endpoints"] and g["evidence"] and g["components"]
    assert off["verdict"] == "no_go" and off["readiness"] < on["readiness"]


def test_every_automatic_fix_clears_the_gap_it_belongs_to():
    req = reqs.extract(RAG_TEXT)
    for pid in ("PAT-001", "PAT-005", "PAT-006", "PAT-012"):
        inputs = dict(blueprint_id=pid, selections=engine.normalise_selections(_sel(pid, exposure="internet", posture=[]), pid), nfr={}, ops=[], linked_apps=[])
        for _ in range(40):
            arch = engine.build(pid, inputs["selections"], inputs["ops"])
            val = engine.validate(arch, inputs["nfr"], "tier2", [], "t", "c", req)
            todo = next((g for g in val["gaps"] if g["fix"]), None)
            if not todo:
                break
            f = todo["fix"]
            value = None
            if f.get("input"):
                i = f["input"]
                value = (i.get("options") or ["x"])[0] if i["kind"] == "choice" else 365 if i["kind"] == "number" else "GDPR"
            new = engine.apply_fix(inputs, f, value)
            new["selections"] = engine.normalise_selections(new["selections"], pid)
            new["nfr"] = engine.clean_nfr(new["nfr"])
            after = engine.validate(engine.build(pid, new["selections"], new["ops"]), new["nfr"], "tier2", [], "t", "c", req)
            assert todo["id"] not in {g["id"] for g in after["gaps"]}, f"{pid}: '{f['label']}' did not clear {todo['id']}"
            inputs = new
        else:
            pytest.fail(f"{pid}: fixes never converged")


def test_other_clouds_are_listed_as_not_assessed_and_cannot_score_a_go():
    arch = engine.build("PAT-005", _sel("PAT-005", cloud="aws", deployment="eks", llm="bedrock", databases=["cosmos_db"], posture=[p["id"] for p in cat.POSTURE]))
    val = engine.validate(arch, dict(availability="99.9", rto_hours=4, rpo_minutes=15, latency_ms=2000, throughput_tps=10, compliance=["GDPR"]), "tier2", [], "t", "c")
    assert val["coverage"]["percent"] < engine.COVERAGE_FLOOR and val["coverage"]["not_assessed"]
    assert val["verdict"] != "go" and any("could be assessed" in c for c in val["conditions"])


def test_a_prohibited_technology_is_a_finding_with_alternatives():
    arch = engine.build("PAT-012", _sel("PAT-012", databases=["oracle_12c"], backend="java8"))
    val = engine.validate(arch, {}, "tier2", [], "t", "c")
    ora = next(g for g in val["gaps"] if g["id"].startswith("std:STD-TECH-006"))
    assert ora["severity"] == "high" and len(ora["fix"]["alternatives"]) == 2
    assert any(g["id"].startswith("std:STD-TECH-005") for g in val["gaps"]), "Java 8 is deprecated"


def test_region_outside_europe_conflicts_with_stated_residency():
    req = reqs.extract(RAG_TEXT)
    val = engine.validate(engine.build("PAT-005", _sel("PAT-005", region="eastus2")), {}, "tier2", [], "t", "c", req)
    g = next(g for g in val["gaps"] if g["id"] == "residency:region")
    assert g["severity"] == "high" and "Data must stay in the EU" in g["detail"]


def test_a_removed_blueprint_component_is_called_out_and_restorable():
    inp = dict(blueprint_id="PAT-005", selections=_sel("PAT-005"), nfr={}, ops=[dict(op="remove_node", id="IDX")], linked_apps=[])
    val = engine.validate(engine.build("PAT-005", inp["selections"], inp["ops"]), {}, "tier2", [], "t", "c")
    g = next(g for g in val["gaps"] if g["id"].startswith("missing:role-"))
    restored = engine.apply_fix(inp, g["fix"])
    assert restored["ops"] == []


def test_gateway_is_missing_for_internet_exposure_and_the_fix_adds_it():
    sel = _sel("PAT-006", exposure="internet", posture=[])
    arch = engine.build("PAT-006", sel, [dict(op="remove_node", id="GW")])
    val = engine.validate(arch, {}, "tier2", [], "t", "c")
    g = next((g for g in val["gaps"] if g["id"] == "missing:gateway"), None)
    assert g and g["severity"] == "high" and any(o["op"] == "add_node" for o in g["fix"]["ops"])


def test_terraform_round_trip_agrees_with_the_design():
    for pid in ("PAT-005", "PAT-006", "PAT-012"):
        sel = _sel(pid, posture=[p["id"] for p in cat.POSTURE], retention_days=90, classification="confidential")
        arch = engine.build(pid, sel)
        files, tfmap = export.terraform(arch, dict(title="Claims copilot", owner="Claims Platform"))
        checks = export.check_terraform(arch, files, tfmap)
        bad = [c for c in checks if c["status"] == "fail"]
        assert not bad, f"{pid}: {bad}"
        assert any(c["label"].endswith("agrees with the design") for c in checks)


def test_the_hcl_checker_would_catch_a_mismatch():
    arch = engine.build("PAT-012", _sel("PAT-012", posture=["private_endpoints", "tls12", "diagnostics", "mandatory_tags"]))
    files, tfmap = export.terraform(arch, dict(title="x", owner="o"))
    files["infra/terraform/main.tf"] = files["infra/terraform/main.tf"].replace("public_network_access_enabled = false", "public_network_access_enabled = true")
    assert any(c["status"] == "fail" for c in export.check_terraform(arch, files, tfmap))


# ------------------------------------------------------------------ the whole flow through the API
def test_full_flow_from_requirements_to_the_review_queue(client):
    d = _create(client)
    n = d["n"]
    assert d["blueprint_id"] == "PAT-005" and d["recommendation"]["recommended"]["confidence"] > 0.5 and d["ai"]["recommendation"]["summary"]
    assert d["architecture"]["nodes"] and d["validation"]["gaps"] is not None and d["status"] == "draft"
    # customise: remove private endpoints and the critical gap appears
    post = [p for p in d["selections"]["posture"] if p != "private_endpoints"]
    d = client.patch(f"{API}/designs/{n}", json=dict(selections=dict(posture=post))).json()
    gap = _gap(d, "std:STD-SEC-014")
    assert gap and gap["severity"] == "critical"
    # accept the recommendation
    d = client.post(f"{API}/designs/{n}/decisions", json=dict(gap_id="std:STD-SEC-014", action="accept")).json()
    assert _gap(d, "std:STD-SEC-014") is None and "private_endpoints" in d["selections"]["posture"]
    assert any(x["id"] == "std:STD-SEC-014" and x["status"] == "accepted" for x in d["validation"]["resolved"])
    # edit the diagram
    ops = [dict(op="add_node", id="CACHE1", role="database", name="Session cache"), dict(op="add_edge", source="ORCH", target="CACHE1", label="sessions")]
    d = client.put(f"{API}/designs/{n}/ops", json=dict(ops=ops)).json()
    assert any(x["id"] == "CACHE1" for x in d["architecture"]["nodes"])
    bad = client.put(f"{API}/designs/{n}/ops", json=dict(ops=ops + [dict(op="add_edge", source="NOPE", target="ORCH")]))
    assert bad.status_code == 400 and "different components" in bad.json()["error"]["message"]
    # validation, version, restore
    d = client.post(f"{API}/designs/{n}/validate").json()
    assert d["status"] == "validated" and d["narration"]["summary"] and d["recorded_validation"]["readiness"] == d["validation"]["readiness"]
    d = client.post(f"{API}/designs/{n}/versions", json=dict(label="baseline")).json()
    assert d["versions"][-1]["label"] == "baseline"
    d = client.put(f"{API}/designs/{n}/ops", json=dict(ops=[])).json()
    assert d["status"] == "draft" and not any(x["id"] == "CACHE1" for x in d["architecture"]["nodes"])
    d = client.post(f"{API}/designs/{n}/versions/1/restore").json()
    assert any(x["id"] == "CACHE1" for x in d["architecture"]["nodes"])
    # export
    doc = client.get(f"{API}/designs/{n}/export/document").json()
    assert "# Target architecture" in doc["markdown"] and "```mermaid" in doc["markdown"] and "as declared" in doc["markdown"]
    z = client.get(f"{API}/designs/{n}/export/starter.zip")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert any(x.endswith("diagrams/architecture.svg") for x in names) and any(x.endswith("infra/terraform/main.tf") for x in names) and any(x.endswith("config/standards-input.json") for x in names)
    readme = zipfile.ZipFile(io.BytesIO(z.content)).read(next(x for x in names if x.endswith("/README.md"))).decode()
    assert "not deployable infrastructure" in readme and "terraform validate" in readme and "Not checked" in readme
    assert client.get(f"{API}/designs/{n}/export/diagram.svg").text.startswith("<svg")
    # governance
    s = client.post(f"{API}/designs/{n}/submit", json=dict(notes="for the next board")).json()
    arb = s["submission"]["arb_id"]
    assert arb.startswith("ARB-") and s["status"] == "submitted"
    rv = client.get(f"/api/v1/reviews/{arb}").json()
    assert rv["review"]["readiness"] == s["validation"]["readiness"], "the review queue runs the same engine on the same components"
    assert arb in [r["id"] for r in client.get("/api/v1/reviews").json()["items"]]
    assert client.post(f"{API}/designs/{n}/submit", json={}).status_code == 400, "the same version cannot be submitted twice"
    # change and resubmit: same review record, new version
    d = client.patch(f"{API}/designs/{n}", json=dict(selections=dict(region="northeurope"))).json()
    assert d["status"] == "changed_after_submission"
    s2 = client.post(f"{API}/designs/{n}/submit", json={}).json()
    assert s2["submission"]["arb_id"] == arb and s2["submission"]["version"] > s["submission"]["version"]
    assert len([r for r in client.get("/api/v1/reviews").json()["items"] if r["id"] == arb]) == 1
    assert client.delete(f"{API}/designs/{n}").status_code == 400, "a submitted design is part of the review record"


def test_a_critical_gap_blocks_submission_until_the_risk_is_accepted_with_a_reason(client):
    d = _create(client)
    n = d["n"]
    d = client.patch(f"{API}/designs/{n}", json=dict(selections=dict(llm="public_api"))).json()
    assert _gap(d, "std:STD-AI-004")["severity"] == "critical"
    r = client.post(f"{API}/designs/{n}/submit", json={})
    assert r.status_code == 400 and "critical" in r.json()["error"]["message"].lower()
    assert client.post(f"{API}/designs/{n}/decisions", json=dict(gap_id="std:STD-AI-004", action="risk_accept", note="short")).status_code == 400
    d = client.post(f"{API}/designs/{n}/decisions", json=dict(gap_id="std:STD-AI-004", action="risk_accept", note="Approved exception for a pilot until 2027-03, no enterprise data")).json()
    g = _gap(d, "std:STD-AI-004")
    assert g["state"] == "risk_accepted" and d["validation"]["verdict"] == "no_go", "an accepted risk is still a finding, and it does not lift the verdict"
    s = client.post(f"{API}/designs/{n}/submit", json={})
    assert s.status_code == 200
    queue = client.get(f"/api/v1/reviews/{s.json()['submission']['arb_id']}").json()
    assert queue["review"]["verdict"] == "no_go"
    saved = [r for r in persist.list_items("arb_submission", 10)][0]
    assert saved["accepted_risks"][0]["note"].startswith("Approved exception")


def test_modify_picks_an_alternative_and_inputs_are_validated(client):
    d = _create(client)
    n = d["n"]
    d = client.patch(f"{API}/designs/{n}", json=dict(selections=dict(databases=["oracle_12c"]))).json()
    gid = next(g["id"] for g in d["validation"]["gaps"] if g["id"].startswith("std:STD-TECH-006"))
    assert client.post(f"{API}/designs/{n}/decisions", json=dict(gap_id=gid, action="modify")).status_code == 400
    d = client.post(f"{API}/designs/{n}/decisions", json=dict(gap_id=gid, action="modify", alternative=0)).json()
    assert d["selections"]["databases"] == ["oracle_19c"] and d["decisions"][gid]["status"] == "modified"
    cls = next((g for g in d["validation"]["gaps"] if g["id"] == "std:STD-SEC-010"), None)
    if cls:
        assert client.post(f"{API}/designs/{n}/decisions", json=dict(gap_id=cls["id"], action="accept", value="top-secret")).status_code == 400
        d = client.post(f"{API}/designs/{n}/decisions", json=dict(gap_id=cls["id"], action="accept", value="restricted")).json()
        assert d["selections"]["classification"] == "restricted"
    assert client.post(f"{API}/designs/{n}/decisions", json=dict(gap_id="std:NOPE", action="accept")).status_code == 404


def test_choosing_a_different_blueprint_needs_a_reason_and_resets_the_design(client):
    d = _create(client)
    n = d["n"]
    assert client.put(f"{API}/designs/{n}/blueprint", json=dict(blueprint_id="PAT-001")).status_code == 400
    assert client.put(f"{API}/designs/{n}/blueprint", json=dict(blueprint_id="PAT-099", reason="because")).status_code == 400
    d = client.put(f"{API}/designs/{n}/blueprint", json=dict(blueprint_id="PAT-001", reason="We also expose APIs")).json()
    assert d["blueprint_id"] == "PAT-001" and d["blueprint_choice"]["overridden"] and d["ops"] == []
    assert "different from the recommendation" in d["workflow"][-1]["note"]


def test_a_vague_text_creates_a_design_with_no_blueprint_until_one_is_chosen(client):
    d = _create(client, text="We would like a new system for the business that is good.")
    assert d["blueprint_id"] is None and d["architecture"] is None and d["recommendation"]["needs_more_detail"]
    assert client.patch(f"{API}/designs/{d['n']}", json=dict(title="Mine")).status_code == 400
    d = client.put(f"{API}/designs/{d['n']}/blueprint", json=dict(blueprint_id="PAT-012", reason="We know what we need")).json()
    assert d["architecture"]["nodes"]


def test_request_validation(client):
    assert client.post(f"{API}/designs", json=dict(text="too short")).status_code == 422
    assert client.get(f"{API}/designs/999999").status_code == 404
    d = _create(client)
    assert client.patch(f"{API}/designs/{d['n']}", json=dict(selections=dict(cloud="mars"))).status_code == 400
    assert client.patch(f"{API}/designs/{d['n']}", json=dict(nfr=dict(availability="12"))).status_code == 400
    assert client.patch(f"{API}/designs/{d['n']}", json=dict(linked_apps=["APP-9999"])).status_code == 400
    assert client.post(f"{API}/designs/{d['n']}/decisions", json=dict(gap_id="std:STD-SEC-014", action="explode")).status_code in (400, 404)


def test_designs_survive_a_restart(client):
    d = _create(client, title="Persisted design")
    persist.close()  # the next call reopens the same database file
    again = client.get(f"{API}/designs/{d['n']}").json()
    assert again["title"] == "Persisted design" and again["architecture"]["nodes"]
    assert [x["title"] for x in client.get(f"{API}/designs").json()["items"]] == ["Persisted design"]


def test_the_studio_leaves_the_seeded_review_queue_alone(client):
    before = client.get("/api/v1/reviews").json()["total"]
    d = _create(client)
    assert client.get("/api/v1/reviews").json()["total"] == before, "creating or editing a design adds nothing to the queue; only a submission does"
    client.post(f"{API}/designs/{d['n']}/submit", json={})
    assert client.get("/api/v1/reviews").json()["total"] == before + 1
    assert client.get("/api/v1/reviews/ARB-2026-001").status_code == 200
    json.dumps(client.get("/api/v1/overview/summary").json())
