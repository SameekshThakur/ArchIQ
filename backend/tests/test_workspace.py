"""The guided start: empty until used, runs end to end, cleans up after itself."""

import time
from pathlib import Path

import pytest

from app.repositories import persist
from app.services import files, workspace

SAMPLES = Path(__file__).resolve().parents[2] / "sample-files"


@pytest.fixture(autouse=True)
def _fresh_workspace():
    def clean():
        workspace.reset()
        for kind in ("connection", "connection_sync"):  # saved connections survive a reset by design, so tests clear them themselves
            for row in persist.list_items(kind, 500):
                persist.delete_item(kind, row["id"])

    clean()
    yield
    clean()


def _files(*names: str) -> list[dict]:
    out = []
    for n in names:
        e = files.extract(n, (SAMPLES / n).read_bytes())
        out.append(dict(filename=n, text=e["text"]))
    return out


def _wait(client, timeout: float = 20) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        w = client.get("/api/v1/workspace").json()
        if w["status"] != "running":
            return w
        time.sleep(0.05)
    raise AssertionError("workspace run did not finish")


def test_starts_empty_and_offers_intents_and_domains(client):
    assert client.get("/api/v1/workspace").json()["status"] == "empty"
    o = client.get("/api/v1/workspace/options").json()
    assert {i["id"] for i in o["intents"]} >= {"understand", "review", "compliance", "risk", "modernize"}
    assert "Claims" in {d["name"] for d in o["domains"]}


def test_intent_is_chosen_or_read_from_the_words():
    assert workspace.classify_intent("", "risk")["id"] == "risk"
    assert workspace.classify_intent("get this ready for ARB sign-off")["id"] == "review"
    assert workspace.classify_intent("check our terraform against the baseline")["id"] == "compliance"
    assert workspace.classify_intent("which systems are single points of failure?")["id"] == "risk"
    assert workspace.classify_intent("asdf qwer")["id"] == "understand"  # no clue: the broadest view


def test_demo_marks_the_workspace_ready_and_reset_empties_it(client):
    w = client.post("/api/v1/workspace/demo").json()
    assert w["status"] == "ready" and w["mode"] == "demo"
    assert client.get("/api/v1/workspace").json()["status"] == "ready"
    assert client.delete("/api/v1/workspace").json()["status"] == "empty"
    assert client.get("/api/v1/workspace").json()["status"] == "empty"


def test_full_run_with_the_sample_files(client):
    before_docs = client.get("/api/v1/documents").json()["total"]
    r = client.post("/api/v1/workspace/start", json=dict(intent_text="get my design ready for ARB", domain="Claims",
                    files=_files("sample-cmdb-export-2026-11.csv", "claims-copilot-main.tf", "claims-notifications-design.md", "Claims-Intake-Modernization-HLD-v1.2.docx")))
    assert r.status_code == 200 and r.json()["status"] == "running"
    w = _wait(client)
    assert w["status"] == "ready", w["error"]
    assert w["intent"]["id"] == "review" and w["domain"] == dict(name="Claims", known=True)
    assert [s["status"] for s in w["steps"]] == ["skipped"] + ["done"] * 7
    roles = {d["name"]: d["role"] for d in w["documents"]}
    assert roles["sample-cmdb-export-2026-11.csv"] == "inventory"
    assert roles["claims-copilot-main.tf"] == "iac"
    assert roles["claims-notifications-design.md"] == "design"
    assert roles["Claims-Intake-Modernization-HLD-v1.2.docx"] == "document"
    res = w["result"]
    assert res["verdict"] in ("go", "conditional", "no_go")
    ids = [s["id"] for s in res["sections"]]
    assert ids == ["documents", "inventory", "standards", "reviews", "estate"]
    estate = next(s for s in res["sections"] if s["id"] == "estate")
    assert next(m["value"] for m in estate["metrics"] if m["label"] == "Applications") == 12
    # what the run added is really in the other modules
    assert client.get("/api/v1/documents").json()["total"] > before_docs
    assert client.get("/api/v1/discovery/imports").json()["total"] == 1
    assert client.get("/api/v1/reviews/adhoc").json()["total"] == 2


