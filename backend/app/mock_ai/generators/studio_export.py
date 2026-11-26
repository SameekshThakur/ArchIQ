"""Blueprint Intelligence Studio, step 7: the target architecture document and the starter ZIP.

What the ZIP is, and is not:
* It holds the architecture as the person edited it (diagram, model, configuration), the documentation, and starter files for the choices made.
* Every file is checked in ways this server can check: Python is parsed, YAML and JSON are parsed, XML is read, the OpenAPI contract is checked for structure and references, and the
  generated Terraform is read back with ArchIQ's own HCL reader and compared with the design for the attributes Terraform can express.
* Nothing is run against a cloud. `terraform init`, `validate` and `plan`, container builds and the service's own tests have NOT been run, and the README says so.
  Do not describe the infrastructure files as deployable until your pipeline has validated them.
"""

from __future__ import annotations

import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import yaml

from app.mock_ai.generators import codegen
from app.mock_ai.generators import studio_catalog as cat
from app.mock_ai.rules import standards as std
from app.mock_ai.rules import studio as studio_rules
from app.repositories.store import get_store

ROLE_FILL = {"actor": ("#E8EEF7", "#1F3A5F"), "edge": ("#E1EEFF", "#10407A"), "api": ("#E0F4EE", "#0B5B47"), "compute": ("#EDF3DD", "#3F5A0B"), "ai_agent": ("#F1E6FF", "#4B2A86"), "ai_llm": ("#F1E6FF", "#4B2A86"),
             "ai_search": ("#FDEFDD", "#7A4308"), "messaging": ("#FFF3CF", "#6B5200"), "integration": ("#E6EEF6", "#26435F"), "database": ("#DDEFF2", "#0E4F5C"), "security": ("#FCE6E6", "#7A1F1F"), "external": ("#EDEDED", "#444444")}


def slug(text: str, fallback: str = "architecture") -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:48] or fallback


def _cell(v: object) -> str:
    return str(v if v not in (None, "") else "-").replace("|", "\\|").replace("\n", " ")


