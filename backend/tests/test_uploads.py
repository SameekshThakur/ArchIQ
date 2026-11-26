"""File extraction, inventory reconciliation, Terraform parsing and the sample files."""
from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[2] / "sample-files"


def _extract(client, name: str, data: bytes | None = None):
    data = data if data is not None else (SAMPLES / name).read_bytes()
    return client.post("/api/v1/files/extract", files={"file": (name, data)})


def test_supported_lists_office_formats(client):
    ext = client.get("/api/v1/files/supported").json()["extensions"]
    assert {".docx", ".pdf", ".xlsx", ".csv", ".tf", ".json"} <= set(ext)


@pytest.mark.parametrize("name,kind", [
    ("Claims-Intake-Modernization-HLD-v1.2.docx", "docx"),
    ("Policy-Admin-Operations-Runbook.pdf", "pdf"),
    ("sample-cmdb-export-2026-11.xlsx", "xlsx"),
    ("claims-copilot-main.tf", "tf"),
    ("ADR-0052-Event-Driven-Claims-Notifications.md", "md"),
])
def test_extract_each_format(client, name, kind):
    r = _extract(client, name)
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == kind and body["chars"] > 500 and body["text"].strip()


def test_extract_docx_keeps_structure(client):
    text = _extract(client, "Claims-Intake-Modernization-HLD-v1.2.docx").json()["text"]
    assert text.startswith("# ") and "Status: Proposed" in text and "| Availability |" in text


def test_extract_rejects_unknown_type_and_empty(client):
    r = _extract(client, "photo.exe", b"MZ\x00\x00")
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_file"
    assert _extract(client, "blank.txt", b"   ").status_code == 400


def test_extract_rejects_oversize(client):
    assert _extract(client, "big.txt", b"a" * (8 * 1024 * 1024 + 1)).status_code in (400, 413)


def test_cmdb_export_reconciles_with_estate(client):
    text = _extract(client, "sample-cmdb-export-2026-11.xlsx").json()["text"]
    r = client.post("/api/v1/discovery/import", json={"filename": "cmdb.xlsx", "text": text})
    assert r.status_code == 200
    d = r.json()
    assert d["rows"] == 66 and d["estate_total"] == 69
    assert d["matched"] + d["conflicts"] + d["probable"] == 63
    assert d["new"] == 2 and d["retired"] == 1 and d["probable"] == 2
    assert d["conflict_fields"] == {"criticality": 3, "hosting": 2, "owner": 2}
    assert len(d["missing"]) == 6
    assert d["ai"]["summary"]


def test_import_is_read_only(client, store):
    before = len(store.apps)
    text = (SAMPLES / "sample-cmdb-export-2026-11.csv").read_text()
    client.post("/api/v1/discovery/import", json={"filename": "x.csv", "text": text})
    assert len(store.apps) == before


def test_import_requires_a_name_column(client):
    r = client.post("/api/v1/discovery/import", json={"filename": "x.csv", "text": "foo,bar\n1,2\n3,4\n"})
    assert r.status_code == 400


def test_runbook_closes_gap_and_hld_adds_conflict(client):
    def titles():
        return [g["title"] for g in client.get("/api/v1/documents/gaps").json()["items"]]

    gap = "Policy Admin Core → Policy Master DB is not documented"
    assert gap in titles()
    for name, title in [("Policy-Admin-Operations-Runbook.pdf", "Runbook"), ("Claims-Intake-Modernization-HLD-v1.2.docx", "HLD upload")]:
        assert client.post("/api/v1/documents/ingest", json={"title": title, "text": _extract(client, name).json()["text"]}).status_code == 200
    assert gap not in titles()
    assert any("Customer Notification Hub" in c["title"] for c in client.get("/api/v1/documents/conflicts").json()["items"])


def test_terraform_before_and_after(client):
    def check(name):
        return client.post("/api/v1/standards/check", json={"design": (SAMPLES / name).read_text()}).json()

    bad, good = check("claims-copilot-main.tf"), check("claims-copilot-main.fixed.tf")
    assert bad["format"] == good["format"] == "terraform"
    assert bad["failed"] >= 6 and good["failed"] == 0
    assert good["score"] > bad["score"] + 30


# ------------------------------------------------------------------ persistence
def _restart():
    """Simulate an API restart: drop in-memory state and reload from the database file."""
    from app.mock_ai.generators import documents
    from app.repositories import persist

    persist.close()
    documents._uploaded.clear()
    documents._version[0] += 1
    return documents.load_uploads()