def test_start_over_removes_what_the_run_added(client):
    before = client.get("/api/v1/documents").json()["total"]
    client.post("/api/v1/workspace/start", json=dict(intent_id="understand", domain="Claims", files=_files("Policy-Admin-Operations-Runbook.pdf", "claims-copilot-main.tf")))
    assert _wait(client)["status"] == "ready"
    assert client.get("/api/v1/documents").json()["total"] == before + 1
    client.delete("/api/v1/workspace")
    assert client.get("/api/v1/documents").json()["total"] == before
    assert client.get("/api/v1/reviews/adhoc").json()["total"] == 0


def test_a_new_domain_is_filed_but_has_no_estate_behind_it(client):
    client.post("/api/v1/workspace/start", json=dict(intent_id="understand", domain="Treasury", files=_files("Policy-Admin-Operations-Runbook.pdf")))
    w = _wait(client)
    assert w["status"] == "ready" and w["domain"]["known"] is False
    assert any("new domain" in n for n in w["result"]["notes"])
    estate = next(s for s in w["result"]["sections"] if s["id"] == "estate")
    assert next(m["value"] for m in estate["metrics"] if m["label"] == "Applications") == 0
    assert client.get("/api/v1/documents?domain=Treasury").json()["total"] == 1


def test_a_run_without_files_still_shows_the_domain(client):
    client.post("/api/v1/workspace/start", json=dict(intent_id="risk", domain="Billing & Finance", files=[]))
    w = _wait(client)
    assert w["status"] == "ready"
    assert [s["status"] for s in w["steps"]] == ["skipped", "done", "skipped", "skipped", "skipped", "skipped", "done", "done"]
    assert any("No files" in n for n in w["result"]["notes"])


def test_a_file_that_is_not_an_inventory_is_treated_as_a_document(client):
    client.post("/api/v1/workspace/start", json=dict(intent_id="understand", domain="Claims", files=[dict(filename="notes.csv", text="Claims Intake Portal calls Claims Core.\nSecond line of free text here.")]))
    w = _wait(client)
    assert w["status"] == "ready" and w["documents"][0]["role"] == "document"


def test_validation(client):
    assert client.post("/api/v1/workspace/start", json=dict(domain="", files=[])).status_code == 422
    too_many = [dict(filename=f"f{i}.txt", text="Claims Core calls Claims DB and more text.") for i in range(13)]
    assert client.post("/api/v1/workspace/start", json=dict(domain="Claims", files=too_many)).status_code == 422


def test_an_interrupted_run_is_reported_not_left_running(client):
    workspace.reset()
    from app.repositories import persist

    state = workspace._empty()
    state.update(status="running", mode="custom", steps=[])
    persist.add_item(workspace.KIND, state)
    w = client.get("/api/v1/workspace").json()
    assert w["status"] == "failed" and "interrupted" in w["error"]


def test_a_compliant_design_comes_out_ready(client):
    client.post("/api/v1/workspace/start", json=dict(intent_id="review", domain="Customer & Distribution", files=_files("agent-portal-sso-design.json")))
    w = _wait(client)
    assert w["status"] == "ready", w["error"]
    assert w["documents"][0]["role"] == "iac" or w["documents"][0]["role"] == "design"
    assert w["result"]["verdict"] == "go"
    standards = next(s for s in w["result"]["sections"] if s["id"] == "standards")
    assert next(m["value"] for m in standards["metrics"] if m["label"] == "Failed") == 0


def test_the_flawed_samples_never_read_as_ready(client):
    for names in (("claims-copilot-main.tf",), ("claims-notifications-design.md",), ("claims-copilot-main.fixed.tf",)):
        client.post("/api/v1/workspace/start", json=dict(intent_id="review", domain="Claims", files=_files(*names)))
        assert _wait(client)["result"]["verdict"] in ("no_go", "conditional"), names


ALL_TOOLS = ["servicenow", "jira", "azure", "github", "confluence", "sharepoint"]


def _demo_connect(client, *pids):
    for p in pids:
        assert client.put(f"/api/v1/connections/{p}", json=dict(mode="demo")).status_code == 200