def _table(head: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return "_None._\n"
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ diagram
def mermaid(arch: dict) -> str:
    lines = [f"flowchart {arch['direction']}"]
    for n in arch["nodes"]:
        label = n["name"].replace('"', "'")
        if n.get("technology") and n["role"] not in ("actor",):
            label += f"<br/>{n['technology'].replace(chr(34), chr(39))}"
        shape = f'{n["id"]}[("{label}")]' if n["role"] == "database" else f'{n["id"]}[["{label}"]]' if n["role"] == "messaging" else f'{n["id"]}["{label}"]'
        lines.append("  " + shape)
    for e in arch["edges"]:
        arrow = "-.->" if e.get("dashed") else "-->"
        lbl = f'|"{e["label"].replace(chr(34), chr(39))}"|' if e.get("label") else ""
        lines.append(f"  {e['source']} {arrow}{lbl} {e['target']}")
    return "\n".join(lines) + "\n"


def svg(arch: dict, title: str = "") -> str:
    w, h = arch["node_size"]["w"], arch["node_size"]["h"]
    pos = {n["id"]: n["pos"] for n in arch["nodes"]}
    maxx = max([p["x"] for p in pos.values()] or [0]) + w + 40
    maxy = max([p["y"] for p in pos.values()] or [0]) + h + 70
    lr = arch["direction"] == "LR"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {maxx:.0f} {maxy:.0f}" width="{maxx:.0f}" height="{maxy:.0f}" font-family="Segoe UI, Arial, sans-serif">',
           f"<title>{escape(title or 'Target architecture')}</title>",
           '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#5a6678"/></marker></defs>',
           f'<rect width="{maxx:.0f}" height="{maxy:.0f}" fill="#ffffff"/>']
    for e in arch["edges"]:
        a, b = pos.get(e["source"]), pos.get(e["target"])
        if not a or not b:
            continue
        if lr:
            x1, y1, x2, y2 = a["x"] + w, a["y"] + h / 2, b["x"], b["y"] + h / 2
            c = f"M{x1:.0f} {y1:.0f} C{(x1 + x2) / 2:.0f} {y1:.0f} {(x1 + x2) / 2:.0f} {y2:.0f} {x2:.0f} {y2:.0f}"
        else:
            x1, y1, x2, y2 = a["x"] + w / 2, a["y"] + h, b["x"] + w / 2, b["y"]
            c = f"M{x1:.0f} {y1:.0f} C{x1:.0f} {(y1 + y2) / 2:.0f} {x2:.0f} {(y1 + y2) / 2:.0f} {x2:.0f} {y2:.0f}"
        edash = ' stroke-dasharray="6 4"' if e.get("dashed") else ""
        out.append(f'<path d="{c}" fill="none" stroke="#5a6678" stroke-width="1.4"{edash} marker-end="url(#a)"/>')
        if e.get("label"):
            out.append(f'<text x="{(x1 + x2) / 2:.0f}" y="{(y1 + y2) / 2 - 5:.0f}" font-size="11" text-anchor="middle" fill="#3b4656">{escape(e["label"])}</text>')
    for n in arch["nodes"]:
        p = n["pos"]
        fill, ink = ROLE_FILL.get(n["role"], ("#EEE", "#333"))
        dash = ' stroke-dasharray="5 3"' if not n["assessed"] and n["role"] not in ("actor", "external") else ""
        out.append(f'<rect x="{p["x"]:.0f}" y="{p["y"]:.0f}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{ink}" stroke-width="1.2"{dash}/>')
        out.append(f'<text x="{p["x"] + w / 2:.0f}" y="{p["y"] + 30:.0f}" font-size="13" font-weight="600" text-anchor="middle" fill="{ink}">{escape(n["name"][:30])}</text>')
        sub = n.get("technology") or n["role_label"]
        out.append(f'<text x="{p["x"] + w / 2:.0f}" y="{p["y"] + 50:.0f}" font-size="11" text-anchor="middle" fill="#3b4656">{escape(str(sub)[:34])}</text>')
    out.append(f'<text x="14" y="{maxy - 14:.0f}" font-size="11" fill="#5a6678">Dashed outline: not assessed by the standards library. Generated by ArchIQ Blueprint Intelligence Studio.</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ document
def _label_of(kind: str, ident: str) -> str:
    items = dict(cloud=cat.CLOUDS, llm=cat.LLMS, backend=cat.BACKENDS, messaging=cat.MESSAGING, iac=cat.IAC, region=cat.REGIONS, tier=cat.TIERS, classification=cat.CLASSIFICATIONS, exposure=cat.EXPOSURE)[kind]
    return next((x["label"] for x in items if x["id"] == ident), str(ident))


def document(design: dict, arch: dict, val: dict, summary: str = "") -> str:
    sel = arch["selections"]
    rec = design.get("recommendation") or {}
    ext = design.get("extraction") or {}
    from app.mock_ai.generators import blueprints as bp_gen

    meta = bp_gen.BLUEPRINTS[arch["blueprint_id"]]
    pats = {p["id"]: p for p in get_store().patterns}
    ver = (design.get("versions") or [{}])[-1].get("n", 0)
    md: list[str] = []
    add = md.append
    add(f"# Target architecture: {design['title']}\n")
    add(f"_Generated by ArchIQ Blueprint Intelligence Studio on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. Design {design.get('ref', '')}, version {ver or 'unsaved'}._\n")
    add("> **Status of the figures in this document.** The readiness score, verdict and every finding come from deterministic engines (standards, NFR and estate-risk rules). They describe the design **as declared**: "
        "nothing here was verified against a deployed environment.\n")
    add(_table(["", ""], [["Business domain", design.get("domain")], ["Blueprint", f"{arch['blueprint_id']}: {pats[arch['blueprint_id']]['name']}"], ["Readiness (review engine)", f"{val['readiness']}%"], ["Verdict", val["verdict"].replace("_", " ")],
                          ["Components assessed by the standards library", f"{val['coverage']['assessed']} of {val['coverage']['total']} ({val['coverage']['percent']}%)"], ["Open gaps", f"{val['open_counts']['critical']} critical, {val['open_counts']['high']} high, {val['open_counts']['medium']} medium, {val['open_counts']['low']} low"]]))
    if summary:
        add("## Summary\n")
        add(summary.strip() + "\n")
    add("## 1. Requirements\n")
    add((design.get("requirement") or {}).get("text", "").strip() + "\n")
    facts = ext.get("facts") or []
    if facts:
        add("What was read from the text:\n")
        add(_table(["Fact", "Value", "Evidence from the text"], [[f["label"], f["value"], f["evidence"]] for f in facts]))
    add("## 2. Blueprint selection\n")
    if rec.get("recommended"):
        r = rec["recommended"]
        add(f"The Studio recommended **{r['name']}** ({r['id']}) with a confidence of {round(r['confidence'] * 100)}%. The score is a count of weighted matches between the requirements and the blueprint's use cases ({r['score']} points).\n")
        add(_table(["Signal", "Weight", "Evidence"], [[m["label"], m["weight"], m["evidence"]] for m in r["rationale"]]))
    chosen = design.get("blueprint_choice") or {}
    if chosen.get("overridden"):
        add(f"The architect chose a different blueprint: **{pats[arch['blueprint_id']]['name']}**. Reason recorded: {chosen.get('reason') or 'none given'}.\n")
    alts = rec.get("alternatives") or []
    if alts:
        add("Alternatives considered:\n")
        add(_table(["Blueprint", "Score", "Why it was not first"], [[f"{a['name']} ({a['id']})", a["score"], a["why_not"]] for a in alts]))
    add(f"**{meta['title']}**\n")
    add("Use this blueprint when:\n")
    md += [f"- {w}" for w in meta["when"]]
    add("")
    add("## 3. Choices\n")
    labels = {d["id"]: d["label"] for d in cat.DATABASES}
    dep = next((d["label"] for d in cat.DEPLOYMENTS[sel["cloud"]] if d["id"] == sel["deployment"]), sel["deployment"])
    add(_table(["Choice", "Value", "Source"], [["Cloud", _label_of("cloud", sel["cloud"]), design.get("selection_sources", {}).get("cloud", "")], ["Region", _label_of("region", sel["region"]), design.get("selection_sources", {}).get("region", "")],
                                            ["Deployment", dep, design.get("selection_sources", {}).get("deployment", "")], ["LLM", _label_of("llm", sel["llm"]), design.get("selection_sources", {}).get("llm", "")],
                                            ["Data stores", ", ".join(labels[d] for d in sel["databases"]) or "none", design.get("selection_sources", {}).get("databases", "")], ["Backend", _label_of("backend", sel["backend"]), design.get("selection_sources", {}).get("backend", "")],
                                            ["Messaging", _label_of("messaging", sel["messaging"]), design.get("selection_sources", {}).get("messaging", "")], ["Infrastructure as code", _label_of("iac", sel["iac"]), ""],
                                            ["Exposure", _label_of("exposure", sel["exposure"]), ""], ["Criticality tier", _label_of("tier", sel["tier"]), ""], ["Data classification", _label_of("classification", sel["classification"]) if sel.get("classification") else "not set", ""]]))
    add("Security and operations controls declared:\n")
    add(_table(["Control", "Serves standards"], [[p["label"], ", ".join(p["standards"])] for p in cat.POSTURE if p["id"] in sel["posture"]]))
    add("## 4. Architecture\n")
    add("```mermaid\n" + mermaid(arch) + "```\n")
    rows = []
    for n in arch["nodes"]:
        keyp = ", ".join(f"{k}={v}" for k, v in sorted(n["props"].items()) if k in ("public_network_access", "auth", "tls_min", "internet_facing", "data_classification", "multi_az"))
        rows.append([n["name"], n["role_label"], n["type_label"], n.get("technology"), keyp, "yes" if n["assessed"] else ("n/a" if n["role"] in ("actor", "external") else "no")])
    add(_table(["Component", "Role", "Type", "Technology", "Declared properties", "Assessed"], rows))
    nm = {n["id"]: n["name"] for n in arch["nodes"]}
    add("Connections:\n")
    add(_table(["From", "To", "Label"], [[nm[e["source"]], nm[e["target"]], e.get("label")] for e in arch["edges"]]))
    add("## 5. Non-functional requirements\n")
    nfr = design.get("nfr") or {}
    add(_table(["Target", "Value", "Origin"], [[k.replace("_", " "), (", ".join(v) if isinstance(v, list) else v), (design.get("nfr_origin") or {}).get(k, "entered")] for k, v in sorted(nfr.items())]))
    add(f"Required targets not stated: {', '.join(k.replace('_', ' ') for k in val['nfr_coverage']['missing']) or 'none'}.\n")
    add("## 6. Validation\n")
    add(f"Readiness {val['readiness']}% and verdict **{val['verdict'].replace('_', ' ')}** come from the existing review engine"
        + (f" (the engine's own verdict was {val['engine_verdict'].replace('_', ' ')})" if val["engine_verdict"] != val["verdict"] else "") + ". " + val["basis"] + "\n")
    add(_table(["Check", "Result", "Engine"], [[c["label"], c["detail"], c["engine"]] for c in val["checks_run"]]))
    add("Standards evaluated:\n")
    add(_table(["Standard", "Status", "Severity", "Rationale"], [[f"{r['standard_id']}: {r['title']}", r["status"], r["severity"], r["rationale"]] for r in val["standards"]["results"]]))
    if val["coverage"]["not_assessed"]:
        add("Components the standards library could not assess:\n")
        add(_table(["Component", "Type", "Reason"], [[c["name"], c["type"], c["reason"]] for c in val["coverage"]["not_assessed"]]))
    add("## 7. Gap analysis\n")
    add(_table(["Severity", "Gap", "State", "Recommendation"], [[g["severity"], g["title"], g["state"].replace("_", " "), g["recommendation"]] for g in val["gaps"]]))
    dec = [(gid, d) for gid, d in (design.get("decisions") or {}).items() if d.get("status") == "risk_accepted"]
    if dec:
        add("Risks accepted by the architect (these remain open findings and need the review board's agreement):\n")
        add(_table(["Gap", "Justification", "Recorded"], [[next((g["title"] for g in val["gaps"] if g["id"] == gid), gid), d.get("note"), d.get("at", "")[:10]] for gid, d in dec]))
    applied = [(gid, d) for gid, d in (design.get("decisions") or {}).items() if d.get("status") in ("accepted", "modified")]
    if applied:
        add("Recommendations applied:\n")
        add(_table(["Gap", "Decision", "Change", "Recorded"], [[gid, d["status"], d.get("fix_label"), d.get("at", "")[:10]] for gid, d in applied]))
    add("## 8. Governance\n")
    sub = design.get("submission")
    add((f"Submitted to the architecture review board as **{sub['arb_id']}** on {sub['submitted_at'][:10]} (version {sub['version']}). Stage in the review queue: {sub['stage'].replace('_', ' ')}.\n") if sub else "Not yet submitted to the architecture review board.\n")
    add("## 9. Assumptions and limitations\n")
    for x in ("Properties are declared by choices, the blueprint's diagram, Azure platform defaults, connections or edits. They were not read from a running environment.",
              "The standards library describes Azure resource types. Components on other clouds, and generic services, are not assessed.",
              "Blueprint selection is a weighted keyword match against authored blueprint use cases. It is explainable and repeatable, and it can miss intent that the text does not state.",
              "The review engine's readiness formula is unchanged. Gaps from the Studio's additional checks can only make the verdict more cautious."):
        add(f"- {x}")
    vs = design.get("versions") or []
    if vs:
        add("\n## 10. Version history\n")
        add(_table(["Version", "Saved", "Label", "Readiness", "Verdict"], [[v["n"], v["at"][:16].replace("T", " "), v.get("label"), v["summary"].get("readiness"), v["summary"].get("verdict")] for v in vs]))
    return "\n".join(md) + "\n"


# ------------------------------------------------------------------ terraform
def _tf_label(nid: str) -> str:
    s = re.sub(r"[^a-z0-9_]", "_", nid.lower())
    return s if s[:1].isalpha() else "r_" + s


PE_SPEC = {"key_vault": ("vault", "privatelink.vaultcore.azure.net"), "azure_openai": ("account", "privatelink.openai.azure.com"), "ai_search": ("searchService", "privatelink.search.windows.net"),
           "postgres": ("postgresqlServer", "privatelink.postgres.database.azure.com"), "cosmos_db": ("Sql", "privatelink.documents.azure.com"), "data_lake": ("dfs", "privatelink.dfs.core.windows.net"),
           "sql_database": ("sqlServer", "privatelink.database.windows.net")}


def terraform(arch: dict, design: dict) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Terraform for the Azure resources in the design. Returns the files and a map from each resource label to the design components it stands for."""
    sel = arch["selections"]
    nodes = [n for n in arch["nodes"] if n["assessed"] and n["type"] in ("key_vault", "azure_openai", "ai_search", "postgres", "cosmos_db", "data_lake", "sql_database", "aks_cluster", "app_service", "function", "api_management", "kafka")]
    owner = design.get("owner") or "Platform Engineering"
    cls = sel.get("classification") or "internal"
    tags_ok = any(n["props"].get("tags_complete") for n in arch["nodes"])
    body: list[str] = []
    tfmap: dict[str, list[str]] = {}
    pe_needed = [n for n in nodes if n["props"].get("public_network_access") is False and n["type"] in PE_SPEC]
    diag = [n for n in nodes if n["props"].get("logging") is True and n["type"] in ("key_vault", "azure_openai", "ai_search", "postgres", "cosmos_db", "data_lake", "sql_database", "app_service", "function")]
    mi = lambda n: n["props"].get("auth") == "managed_identity"  # noqa: E731

    def tags() -> str:
        return "  tags                = var.tags\n"

    def head(rtype: str, label: str, name_expr: str) -> str:
        return f'resource "{rtype}" "{label}" {{\n  name                = {name_expr}\n  location            = var.location\n  resource_group_name = azurerm_resource_group.this.name\n'

    def pub(n: dict, attr: str = "public_network_access_enabled") -> str:
        v = n["props"].get("public_network_access")
        return f"  {attr} = {'true' if v else 'false'}\n" if v is not None else ""

    body.append('resource "azurerm_resource_group" "this" {\n  name     = "rg-${local.suffix}"\n  location = var.location\n  tags     = var.tags\n}\n')
    plans: set[str] = set()
    for n in nodes:
        lab = _tf_label(n["id"])
        t = n["type"]
        if t == "key_vault":
            body.append(head("azurerm_key_vault", lab, f'"kv-${{substr(replace(local.suffix, "-", ""), 0, 20)}}"') + '  tenant_id           = data.azurerm_client_config.current.tenant_id\n  sku_name            = "standard"\n  enable_rbac_authorization = true\n  purge_protection_enabled  = true\n' + pub(n) + tags() + "}\n")
            tfmap[f"azurerm_key_vault.{lab}"] = [n["id"]]
        elif t == "azure_openai":
            body.append(head("azurerm_cognitive_account", lab, f'"oai-{lab}-${{local.suffix}}"') + f'  kind                  = "OpenAI"\n  sku_name              = "S0"\n  custom_subdomain_name = "oai-{lab}-${{local.suffix}}"\n' + pub(n)
                        + ("  local_auth_enabled    = false\n  identity {\n    type = \"SystemAssigned\"\n  }\n" if mi(n) else "") + tags() + "}\n")
            tfmap[f"azurerm_cognitive_account.{lab}"] = [n["id"]]
        elif t == "ai_search":
            body.append(head("azurerm_search_service", lab, f'"srch-{lab}-${{local.suffix}}"') + '  sku                 = "standard"\n' + pub(n) + tags() + "}\n")
            tfmap[f"azurerm_search_service.{lab}"] = [n["id"]]
        elif t == "postgres":
            auth = ('  authentication {\n    active_directory_auth_enabled = true\n    password_auth_enabled         = false\n    tenant_id                     = data.azurerm_client_config.current.tenant_id\n  }\n' if mi(n)
                    else '  administrator_login    = "pgadmin"\n  administrator_password = var.postgres_admin_password\n')
            ha = '  high_availability {\n    mode = "ZoneRedundant"\n  }\n' if n["props"].get("multi_az") else ""
            body.append(head("azurerm_postgresql_flexible_server", lab, f'"pg-{lab}-${{local.suffix}}"') + '  version    = "15"\n  sku_name   = "GP_Standard_D2s_v3"\n  storage_mb = 32768\n' + auth + ha + pub(n) + tags() + "}\n")
            tfmap[f"azurerm_postgresql_flexible_server.{lab}"] = [n["id"]]
        elif t == "cosmos_db":
            body.append(head("azurerm_cosmosdb_account", lab, f'"cosmos-{lab}-${{local.suffix}}"') + '  offer_type = "Standard"\n  kind       = "GlobalDocumentDB"\n\n  consistency_policy {\n    consistency_level = "Session"\n  }\n\n  geo_location {\n    location          = var.location\n    failover_priority = 0\n'
                        + ('    zone_redundant    = true\n' if n["props"].get("multi_az") else "") + "  }\n" + pub(n) + ("  local_authentication_disabled = true\n" if mi(n) else "") + tags() + "}\n")
            tfmap[f"azurerm_cosmosdb_account.{lab}"] = [n["id"]]
        elif t == "data_lake":
            body.append(head("azurerm_storage_account", lab, f'"st${{substr(replace(local.suffix, "-", ""), 0, 14)}}{lab[:6].replace("_", "")}"') + f'  account_tier              = "Standard"\n  account_replication_type  = "{"ZRS" if n["props"].get("multi_az") else "LRS"}"\n  is_hns_enabled            = true\n  min_tls_version           = "TLS1_2"\n'
                        + pub(n) + ("  shared_access_key_enabled = false\n" if mi(n) else "") + tags() + "}\n")
            tfmap[f"azurerm_storage_account.{lab}"] = [n["id"]]
        elif t == "sql_database":
            body.append(head("azurerm_mssql_server", lab, f'"sql-{lab}-${{local.suffix}}"') + '  version                      = "12.0"\n  minimum_tls_version          = "1.2"\n  administrator_login          = "sqladmin"\n  administrator_login_password = var.sql_admin_password\n' + pub(n) + tags() + "}\n")
            tfmap[f"azurerm_mssql_server.{lab}"] = [n["id"]]
        elif t == "api_management":
            body.append(head("azurerm_api_management", lab, f'"apim-{lab}-${{local.suffix}}"') + '  publisher_name  = var.owner\n  publisher_email = var.publisher_email\n  sku_name        = var.apim_sku\n' + ('  identity {\n    type = "SystemAssigned"\n  }\n' if mi(n) else "") + tags() + "}\n")
            tfmap[f"azurerm_api_management.{lab}"] = [n["id"]]
        elif t == "kafka" and n["technology"] == "Azure Event Hubs":
            body.append(head("azurerm_eventhub_namespace", lab, f'"evh-{lab}-${{local.suffix}}"') + '  sku      = "Standard"\n  capacity = 1\n' + tags() + "}\n")
        elif t == "kafka":
            body.append(f"# {n['name']}: Apache Kafka on Confluent is provisioned with the Confluent provider, which the Studio does not generate.\n")
        elif t in ("app_service", "function"):
            plans.add("plan")
    hosts = [n for n in nodes if n["type"] == "aks_cluster"]
    if hosts:
        ids = [n["id"] for n in hosts]
        priv = any(n["props"].get("public_network_access") is False for n in nodes)
        body.append(head("azurerm_kubernetes_cluster", "aks", '"aks-${local.suffix}"') + f'  dns_prefix = "aks-${{local.suffix}}"\n  sku_tier   = "Standard"\n' + ("  private_cluster_enabled   = true\n" if priv else "") + ('  oidc_issuer_enabled       = true\n  workload_identity_enabled = true\n' if any(mi(n) for n in hosts) else "")
                    + f'\n  default_node_pool {{\n    name       = "system"\n    vm_size    = "Standard_D4s_v5"\n    node_count = {max([n["props"].get("instances") or 1 for n in hosts] + [1])}\n' + ('    zones      = ["1", "2", "3"]\n' if any(n["props"].get("multi_az") for n in hosts) else "")
                    + "  }\n\n  identity {\n    type = \"SystemAssigned\"\n  }\n" + tags() + "}\n")
        tfmap["azurerm_kubernetes_cluster.aks"] = ids
    apps = [n for n in nodes if n["type"] in ("app_service", "function")]
    if apps:
        body.append('resource "azurerm_service_plan" "plan" {\n  name                = "plan-${local.suffix}"\n  location            = var.location\n  resource_group_name = azurerm_resource_group.this.name\n  os_type             = "Linux"\n  sku_name            = var.app_plan_sku\n  tags                = var.tags\n}\n')
        if any(n["type"] == "function" for n in apps):
            body.append('resource "azurerm_storage_account" "functions" {\n  name                     = "stfn${substr(replace(local.suffix, "-", ""), 0, 18)}"\n  location                 = var.location\n  resource_group_name      = azurerm_resource_group.this.name\n  account_tier             = "Standard"\n  account_replication_type = "LRS"\n  min_tls_version          = "TLS1_2"\n  tags                     = var.tags\n}\n')
        kv = next((n for n in nodes if n["type"] == "key_vault"), None)
        for n in apps:
            lab = _tf_label(n["id"])
            ident = '  identity {\n    type = "SystemAssigned"\n  }\n' if mi(n) else ""
            settings = ""
            if n["props"].get("secrets_store") == "key_vault" and kv:
                settings = f'  app_settings = {{\n    "EXAMPLE_SECRET" = "@Microsoft.KeyVault(SecretUri=${{azurerm_key_vault.{_tf_label(kv["id"])}.vault_uri}}secrets/replace-with-secret-name/)"\n  }}\n'
            tls = '    minimum_tls_version = "1.2"\n' if n["props"].get("tls_min") == "1.2" else ""
            if n["type"] == "app_service":
                body.append(head("azurerm_linux_web_app", lab, f'"app-{lab}-${{local.suffix}}"') + f'  service_plan_id = azurerm_service_plan.plan.id\n  https_only      = true\n\n  site_config {{\n{tls}  }}\n' + ident + settings + tags() + "}\n")
                tfmap[f"azurerm_linux_web_app.{lab}"] = [n["id"]]
            else:
                body.append(head("azurerm_linux_function_app", lab, f'"func-{lab}-${{local.suffix}}"') + f'  service_plan_id               = azurerm_service_plan.plan.id\n  storage_account_name          = azurerm_storage_account.functions.name\n  storage_uses_managed_identity = true\n  https_only                    = true\n\n  site_config {{\n{tls}  }}\n'
                            + (ident or '  identity {\n    type = "SystemAssigned"\n  }\n') + settings + tags() + "}\n")
                tfmap[f"azurerm_linux_function_app.{lab}"] = [n["id"]]
    if pe_needed:
        body.append('resource "azurerm_virtual_network" "this" {\n  name                = "vnet-${local.suffix}"\n  location            = var.location\n  resource_group_name = azurerm_resource_group.this.name\n  address_space       = var.address_space\n  tags                = var.tags\n}\n')
        body.append('resource "azurerm_subnet" "private" {\n  name                 = "snet-private"\n  resource_group_name  = azurerm_resource_group.this.name\n  virtual_network_name = azurerm_virtual_network.this.name\n  address_prefixes     = [var.private_subnet_prefix]\n}\n')
        zones: dict[str, str] = {}
        for n in pe_needed:
            sub, zone = PE_SPEC[n["type"]]
            zl = re.sub(r"[^a-z0-9]", "_", zone)
            if zone not in zones:
                zones[zone] = zl
                body.append(f'resource "azurerm_private_dns_zone" "{zl}" {{\n  name                = "{zone}"\n  resource_group_name = azurerm_resource_group.this.name\n  tags                = var.tags\n}}\n')
                body.append(f'resource "azurerm_private_dns_zone_virtual_network_link" "{zl}" {{\n  name                  = "link-{zl}"\n  resource_group_name   = azurerm_resource_group.this.name\n  private_dns_zone_name = azurerm_private_dns_zone.{zl}.name\n  virtual_network_id    = azurerm_virtual_network.this.id\n}}\n')
            lab = _tf_label(n["id"])
            rtype = next(k.split(".")[0] for k, v in tfmap.items() if n["id"] in v and k.endswith("." + lab))
            body.append(f'resource "azurerm_private_endpoint" "{lab}" {{\n  name                = "pe-{lab}-${{local.suffix}}"\n  location            = var.location\n  resource_group_name = azurerm_resource_group.this.name\n  subnet_id           = azurerm_subnet.private.id\n\n'
                        f'  private_service_connection {{\n    name                           = "psc-{lab}"\n    private_connection_resource_id = {rtype}.{lab}.id\n    subresource_names              = ["{sub}"]\n    is_manual_connection           = false\n  }}\n\n'
                        f'  private_dns_zone_group {{\n    name                 = "default"\n    private_dns_zone_ids = [azurerm_private_dns_zone.{zones[zone]}.id]\n  }}\n\n  tags = var.tags\n}}\n')
    if diag:
        body.append('resource "azurerm_log_analytics_workspace" "this" {\n  name                = "log-${local.suffix}"\n  location            = var.location\n  resource_group_name = azurerm_resource_group.this.name\n  sku                 = "PerGB2018"\n  retention_in_days   = 30\n  tags                = var.tags\n}\n')
        for n in diag:
            lab = _tf_label(n["id"])
            rt = next((k.split(".")[0] for k, v in tfmap.items() if n["id"] in v and k.endswith("." + lab)), None)
            if rt:
                body.append(f'resource "azurerm_monitor_diagnostic_setting" "{lab}" {{\n  name                       = "diag-{lab}"\n  target_resource_id         = {rt}.{lab}.id\n  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id\n\n  enabled_log {{\n    category_group = "allLogs"\n  }}\n}}\n')
    tag_map = (f'  default = {{\n    owner               = "{owner}"\n    cost_centre         = "CC-0000"\n    data_classification = "{cls}"\n    managed_by          = "terraform"\n  }}\n' if tags_ok else '  default = {\n    managed_by = "terraform"\n  }\n')
    providers = ('terraform {\n  required_version = ">= 1.6.0"\n\n  required_providers {\n    azurerm = {\n      source  = "hashicorp/azurerm"\n      version = "~> 3.110"\n    }\n  }\n}\n\nprovider "azurerm" {\n  features {}\n}\n\ndata "azurerm_client_config" "current" {}\n')
    vars_ = [f'variable "tags" {{\n  type = map(string)\n{tag_map}}}\n', f'variable "name" {{\n  type        = string\n  description = "Workload name used in resource names."\n  default     = "{slug(design["title"])[:18]}"\n}}\n', 'variable "environment" {\n  type    = string\n  default = "dev"\n}\n',
             f'variable "location" {{\n  type    = string\n  default = "{sel["region"]}"\n}}\n', f'variable "owner" {{\n  type    = string\n  default = "{owner}"\n}}\n']
    if pe_needed:
        vars_ += ['variable "address_space" {\n  type    = list(string)\n  default = ["10.40.0.0/16"]\n}\n', 'variable "private_subnet_prefix" {\n  type    = string\n  default = "10.40.16.0/24"\n}\n']
    if any(n["type"] == "postgres" and not mi(n) for n in nodes):
        vars_.append('variable "postgres_admin_password" {\n  type      = string\n  sensitive = true\n}\n')
    if any(n["type"] == "sql_database" for n in nodes):
        vars_.append('variable "sql_admin_password" {\n  type      = string\n  sensitive = true\n}\n')
    if any(n["type"] == "api_management" for n in nodes):
        vars_ += ['variable "publisher_email" {\n  type = string\n}\n', 'variable "apim_sku" {\n  type        = string\n  description = "Developer_1 is for non-production use. Choose the SKU for your tier."\n  default     = "Developer_1"\n}\n']
    if apps:
        vars_.append('variable "app_plan_sku" {\n  type    = string\n  default = "P1v3"\n}\n')
    main = 'locals {\n  suffix = "${var.name}-${var.environment}"\n}\n\n' + "\n".join(body)
    outputs = 'output "resource_group_name" {\n  value = azurerm_resource_group.this.name\n}\n'
    return {"infra/terraform/providers.tf": providers, "infra/terraform/variables.tf": "\n".join(vars_), "infra/terraform/main.tf": main, "infra/terraform/outputs.tf": outputs}, tfmap


def check_terraform(arch: dict, files: dict[str, str], tfmap: dict[str, list[str]]) -> list[dict]:
    """Read the generated Terraform back with ArchIQ's own HCL reader and compare it with the design on the attributes Terraform can express."""
    text = "\n".join(files[p] for p in sorted(files) if p.endswith(".tf"))
    checks: list[dict] = []

    def add(label: str, ok: bool, detail: str) -> None:
        checks.append(dict(label=label, status="pass" if ok else "fail", detail=detail))

    add("Terraform braces balanced", text.count("{") == text.count("}"), f"{text.count('{')} opening and {text.count('}')} closing")
    try:
        parsed = std._parse_hcl(text)
    except Exception as e:  # noqa: BLE001
        add("Terraform is read by the ArchIQ HCL reader", False, str(e)[:160])
        return checks
    add("Terraform is read by the ArchIQ HCL reader", True, f"{len(parsed['components'])} resource(s) recognised")
    by_label = {c["id"]: c for c in parsed["components"]}
    nodes = {n["id"]: n for n in arch["nodes"]}
    for key, ids in tfmap.items():
        rtype, lab = key.split(".", 1)
        c = by_label.get(lab)
        if not c:
            add(f"{key} is recognised", False, "the reader did not find it")
            continue
        n = nodes[ids[0]]
        mism = []
        for k in ("public_network_access", "tls_min", "region"):
            dv, iv = n["props"].get(k), c.get(k)
            if dv is not None and iv is not None and dv != iv:
                mism.append(f"{k}: design {dv}, Terraform {iv}")
        if n["props"].get("auth") == "managed_identity":
            if rtype == "azurerm_postgresql_flexible_server":  # Entra ID sign-in is an `authentication` block, which the reader does not interpret
                body = text[text.index(f'resource "{rtype}" "{lab}"'):]
                if not re.search(r"password_auth_enabled\s*=\s*false", body.split("\nresource ")[0]):
                    mism.append("auth: design managed_identity, Terraform still allows passwords")
            elif c.get("auth") != "managed_identity":
                mism.append("auth: design managed_identity, Terraform not")
        if n["props"].get("tags_complete") is True and c.get("tags_complete") is not True:
            mism.append("tags: design complete, Terraform incomplete")
        add(f"{key} agrees with the design", not mism, "; ".join(mism) or f"{n['name']}: public access, TLS, region, identity and tags match")
    pubs = [n for n in arch["nodes"] if n["props"].get("public_network_access") is False and n["type"] in PE_SPEC]
    missing = [n["name"] for n in pubs if not any(re.search(rf'azurerm_private_endpoint" "{_tf_label(n["id"])}"', text) for _ in (0,))]
    add("Every service with public access off has a private endpoint", not missing, "none missing" if not missing else ", ".join(missing))
    return checks


# ------------------------------------------------------------------ service starters
def _api_nodes(arch: dict) -> list[dict]:
    return [n for n in arch["nodes"] if n["role"] in ("api", "compute", "ai_agent")]


def openapi(arch: dict, design: dict) -> str:
    svc = _api_nodes(arch)
    paths: dict = {"/healthz": {"get": {"operationId": "getHealth", "summary": "Liveness", "responses": {"200": {"description": "Healthy", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Health"}}}}}}}}
    for n in svc:
        s = slug(n["name"])
        paths[f"/v1/{s}"] = {"get": {"operationId": "list_" + s.replace("-", "_"), "summary": f"{n['name']}: placeholder operation", "description": "Replace with the real contract before use.",
                                     "responses": {"200": {"description": "Placeholder", "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}, "default": {"description": "Error", "content": {"application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}}}}}}
    doc = {"openapi": "3.1.0", "info": {"title": design["title"], "version": "0.1.0", "description": "Starter contract generated by ArchIQ. Placeholder operations only."}, "paths": paths,
           "components": {"schemas": {"Health": {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}, "Problem": {"type": "object", "properties": {"type": {"type": "string"}, "title": {"type": "string"}, "status": {"type": "integer"}}}}}}
    return yaml.safe_dump(doc, sort_keys=False)


def service_files(arch: dict, design: dict) -> dict[str, str]:
    sel = arch["selections"]
    b = sel["backend"]
    title = design["title"]
    s = slug(title)
    files: dict[str, str] = {}
    routes = [(slug(n["name"]), n["name"]) for n in _api_nodes(arch)]
    if b == "python":
        body = [f'"""{title}: service skeleton generated by ArchIQ. Placeholder routes return 501 until implemented."""', "from fastapi import FastAPI, HTTPException", "", f'app = FastAPI(title="{title}", version="0.1.0")', "", "", '@app.get("/healthz", tags=["ops"])',
                "def healthz() -> dict[str, str]:", '    return {"status": "ok"}', ""]
        for r, nm in routes:
            fn = r.replace("-", "_")
            body += ["", f'@app.get("/v1/{r}", tags=["{nm}"])', f"def list_{fn}() -> list[dict]:", f'    raise HTTPException(status_code=501, detail="{nm}: not implemented")', ""]
        files["service/app/__init__.py"] = ""
        files["service/app/main.py"] = "\n".join(body) + "\n"
        files["service/tests/test_health.py"] = 'from fastapi.testclient import TestClient\n\nfrom app.main import app\n\nclient = TestClient(app)\n\n\ndef test_health() -> None:\n    assert client.get("/healthz").json() == {"status": "ok"}\n'
        files["service/requirements.txt"] = "fastapi>=0.115,<1\nuvicorn[standard]>=0.30\nhttpx>=0.27\npytest>=8.2\n"
        files["service/Dockerfile"] = ('FROM python:3.12-slim\nENV PYTHONUNBUFFERED=1\nRUN useradd --system --uid 10001 --no-create-home appuser\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY app ./app\nUSER 10001\nEXPOSE 8080\n'
                                       'HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen(\'http://127.0.0.1:8080/healthz\')"\nCMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]\n')
    elif b in ("java17", "java8"):
        pkg = re.sub(r"[^a-z0-9]", "", s) or "service"
        ver = "3.3.4" if b == "java17" else "2.7.18"
        jv = "17" if b == "java17" else "8"
        files["service/pom.xml"] = (f'<?xml version="1.0" encoding="UTF-8"?>\n<project xmlns="http://maven.apache.org/POM/4.0.0">\n  <modelVersion>4.0.0</modelVersion>\n  <parent>\n    <groupId>org.springframework.boot</groupId>\n    <artifactId>spring-boot-starter-parent</artifactId>\n    <version>{ver}</version>\n    <relativePath/>\n  </parent>\n'
                                    f'  <groupId>com.example.{pkg}</groupId>\n  <artifactId>{s}</artifactId>\n  <version>0.1.0</version>\n  <properties>\n    <java.version>{jv}</java.version>\n  </properties>\n  <dependencies>\n    <dependency>\n      <groupId>org.springframework.boot</groupId>\n      <artifactId>spring-boot-starter-web</artifactId>\n    </dependency>\n'
                                    '    <dependency>\n      <groupId>org.springframework.boot</groupId>\n      <artifactId>spring-boot-starter-actuator</artifactId>\n    </dependency>\n  </dependencies>\n</project>\n')
        files[f"service/src/main/java/com/example/{pkg}/Application.java"] = f"package com.example.{pkg};\n\nimport org.springframework.boot.SpringApplication;\nimport org.springframework.boot.autoconfigure.SpringBootApplication;\n\n@SpringBootApplication\npublic class Application {{\n    public static void main(String[] args) {{\n        SpringApplication.run(Application.class, args);\n    }}\n}}\n"
        files["service/src/main/resources/application.yml"] = "server:\n  port: 8080\nmanagement:\n  endpoints:\n    web:\n      exposure:\n        include: health\n"
    elif b == "dotnet8":
        files["service/Service.csproj"] = '<Project Sdk="Microsoft.NET.Sdk.Web">\n  <PropertyGroup>\n    <TargetFramework>net8.0</TargetFramework>\n    <Nullable>enable</Nullable>\n  </PropertyGroup>\n</Project>\n'
        files["service/Program.cs"] = 'var app = WebApplication.CreateBuilder(args).Build();\napp.MapGet("/healthz", () => Results.Ok(new { status = "ok" }));\napp.Run();\n'
    else:
        files["service/package.json"] = json.dumps({"name": s, "version": "0.1.0", "private": True, "scripts": {"start": "node server.js"}, "dependencies": {"express": "^4.19.0"}}, indent=2) + "\n"
        files["service/server.js"] = "const express = require('express');\nconst app = express();\napp.get('/healthz', (_req, res) => res.json({ status: 'ok' }));\napp.listen(8080);\n"
    files[f"openapi/{s}.yaml"] = openapi(arch, design)
    return files


def check_service(files: dict[str, str]) -> list[dict]:
    checks = codegen.validate({p: c for p, c in files.items() if not p.endswith(".tf")})
    for p, c in files.items():
        if p.endswith((".csproj",)):
            try:
                ET.fromstring(c)
                checks.append(dict(label="Project file is well-formed XML", status="pass", detail=p))
            except ET.ParseError as e:
                checks.append(dict(label="Project file is well-formed XML", status="fail", detail=f"{p}: {e}"))
        if p.endswith("package.json"):
            try:
                json.loads(c)
                checks.append(dict(label="package.json parses", status="pass", detail=p))
            except ValueError as e:
                checks.append(dict(label="package.json parses", status="fail", detail=str(e)))
        if p.endswith("pom.xml"):
            try:
                ET.fromstring(c.encode())
                checks.append(dict(label="Maven POM is well-formed XML", status="pass", detail=p))
            except ET.ParseError as e:
                checks.append(dict(label="Maven POM is well-formed XML", status="fail", detail=f"{p}: {e}"))
    for c in checks:
        if c["label"] == "Container runs as non-root":
            c["detail"] = c["detail"] + " (service/Dockerfile)"
    return checks


# ------------------------------------------------------------------ the ZIP
def starter(design: dict, arch: dict, val: dict, doc_md: str) -> dict:
    """All files for the starter, the checks that were run on them, and what was not checked."""
    sel = arch["selections"]
    s = slug(design["title"])
    files: dict[str, str] = {}
    notes: list[str] = []
    files["docs/target-architecture.md"] = doc_md
    files["docs/validation.json"] = json.dumps(dict(readiness=val["readiness"], verdict=val["verdict"], counts=val["counts"], open_counts=val["open_counts"], coverage=val["coverage"], gaps=[{k: g[k] for k in ("id", "severity", "title", "state", "recommendation", "components")} for g in val["gaps"]]), indent=2) + "\n"
    files["diagrams/architecture.mmd"] = mermaid(arch)
    files["diagrams/architecture.svg"] = svg(arch, design["title"])
    files["diagrams/architecture.json"] = json.dumps(dict(blueprint=arch["blueprint_id"], direction=arch["direction"], nodes=[{k: n[k] for k in ("id", "name", "role", "type", "technology", "props", "pos")} for n in arch["nodes"]],
                                                          edges=[{k: e.get(k) for k in ("source", "target", "label", "dashed")} for e in arch["edges"]]), indent=2) + "\n"
    files["config/archiq-design.json"] = json.dumps(dict(title=design["title"], domain=design.get("domain"), blueprint_id=arch["blueprint_id"], selections=sel, nfr=design.get("nfr") or {}, ops=design.get("ops") or [], linked_apps=design.get("linked_apps") or []), indent=2) + "\n"
    files["config/standards-input.json"] = json.dumps(dict(name=design["title"], nfr=design.get("nfr") or {}, components=[dict(c) for c in studio_rules.components_of(arch)]), indent=2, default=str) + "\n"
    files["config/nfr.yaml"] = yaml.safe_dump({"tier": sel["tier"], **(design.get("nfr") or {})}, sort_keys=False)
    checks: list[dict] = []
    tfmap: dict[str, list[str]] = {}
    if sel["cloud"] != "azure":
        notes.append(f"No infrastructure starter was generated: the Studio's starters are Azure-only and the chosen cloud is {next(c['label'] for c in cat.CLOUDS if c['id'] == sel['cloud'])}.")
    elif sel["iac"] == "bicep":
        notes.append("No infrastructure starter was generated: Bicep was chosen and the Studio generates Terraform only. Use docs/target-architecture.md and config/standards-input.json as the specification.")
    else:
        tf, tfmap = terraform(arch, design)
        files.update(tf)
        checks += check_terraform(arch, tf, tfmap)
        if sel["iac"] == "none":
            notes.append("No infrastructure-as-code tool was chosen. Terraform is included as one possible starting point.")
    svc = service_files(arch, design)
    files.update(svc)
    checks += check_service(svc)
    for p, c in files.items():
        if p.endswith(".json"):
            try:
                json.loads(c)
            except ValueError as e:
                checks.append(dict(label="JSON file parses", status="fail", detail=f"{p}: {e}"))
        if p.endswith((".yaml", ".yml")) and not p.startswith("openapi/"):
            try:
                yaml.safe_load(c)
            except yaml.YAMLError as e:
                checks.append(dict(label="YAML file parses", status="fail", detail=f"{p}: {e}"))
    checks.append(dict(label="Diagram files agree with the model", status="pass" if len(re.findall(r"<rect x=", files["diagrams/architecture.svg"])) == len(arch["nodes"]) + 0 else "fail", detail=f"{len(arch['nodes'])} components in the SVG and the model"))
    passed = sum(c["status"] == "pass" for c in checks)
    failed = [c for c in checks if c["status"] == "fail"]
    not_run = ["terraform init, terraform validate and terraform plan", "Building the container image", "Running the service's own tests", "Deploying anything to a cloud account", "Checking against your cloud policies and landing zone"]
    readme = [f"# {design['title']}: starter pack\n",
              "Generated by ArchIQ Blueprint Intelligence Studio from the customised blueprint. It contains the architecture, its documentation and starter files for the choices made.\n",
              "## What this is not\n",
              "**These files are starting points, not deployable infrastructure.** They have been checked only in the ways listed below. None of them has been applied to a cloud account, and the infrastructure code has not been through `terraform validate` or `plan`. "
              "Treat them as a draft for your platform team to review, complete and validate in your pipeline.\n",
              f"## Checks run on these files ({passed} passed, {len(failed)} failed)\n",
              _table(["Check", "Result", "Detail"], [[c["label"], c["status"], c["detail"]] for c in checks]),
              "## Not checked\n", *[f"- {x}" for x in not_run], "",
              "## Contents\n", _table(["File", "What it is"], [[p, _what(p)] for p in sorted(files)])]
    if notes:
        readme += ["## Notes\n", *[f"- {x}" for x in notes], ""]
    readme += ["## Architecture status\n", f"Readiness {val['readiness']}%, verdict {val['verdict'].replace('_', ' ')}, {val['open_counts']['critical']} critical and {val['open_counts']['high']} high gaps open. See docs/target-architecture.md.\n"]
    files["README.md"] = "\n".join(readme) + "\n"
    manifest = [dict(path=p, bytes=len(c.encode()), what=_what(p), checked_by=_checked_by(p)) for p, c in sorted(files.items())]
    return dict(files=files, checks=checks, not_run=not_run, notes=notes, manifest=manifest, root=s, passed=passed, failed=len(failed), tfmap=tfmap)


def _what(p: str) -> str:
    if p.startswith("infra/terraform"):
        return "Terraform starter for the Azure resources in the design"
    if p.startswith("openapi/"):
        return "OpenAPI 3.1 contract with placeholder operations"
    if p.startswith("service/"):
        return "Service skeleton for the chosen backend"
    return {"README.md": "Read this first: status, checks, what was not checked", "docs/target-architecture.md": "Target architecture document", "docs/validation.json": "Validation results and gaps as data",
            "diagrams/architecture.mmd": "Diagram as Mermaid text", "diagrams/architecture.svg": "Diagram as an image", "diagrams/architecture.json": "Editable architecture model",
            "config/archiq-design.json": "The design inputs: choices, requirements and edits", "config/standards-input.json": "Components in the format of the ArchIQ standards checker", "config/nfr.yaml": "Non-functional targets"}.get(p, "")


def _checked_by(p: str) -> str:
    if p.endswith(".tf"):
        return "ArchIQ HCL reader and design comparison (not Terraform)"
    if p.endswith(".py"):
        return "Python parser"
    if p.startswith("openapi/") or p.endswith((".yaml", ".yml")):
        return "YAML parser, OpenAPI structure checks"
    if p.endswith((".json", ".csproj", "pom.xml")):
        return "Parsed"
    if p.endswith("Dockerfile"):
        return "Non-root user and healthcheck present"
    if p.endswith(".svg"):
        return "Component count matches the model"
    return "Not applicable"


def zip_bytes(pack: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p, c in sorted(pack["files"].items()):
            info = zipfile.ZipInfo(f"{pack['root']}/{p}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, c)
    return buf.getvalue()