def test_uploaded_documents_survive_restart(client):
    text = _extract(client, "Policy-Admin-Operations-Runbook.pdf").json()["text"]
    doc = client.post("/api/v1/documents/ingest", json={"title": "Runbook upload", "text": text}).json()
    assert doc["id"] == "UPL-001" or doc["id"].startswith("UPL-")
    assert _restart() == 1
    again = client.get(f"/api/v1/documents/{doc['id']}")
    assert again.status_code == 200 and again.json()["title"] == "Runbook upload" and len(again.json()["relations"]) == len(doc["relations"])
    assert any(r["id"] == doc["id"] and r["uploaded"] for r in client.get("/api/v1/documents?page_size=200").json()["items"])


def test_upload_ids_are_never_reused(client):
    body = {"title": "First doc", "text": "Policy Admin Core calls Customer API v2. " * 3}
    a = client.post("/api/v1/documents/ingest", json=body).json()["id"]
    assert client.delete(f"/api/v1/documents/{a}").status_code == 200
    b = client.post("/api/v1/documents/ingest", json=body).json()["id"]
    assert a != b and client.get(f"/api/v1/documents/{a}").status_code == 404


def test_cannot_delete_seeded_document(client):
    assert client.delete("/api/v1/documents/DOC-001").status_code == 400


def test_adhoc_review_saved_and_reopened(client):
    design = (SAMPLES / "claims-notifications-design.md").read_text(encoding="utf-8")
    run = client.post("/api/v1/reviews/run", json={"title": "Notifications v2", "tier": "tier2", "design": design}).json()
    sid = run["saved_id"]
    listed = client.get("/api/v1/reviews/adhoc").json()["items"]
    assert listed[0]["id"] == sid and listed[0]["verdict"] == run["review"]["verdict"] and "request" not in listed[0]
    _restart()
    again = client.get(f"/api/v1/reviews/adhoc/{sid}").json()
    assert again["review"]["verdict"] == run["review"]["verdict"] and again["review"]["readiness"] == run["review"]["readiness"]
    assert client.delete(f"/api/v1/reviews/adhoc/{sid}").status_code == 200
    assert client.get(f"/api/v1/reviews/adhoc/{sid}").status_code == 404


def test_inventory_import_saved(client):
    text = (SAMPLES / "sample-cmdb-export-2026-11.csv").read_text(encoding="utf-8")
    saved = client.post("/api/v1/discovery/import", json={"filename": "x.csv", "text": text}).json()["saved_id"]
    lst = client.get("/api/v1/discovery/imports").json()["items"]
    assert lst[0]["id"] == saved and lst[0]["matched"] + lst[0]["conflicts"] == 61 and lst[0]["missing"] == 6
    _restart()
    full = client.get(f"/api/v1/discovery/imports/{saved}").json()
    assert full["filename"] == "x.csv" and len(full["items"]) == 66 and full["ai"]["summary"]


def test_corrupt_database_is_set_aside(tmp_path, monkeypatch):
    from app.repositories import persist

    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is not a sqlite database" * 50)
    persist.close()
    monkeypatch.setenv("ARCHIQ_DB", str(bad))
    try:
        assert persist.add_upload("t", "x" * 30, "Confluence", "Claims") == 1
        assert (tmp_path / "bad.db.corrupt").exists()
    finally:
        persist.close()


# ------------------------------------------------------------------ broader parsers
def _workbook(sheets: dict[str, list[list]], hidden: tuple[str, ...] = ()) -> bytes:
    import io

    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
        if name in hidden:
            ws.sheet_state = "hidden"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_excel_reads_every_visible_sheet_and_skips_title_rows(client):
    data = _workbook({
        "Cover": [["Quarterly CMDB export"], []],
        "Applications": [["Generated by ServiceNow"], [], ["Name", "Business Criticality", "Hosting"], ["Claims Copilot", "2 - High", "Azure"], ["Policy Admin Core", "1 - Critical", "On-Premises"]],
        "Secret": [["a", "b"], [1, 2]],
        "Servers": [["Host", "OS"], ["srv01", "Windows"]],
    }, hidden=("Secret",))
    body = _extract(client, "book.xlsx", data).json()
    assert body["meta"]["sheets"] == 2 and "Secret" not in body["text"]
    assert "## Sheet: Applications" in body["text"] and "Generated by ServiceNow" not in body["text"] and "Name,Business Criticality,Hosting" in body["text"]
    rep = client.post("/api/v1/discovery/import", json={"filename": "book.xlsx", "text": body["text"]})
    assert rep.status_code == 200 and rep.json()["rows"] == 2  # the Servers sheet is ignored; Applications is used


