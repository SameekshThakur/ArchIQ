"""Connections: real connectors against a mock HTTP transport, demo mode end to end, secrets handling."""

import json

import httpx
import pytest

from app.connectors import base
from app.connectors.platforms import CONNECTORS


@pytest.fixture
def mock_http():
    routes = {}
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        for (method, frag), fn in routes.items():
            if req.method == method and frag in str(req.url):
                return fn(req)
        return httpx.Response(404, text="no route")

    base.transport = httpx.MockTransport(handler)
    yield routes, calls
    base.transport = None


def j(data, status=200):
    return lambda req: httpx.Response(status, json=data)


def run(pid, cfg):
    with base.client() as http:
        return CONNECTORS[pid].fetch(cfg, http)


def test_servicenow_pages_and_maps_fields(mock_http):
    routes, calls = mock_http
    page1 = [dict(name=f"App {i}", number=f"APM{i}", owned_by=dict(display_value="Ana"), business_criticality="1 - most critical", install_status="Installed") for i in range(500)]
    page2 = [dict(name="Claims Mainframe Core", number="APM9", owned_by="Raj", business_criticality="2 - somewhat critical", install_status="Retired")]
    routes[("GET", "sysparm_offset=0")] = j(dict(result=page1))
    routes[("GET", "sysparm_offset=500")] = j(dict(result=page2))
    d = run("servicenow", dict(instance_url="https://acme.service-now.com", username="svc", password="pw", table="cmdb_ci_business_app"))
    assert len(d.cmdb_rows) == 501 and d.cmdb_rows[0]["owner"] == "Ana" and d.cmdb_rows[-1]["status"] == "Retired"
    assert calls[0].headers["authorization"].startswith("Basic ") and "/api/now/table/cmdb_ci_business_app" in str(calls[0].url)


def test_jira_falls_back_to_classic_search(mock_http):
    routes, _ = mock_http
    routes[("GET", "/rest/api/3/search/jql")] = lambda r: httpx.Response(404)
    routes[("GET", "/rest/api/2/search")] = j(dict(total=1, issues=[dict(key="ARCH-1", fields=dict(summary="Move Claims Mainframe Core behind the gateway", status=dict(name="To Do", statusCategory=dict(key="new"))))]))
    d = run("jira", dict(site_url="https://jira.acme.com", api_token="pat", projects="ARCH"))
    assert d.work_items[0]["key"] == "ARCH-1" and d.work_items[0]["category"] == "new"


def test_jira_cloud_uses_basic_auth_and_page_tokens(mock_http):
    routes, calls = mock_http
    pages = iter([dict(issues=[dict(key="A-1", fields={})], nextPageToken="t2"), dict(issues=[dict(key="A-2", fields={})], isLast=True)])
    routes[("GET", "/rest/api/3/search/jql")] = lambda r: httpx.Response(200, json=next(pages))
    d = run("jira", dict(site_url="https://acme.atlassian.net", email="a@acme.com", api_token="tok", projects="A"))
    assert [w["key"] for w in d.work_items] == ["A-1", "A-2"] and "nextPageToken=t2" in str(calls[1].url)
    assert calls[0].headers["authorization"].startswith("Basic ")


def test_azure_reads_resource_graph_into_components(mock_http):
    routes, calls = mock_http
    routes[("POST", "login.microsoftonline.com")] = j(dict(access_token="T"))
    res = [dict(name="stclaims", type="Microsoft.Storage/storageAccounts", location="westeurope", properties=dict(publicNetworkAccess="Enabled", minimumTlsVersion="TLS1_0"))]
    routes[("POST", "Microsoft.ResourceGraph/resources")] = j(dict(data=res))
    d = run("azure", dict(tenant_id="t", client_id="c", client_secret="s", subscriptions="sub-1"))
    assert d.components[0]["type"] == "storage_account" and d.components[0]["public_network_access"] is True
    body = json.loads(calls[1].content)
    assert body["subscriptions"] == ["sub-1"] and calls[1].headers["authorization"] == "Bearer T"


def test_github_reads_terraform_and_adrs(mock_http):
    routes, _ = mock_http
    routes[("GET", "/git/trees/main")] = j(dict(tree=[dict(path="infra/main.tf", type="blob", size=100), dict(path="docs/adr/0001-events.md", type="blob", size=100)]))
    routes[("GET", "/contents/infra")] = lambda r: httpx.Response(200, text='resource "azurerm_storage_account" "st" {\n  name = "stclaims"\n  public_network_access_enabled = true\n}')
    routes[("GET", "/contents/docs")] = lambda r: httpx.Response(200, text="# ADR 1: Events over direct database access\n\nWe decided to publish events instead of reading the database.")
    routes[("GET", "/repos/org/infra")] = j(dict(full_name="org/infra", default_branch="main"))
    d = run("github", dict(api_url="https://api.github.com", token="t", repositories="org/infra"))
    assert any(c["type"] == "storage_account" for c in d.components) and d.documents[0]["doc_type"] == "ADR"


