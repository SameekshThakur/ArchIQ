"""Architecture drift detection: diff approved IaC config against the deployed configuration."""

from __future__ import annotations

import hashlib
import random
from datetime import timedelta
from functools import lru_cache

from app.repositories.store import get_store

TF_TYPE = {
    "azure_openai": "azurerm_cognitive_account", "storage_account": "azurerm_storage_account", "key_vault": "azurerm_key_vault",
    "app_service": "azurerm_linux_web_app", "function": "azurerm_linux_function_app", "aks_cluster": "azurerm_kubernetes_cluster",
    "postgres": "azurerm_postgresql_flexible_server", "cosmos_db": "azurerm_cosmosdb_account", "data_lake": "azurerm_storage_account",
    "virtual_network": "azurerm_virtual_network", "s3_bucket": "aws_s3_bucket", "ec2_instance": "aws_instance",
    "private_endpoint": "azurerm_private_endpoint", "api_management": "azurerm_api_management",
}
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def hcl_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(hcl_value(x) for x in v) + "]"
    return f'"{v}"'


def render_hcl(resource: dict, cfg: dict) -> str:
    rtype = TF_TYPE.get(resource["type"], resource["type"])
    label = resource["name"].replace("-", "_")
    lines = [f'resource "{rtype}" "{label}" {{', f'  name     = "{resource["name"]}"', f'  location = "{resource["region"]}"']
    for k in sorted(cfg):
        lines.append(f"  {k} = {hcl_value(cfg[k])}")
    lines.append("}")
    return "\n".join(lines)


def _summary(changes: list[dict]) -> str:
    for c in changes:
        if c["attribute"] in ("public_network_access", "public_endpoint") and c["deployed"] is True:
            return "Approved design says private endpoint; deployed environment uses public endpoint."
    c = changes[0]
    return f"Approved design says {c['attribute']} = {hcl_value(c['approved'])}; deployed environment uses {hcl_value(c['deployed'])}."


_state: dict[str, dict] = {}  # runtime overlay for actions (ticket, exception, remediation)


@lru_cache
def _base_items() -> list[dict]:
    s = get_store()
    items = []
    for r in s.cloud:
        if not r.get("drift_meta"):
            continue
        changes = [dict(attribute=k, approved=r["approved"].get(k), deployed=r["deployed"].get(k)) for k in sorted(r["approved"]) if r["approved"].get(k) != r["deployed"].get(k)]
        if not changes:
            continue
        app = s.by_id.get(r["app_id"]) if r["app_id"] else None
        sev = max((r["drift_meta"]["severity"],), key=lambda x: -SEV_ORDER[x])
        items.append(dict(
            resource=dict(id=r["id"], name=r["name"], type=r["type"], provider=r["provider"], region=r["region"], env=r["env"], resource_group=r["resource_group"]),
            app_id=r["app_id"], domain=r["domain"], owner=s.owner(app["owner_id"]) if app else dict(id="", name="Cloud Platform", team="Cloud Platform"),
            severity=sev, changes=changes, summary=_summary(changes), detected_at=r["drift_meta"]["detected_at"],
            base_status=r["drift_meta"]["status"], ticket=r["drift_meta"].get("ticket"), exception_expires=r["drift_meta"].get("exception_expires"),
            approved_iac=render_hcl(r, r["approved"]), deployed_config=render_hcl(r, r["deployed"]),
            standard_id="STD-SEC-014" if any(c["attribute"] == "public_network_access" for c in changes) else ("STD-SEC-002" if any("tls" in c["attribute"] for c in changes) else "STD-CLD-002"),
        ))
    items.sort(key=lambda i: (SEV_ORDER[i["severity"]] if i["resource"]["id"] not in ("CLD-0001",) else -1, i["detected_at"]), reverse=False)
    # the story item first, then by severity, newest first
    story = [i for i in items if i["resource"]["id"] == "CLD-0001"]
    rest = sorted([i for i in items if i["resource"]["id"] != "CLD-0001"], key=lambda i: (SEV_ORDER[i["severity"]], i["detected_at"]), reverse=False)
    out = story + rest
    for n, i in enumerate(out, 1):
        i["id"] = f"DR-{n:03d}"
    return out


def items() -> list[dict]:
    out = []
    for b in _base_items():
        st = _state.get(b["id"], {})
        out.append(dict(b, status=st.get("status", b["base_status"]), ticket=st.get("ticket", b["ticket"]),
                        exception_expires=st.get("exception_expires", b["exception_expires"])))
    return out


def get(item_id: str) -> dict | None:
    return next((i for i in items() if i["id"] == item_id), None)


def act(item_id: str, action: str, days: int = 30) -> dict | None:
    item = get(item_id)
    if not item:
        return None
    s = get_store()
    st = _state.setdefault(item_id, {})
    if action == "ticket":
        st["ticket"] = item["ticket"] or f"INC{int(hashlib.sha1(item_id.encode()).hexdigest()[:6], 16) % 900000 + 1000000}"
        st["status"] = "ticket_raised"
    elif action == "exception":
        st["exception_expires"] = (s.ref_date + timedelta(days=days)).date().isoformat()
        st["status"] = "exception_granted"
    elif action == "remediate":
        st["status"] = "remediating"
    return get(item_id)


def remediation_preview(item: dict) -> str:
    lines = ["# terraform plan (preview, nothing applied)", f"# ~ {item['resource']['name']} will be updated in-place", ""]
    for c in item["changes"]:
        lines.append(f"  ~ {c['attribute']:<32} = {hcl_value(c['deployed'])} -> {hcl_value(c['approved'])}")
    lines += ["", "Plan: 0 to add, 1 to change, 0 to destroy."]
    return "\n".join(lines)


def trend(weeks: int = 12) -> dict:
    from app.repositories.store import get_store as gs

    s = gs()
    cur = sum(1 for i in items() if i["status"] in ("open", "ticket_raised", "remediating"))
    r = random.Random(7)
    pts = [max(0, round(cur + (weeks - 1 - i) * r.uniform(-0.4, 0.9) + r.uniform(-2, 2))) for i in range(weeks)]
    pts[-1] = cur
    labels = [(s.ref_date - timedelta(days=7 * (weeks - 1 - i))).strftime("%d %b") for i in range(weeks)]
    detected = [max(0, round(r.uniform(1, 6))) for _ in range(weeks)]
    return dict(labels=labels, open=pts, detected=detected)


def by_domain() -> dict[str, int]:
    out: dict[str, int] = {}
    for i in items():
        out[i["domain"]] = out.get(i["domain"], 0) + 1
    return out