def test_excel_with_no_name_column_lists_the_sheets(client):
    body = _extract(client, "x.xlsx", _workbook({"A": [["foo", "bar"], [1, 2]], "B": [["baz", "qux"], [3, 4]]})).json()
    r = client.post("/api/v1/discovery/import", json={"filename": "x.xlsx", "text": body["text"]})
    assert r.status_code == 400 and set(r.json()["error"]["details"]["sheets"]) == {"A", "B"}


def _scan(kind: str) -> bytes:
    import io

    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1240, 500), "white")
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
    except OSError:
        f = ImageFont.load_default()
    for i, line in enumerate(["Status: Current", "Policy Admin Core stores its data in Policy Master DB."]):
        d.text((60, 80 + i * 70), line, fill="black", font=f)
    buf = io.BytesIO()
    img.save(buf, "PDF" if kind == "pdf" else "PNG", resolution=150)
    return buf.getvalue()


def _has_ocr() -> bool:
    from app.services import ocr

    return ocr.available()


@pytest.mark.skipif(not _has_ocr(), reason="Tesseract is not installed")
@pytest.mark.parametrize("name,kind", [("scan.pdf", "pdf"), ("scan.png", "png")])
def test_ocr_reads_scans(client, name, kind):
    body = _extract(client, name, _scan(kind)).json()
    assert body["meta"]["ocr"] is True and "Policy Master DB" in body["text"]
    # and the recovered text feeds the same engines as any other document
    doc = client.post("/api/v1/documents/ingest", json={"title": "Scanned runbook", "text": body["text"]}).json()
    assert any(r["rel"] == "stores_in" for r in doc["relations"])