def test_confluence_and_sharepoint_return_documents(mock_http):
    routes, _ = mock_http
    routes[("GET", "/rest/api/content/search")] = j(dict(results=[dict(title="Claims HLD", body=dict(storage=dict(value="<p>Claims Core calls the Customer API v2 and publishes events to Kafka.</p>")), space=dict(key="ARCH"), _links=dict(webui="/x"))], _links={}))
    d = run("confluence", dict(base_url="https://acme.atlassian.net/wiki", email="a@acme.com", api_token="t", spaces="ARCH"))
    assert d.documents[0]["title"] == "Claims HLD" and "<p>" not in d.documents[0]["text"]
    routes[("POST", "login.microsoftonline.com")] = j(dict(access_token="G"))
    routes[("GET", "/sites/acme.sharepoint.com:/sites/Arch")] = j(dict(id="S1", displayName="Arch"))
    routes[("GET", "/drive/root/children")] = j(dict(value=[dict(id="F1", name="standards.md", size=90, file={}), dict(id="F2", name="logo.png", size=9, file={})]))
    routes[("GET", "/drive/items/F1/content")] = lambda r: httpx.Response(200, text="All new integrations go through the API gateway. No direct database access.")
    d = run("sharepoint", dict(tenant_id="t", client_id="c", client_secret="s", site_url="https://acme.sharepoint.com/sites/Arch"))
    assert [x["name"] for x in d.records] == ["standards.md"] and d.documents[0]["doc_type"] == "SharePoint"


def test_errors_are_plain_language(mock_http):
    routes, _ = mock_http
    routes[("GET", "/api/now/table")] = lambda r: httpx.Response(401)
    with pytest.raises(base.ConnectorError, match="credentials were rejected"):
        run("servicenow", dict(instance_url="https://acme.service-now.com", username="u", password="p"))
    with pytest.raises(base.ConnectorError, match="https://"):
        run("servicenow", dict(instance_url="http://acme.service-now.com", username="u", password="p"))


def test_secret_can_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("SN_PW", "from-env")
    assert base.secret("env:SN_PW") == "from-env"
    with pytest.raises(base.ConnectorError):
        base.secret("env:NOT_SET_ANYWHERE")


def test_api_never_returns_secrets_and_demo_sync_feeds_the_app(client):
    r = client.put("/api/v1/connections/servicenow", json=dict(mode="live", config=dict(instance_url="https://acme.service-now.com", username="svc"), secrets=dict(password="hunter2")))
    assert r.status_code == 200 and "hunter2" not in r.text and r.json()["secrets_set"]["password"] is True
    assert "hunter2" not in client.get("/api/v1/connections").text
    assert client.put("/api/v1/connections/servicenow", json=dict(mode="live", config=dict(nope="x"))).status_code == 400
    for p in ("servicenow", "azure", "github"):
        client.put(f"/api/v1/connections/{p}", json=dict(mode="demo"))
        s = client.post(f"/api/v1/connections/{p}/sync").json()
        assert s["ok"] and s["metrics"]
    imp = client.get("/api/v1/discovery/imports").json()["items"][0]
    assert imp["matched"] > 0 and imp["new"] == 3
    drift = client.get("/api/v1/connections").json()["drift"]
    assert drift["compared"] > 0 and drift["drifted"] > 0
    assert any(c["attribute"] == "public_network_access" for i in drift["items"] for c in i["changes"])


def test_failed_live_sync_is_reported_not_raised(client, mock_http):
    routes, _ = mock_http
    routes[("GET", "/rest/api/3/myself")] = lambda r: httpx.Response(401)
    client.put("/api/v1/connections/jira", json=dict(mode="live", config=dict(site_url="https://acme.atlassian.net", email="a@b.c", projects="A"), secrets=dict(api_token="t")))
    t = client.post("/api/v1/connections/jira/test").json()
    assert t["ok"] is False and "rejected" in t["detail"]
    routes[("GET", "/rest/api/3/search/jql")] = lambda r: httpx.Response(403)
    s = client.post("/api/v1/connections/jira/sync").json()
    assert s["ok"] is False and "permission" in s["error"] and s["connection"]["status"] == "error"


def test_connections_survive_start_over(client):
    client.put("/api/v1/connections/confluence", json=dict(mode="demo"))
    client.delete("/api/v1/workspace")
    assert client.get("/api/v1/connections/confluence").json()["connection"]["configured"] is True
    assert client.delete("/api/v1/connections/confluence").json() == dict(removed="confluence")
