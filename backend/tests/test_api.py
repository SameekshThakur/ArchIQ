import json

import pytest

GET_OK = ["/health", "/overview/summary", "/discovery/sources", "/discovery/results", "/assets", "/assets/APP-001", "/assets/API-0002", "/assets/DB-001", "/graph", "/graph?focus=APP-001&hops=2",
          "/graph/path?source=APP-027&target=APP-047", "/graph/hubs", "/documents", "/documents/summary", "/documents/conflicts", "/documents/gaps", "/documents/diagram", "/documents/DOC-005",
          "/assessment/summary", "/assessment/findings", "/assessment/findings/F-001", "/debt/heatmap", "/debt/contributors", "/debt/trends", "/debt/summary", "/impact/API-0002", "/impact/APP-057?change_type=outage",
          "/drift", "/drift/DR-001", "/target-architecture/presets", "/decisions", "/standards", "/standards/STD-SEC-014", "/reviews", "/reviews/ARB-2026-001", "/blueprints", "/blueprints/PAT-001",
          "/modernization/scenarios", "/codegen/templates", "/copilot/suggestions"]


@pytest.mark.parametrize("path", GET_OK)
def test_get_endpoints(client, path):
    r = client.get("/api/v1" + path)
    assert r.status_code == 200, r.text


def test_error_envelope(client):
    r = client.get("/api/v1/assets/NOPE-1")
    assert r.status_code == 404
    e = r.json()["error"]
    assert e["code"] == "not_found" and e["request_id"]
    assert client.post("/api/v1/copilot/query", json={"query": "x"}).status_code == 422


def test_overview_nav_badges(client):
    b = client.get("/api/v1/overview/summary").json()["nav_badges"]
    assert set(b) == {"findings", "reviews", "drift"} and b["drift"] > 0


def test_ai_envelope_present(client):
    ai = client.get("/api/v1/assessment/summary").json()["ai"]
    assert ai["summary"] and 0 < ai["confidence"] <= 1 and ai["reasoning_steps"] and ai["evidence"]


def test_copilot_query_and_stream(client):
    q = {"query": "Show all applications dependent on Oracle 12c that support Claims."}
    r = client.post("/api/v1/copilot/query", json=q).json()
    assert r["intent"] == "list_dependents" and "4 Claims applications" in r["answer"]
    with client.stream("POST", "/api/v1/copilot/stream", json=q) as s:
        body = "".join(s.iter_text())
    events = [l.split(": ", 1)[1] for l in body.splitlines() if l.startswith("event:")]
    assert events[0] == "start" and events[-1] == "done" and "token" in events and events.index("cards") > events.index("token")


def test_copilot_unknown_is_graceful(client):
    r = client.post("/api/v1/copilot/query", json={"query": "banana smoothie recipe"}).json()
    assert r["intent"] == "unknown" and r["cards"]


def test_standards_check_flags_public_openai(client):
    sample = client.get("/api/v1/standards/sample-design").json()
    r = client.post("/api/v1/standards/check", json={"design": sample["text"]}).json()
    assert r["failed"] >= 1
    assert any(x["standard_id"] == "STD-SEC-014" and x["status"] == "fail" for x in r["results"])


def test_review_verdict_and_adhoc(client):
    r = client.get("/api/v1/reviews/ARB-2026-001").json()
    assert r["review"]["verdict"] in ("go", "conditional", "no_go") and r["ai"]["summary"]
    sample = client.get("/api/v1/standards/sample-design").json()
    r2 = client.post("/api/v1/reviews/run", json={"title": "Adhoc", "design": sample["text"]}).json()
    assert r2["review"]["readiness"] <= 100


def test_decision_agent_generates_adr(client):
    r = client.post("/api/v1/decisions/adr", json={"title": "Adopt API-led connectivity", "domain": "Claims"}).json()
    assert r["number"].startswith("ADR-") and "## Decision" in r["markdown"]
    assert any(d["number"] == r["number"] for d in client.get("/api/v1/decisions").json()["items"])


def test_codegen_all_checks_pass_and_zip(client):
    g = client.post("/api/v1/codegen/generate", json={"outputs": ["terraform", "bicep", "openapi", "fastapi", "spring", "dockerfile", "ci"], "include_openai": True}).json()
    assert g["passed"] == g["total"] and g["total"] >= 15
    z = client.get(f"/api/v1/codegen/{g['id']}/download")
    assert z.headers["content-type"] == "application/zip" and z.content[:2] == b"PK"


def test_drift_actions(client):
    r = client.post("/api/v1/drift/DR-002/actions", json={"action": "exception", "days": 30}).json()
    assert r["item"]["status"] == "exception_granted"


def test_document_ingest_detects_relations(client):
    r = client.post("/api/v1/documents/ingest", json={"title": "Scratch note", "text": "Policy Admin Core stores its data in Policy Master DB. Policy Admin Core calls Customer API v2."}).json()
    assert len(r["relations"]) == 2


def test_discovery_stream(client):
    sid = client.post("/api/v1/discovery/scans").json()["id"]
    with client.stream("GET", f"/api/v1/discovery/scans/{sid}/stream") as s:
        body = "".join(s.iter_text())
    assert body.count("event: source") >= 9 and "event: done" in body
    json.loads([l for l in body.splitlines() if l.startswith("data:")][-1][5:])


def test_blueprint_summary_is_prose_not_a_python_list(client):
    s = client.get("/api/v1/blueprints/PAT-002").json()["ai"]["summary"]
    assert "[" not in s and "'" not in s