def test_scan_without_ocr_gives_install_instructions(client, monkeypatch):
    from app.services import ocr

    monkeypatch.setattr(ocr, "available", lambda: False)
    monkeypatch.setattr(ocr, "status", lambda: {"available": False, "reason": "The Tesseract program was not found"})
    r = _extract(client, "scan.pdf", _scan("pdf"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "ocr_unavailable" and "requirements-ocr.txt" in r.json()["error"]["message"]


def test_terraform_variables_comments_merge_modules(client):
    tf = '''
variable "public_access" { default = false }
variable "base_tags" {
  default = { owner = "platform", "cost-centre" = "CC-1" }
}
locals { tags = merge(var.base_tags, { data_classification = "restricted" }) }
/* resource "azurerm_key_vault" "old" { public_network_access_enabled = true } */
module "net" { source = "./net" }
resource "azurerm_storage_account" "s" {
  name = "x"
  min_tls_version = "TLS1_2"   # braces { in a comment }
  public_network_access_enabled = var.public_access
  tags = local.tags
}
resource "azurerm_storage_account" "locked" {
  count = 2
  tags = merge(local.tags, { env = "prod" })
}
resource "azurerm_storage_account_network_rules" "r" {
  storage_account_id = azurerm_storage_account.locked.id
  default_action = "Deny"
}
resource "azurerm_redis_cache" "c" { name = "z" }
'''
    r = client.post("/api/v1/standards/check", json={"design": tf}).json()
    assert r["components"] == 2  # the commented-out Key Vault is ignored
    notes = " ".join(r["notes"])
    assert "Module 'net'" in notes and "count or for_each" in notes and "azurerm_redis_cache" in notes
    from app.mock_ai.rules.standards import parse_design

    comps = {c["id"]: c for c in parse_design(tf)["components"]}
    assert comps["s"]["public_network_access"] is False and comps["s"]["tags_complete"] is True and comps["s"]["data_classification"] == "restricted"
    assert comps["locked"]["public_network_access"] is False and comps["locked"]["tags_complete"] is True


def test_bicep_before_and_after(client):
    def check(name):
        return client.post("/api/v1/standards/check", json={"design": (SAMPLES / name).read_text(encoding="utf-8")}).json()

    bad, good = check("claims-copilot-main.bicep"), check("claims-copilot-main.fixed.bicep")
    assert bad["format"] == good["format"] == "bicep"
    assert bad["failed"] >= 6 and good["failed"] == 0 and good["score"] > bad["score"] + 30


def test_bicep_modules_loops_conditions_are_noted(client):
    bicep = '''
param location string = 'westeurope'
module net './net.bicep' = { name: 'net' }
resource kv 'Microsoft.KeyVault/vaults@2023-02-01' = if (deploy) {
  name: 'kv'
  location: location
  properties: { publicNetworkAccess: 'Disabled' }
}
resource many 'Microsoft.Storage/storageAccounts@2023-01-01' = [for i in range(0, 3): {
  name: 'st${i}'
}]
'''
    r = client.post("/api/v1/standards/check", json={"design": bicep}).json()
    assert r["format"] == "bicep" and r["components"] == 1
    n = " ".join(r["notes"])
    assert "Module 'net'" in n and "conditional" in n and "loop" in n


def test_arm_template(client):
    import json

    arm = {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#", "parameters": {"loc": {"type": "string", "defaultValue": "West Europe"}},
           "resources": [{"type": "Microsoft.Storage/storageAccounts", "apiVersion": "2023-01-01", "name": "st1", "location": "[parameters('loc')]",
                          "properties": {"minimumTlsVersion": "TLS1_0", "publicNetworkAccess": "Enabled"}, "tags": {"owner": "a"}},
                         {"type": "Microsoft.Cache/Redis", "apiVersion": "2023-01-01", "name": "r"}]}
    r = client.post("/api/v1/standards/check", json={"design": json.dumps(arm)}).json()
    assert r["format"] == "arm" and r["components"] == 1 and "Microsoft.Cache/Redis" in " ".join(r["notes"])
    assert any(x["standard_id"] == "STD-SEC-002" and x["status"] == "fail" for x in r["results"])


# ------------------------------------------------------------------ samples served by the API
def test_samples_listed_and_downloadable(client):
    items = {i["name"]: i for i in client.get("/api/v1/files/samples").json()["items"]}
    assert {"sample-cmdb-export-2026-11.xlsx", "Policy-Admin-Operations-Runbook.pdf", "claims-copilot-main.bicep"} <= set(items)
    r = client.get("/api/v1/files/samples/Policy-Admin-Operations-Runbook.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and "attachment" in r.headers["content-disposition"]
    # a served sample goes straight back through the extractor
    assert _extract(client, "Policy-Admin-Operations-Runbook.pdf", r.content).status_code == 200


@pytest.mark.parametrize("name", ["../../backend/requirements.txt", "..%2F..%2Fbackend%2Frequirements.txt", "%2Fetc%2Fpasswd", "nope.txt", "..", ".gitignore"])
def test_sample_endpoint_rejects_traversal(client, name):
    assert client.get(f"/api/v1/files/samples/{name}").status_code == 404


def test_sample_folder_can_be_missing(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ARCHIQ_SAMPLES", str(tmp_path / "nowhere"))
    assert client.get("/api/v1/files/samples").json() == {"items": [], "total": 0}


# ------------------------------------------------------------ saved graph views
def test_graph_views_save_replace_delete_and_survive_restart(client):
    body = dict(name="Claims core", layers=["app", "data"], hops=3, color_by="criticality", focus="APP-001", domains=["Claims"], criticality=["critical", "high"])
    r = client.post("/api/v1/graph/views", json=body)
    assert r.status_code == 201 and r.json()["id"]
    # same name (any case) replaces rather than duplicating
    client.post("/api/v1/graph/views", json={**body, "name": "claims CORE", "hops": 1})
    items = client.get("/api/v1/graph/views").json()["items"]
    assert len(items) == 1 and items[0]["hops"] == 1 and items[0]["domains"] == ["Claims"]
    # views saved before relation filters and collapsing existed still load, with those left empty
    client.post("/api/v1/graph/views", json=dict(name="Old style", layers=["app"]))
    old = [v for v in client.get("/api/v1/graph/views").json()["items"] if v["name"] == "Old style"][0]
    assert old["relations"] == [] and old["collapsed"] == []
    rich = client.post("/api/v1/graph/views", json=dict(name="Rich", relations=["calls", "owned_by"], collapsed=["Claims", "Billing & Finance"])).json()
    assert rich["relations"] == ["calls", "owned_by"] and rich["collapsed"] == ["Claims", "Billing & Finance"]
    client.delete(f"/api/v1/graph/views/{old['id']}")
    client.delete(f"/api/v1/graph/views/{rich['id']}")
    _restart()
    items = client.get("/api/v1/graph/views").json()["items"]
    assert len(items) == 1
    assert client.delete(f"/api/v1/graph/views/{items[0]['id']}").status_code == 200
    assert client.get("/api/v1/graph/views").json()["items"] == []
    assert client.delete("/api/v1/graph/views/999").status_code == 404


@pytest.mark.parametrize("patch", [dict(name=""), dict(name="  "), dict(layers=["bogus"]), dict(hops=9), dict(color_by="size")])
def test_graph_views_validation(client, patch):
    r = client.post("/api/v1/graph/views", json={**dict(name="x", layers=["app"], hops=2, color_by="type"), **patch})
    assert r.status_code in (400, 422)


def test_graph_views_limit(client):
    for i in range(30):
        assert client.post("/api/v1/graph/views", json=dict(name=f"v{i}")).status_code == 201
    assert client.post("/api/v1/graph/views", json=dict(name="one too many")).status_code == 400
    assert client.post("/api/v1/graph/views", json=dict(name="v3")).status_code == 201  # replacing is still fine