def test_a_run_can_start_from_connected_tools_alone(client):
    _demo_connect(client, *ALL_TOOLS)
    docs_before = client.get("/api/v1/documents").json()["total"]
    r = client.post("/api/v1/workspace/start", json=dict(intent_id="understand", domain="Claims", files=[], connections=ALL_TOOLS))
    assert r.status_code == 200 and [x["id"] for x in r.json()["sources"]] == ALL_TOOLS
    w = _wait(client)
    assert w["status"] == "ready", w["error"]
    by = {s["id"]: s for s in w["steps"]}
    assert by["connect"]["status"] == "done" and "ServiceNow" in by["connect"]["detail"] and "demo data" in by["connect"]["detail"]
    assert by["inventory"]["status"] == "done" and by["documents"]["status"] == "done" and by["standards"]["status"] == "done"
    assert by["review"]["status"] == "skipped"  # connected tools bring no design to review
    ids = {s["id"] for s in w["result"]["sections"]}
    assert {"sources", "work", "inventory", "documents", "standards", "estate"} <= ids
    assert not any("No files" in n for n in w["result"]["notes"])
    # the pages that used to say "nothing to show" now hold what the tools brought
    assert client.get("/api/v1/discovery/imports").json()["items"]
    assert client.get("/api/v1/documents").json()["total"] > docs_before
    assert client.get("/api/v1/connections").json()["drift"]["compared"] > 0


def test_starting_over_removes_what_the_tools_brought_but_keeps_the_connections(client):
    _demo_connect(client, "servicenow", "confluence")
    docs_before = client.get("/api/v1/documents").json()["total"]
    client.post("/api/v1/workspace/start", json=dict(intent_id="understand", domain="Claims", connections=["servicenow", "confluence"]))
    assert _wait(client)["status"] == "ready"
    assert client.get("/api/v1/discovery/imports").json()["items"]
    client.delete("/api/v1/workspace")
    assert client.get("/api/v1/discovery/imports").json()["items"] == []
    assert client.get("/api/v1/documents").json()["total"] == docs_before
    c = client.get("/api/v1/connections/servicenow").json()
    assert c["connection"]["configured"] is True and c["sync"] is None


def test_a_tool_that_cannot_be_read_does_not_stop_the_run(client):
    import httpx

    from app.connectors import base

    _demo_connect(client, "servicenow")
    client.put("/api/v1/connections/jira", json=dict(mode="live", config=dict(site_url="https://acme.atlassian.net", email="a@b.c", projects="A"), secrets=dict(api_token="t")))
    base.transport = httpx.MockTransport(lambda req: httpx.Response(403))
    try:
        client.post("/api/v1/workspace/start", json=dict(intent_id="understand", domain="Claims", connections=["servicenow", "jira"]))
        w = _wait(client)
    finally:
        base.transport = None
    assert w["status"] == "ready", w["error"]
    connect = next(s for s in w["steps"] if s["id"] == "connect")
    assert connect["status"] == "done" and "ServiceNow" in connect["detail"] and "could not read Jira" in connect["detail"]
    assert any("Could not read Jira" in n for n in w["result"]["notes"])
    assert any(s["id"] == "inventory" and s["status"] == "done" for s in w["steps"])


def test_every_tool_failing_is_shown_as_a_failed_step_but_the_run_still_finishes(client):
    import httpx

    from app.connectors import base

    client.put("/api/v1/connections/jira", json=dict(mode="live", config=dict(site_url="https://acme.atlassian.net", email="a@b.c", projects="A"), secrets=dict(api_token="t")))
    base.transport = httpx.MockTransport(lambda req: httpx.Response(403))
    try:
        client.post("/api/v1/workspace/start", json=dict(intent_id="understand", domain="Claims", connections=["jira"]))
        w = _wait(client)
    finally:
        base.transport = None
    assert w["status"] == "ready" and next(s for s in w["steps"] if s["id"] == "connect")["status"] == "failed"


def test_connections_must_exist_and_be_set_up(client):
    assert client.post("/api/v1/workspace/start", json=dict(domain="Claims", connections=["nope"])).status_code == 422
    r = client.post("/api/v1/workspace/start", json=dict(domain="Claims", connections=["jira"]))
    assert r.status_code == 422 and "not set up" in r.text
