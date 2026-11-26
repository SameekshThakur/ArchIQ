"""Blueprint Intelligence Studio, steps 3 to 6: build an editable architecture from a blueprint, validate it with the existing engines, and turn the results into gaps.

How an architecture comes about (always recomputed from its inputs, never stored as a diagram):
    blueprint diagram (parsed)  ->  structural edits (add, remove, rename, connect)  ->  choices (cloud, LLM, data, backend, deployment, security controls)
    ->  derived properties  ->  property edits made by the person.

Honesty rules:
* A property only exists if a choice, the blueprint's own label, the Azure platform default, a derivation from the diagram, or the person set it. Everything else stays unspecified
  and the standards engine reports "not specified".
* Validation reads the design as declared. Nothing is verified against a deployed environment, and the results say so.
* Components the standards library does not describe (other clouds, generic services) are listed as not assessed. They are never counted as passing.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict, deque
from typing import Any

from app.core.errors import BadRequest
from app.mock_ai.generators import blueprints as bp_gen
from app.mock_ai.generators import studio_catalog as cat
from app.mock_ai.rules import assessment, review as review_engine, standards as std
from app.repositories.store import get_store

ID_RX = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
NODE_W, NODE_H = 220, 76
SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
OPS = {"add_node", "remove_node", "update_node", "add_edge", "remove_edge", "move_node"}
EU_REGIONS = {"westeurope", "northeurope", "uksouth"}
COVERAGE_FLOOR = 70

TYPE_LABEL = {"aks_cluster": "AKS service", "app_service": "App Service", "function": "Azure Function", "api_management": "API Management", "api": "API", "azure_openai": "Azure OpenAI", "llm_api_external": "Public LLM API",
              "ai_search": "Azure AI Search", "ai_agent": "AI agent", "key_vault": "Key Vault", "storage_account": "Storage account", "sql_database": "SQL database", "postgres": "PostgreSQL", "cosmos_db": "Cosmos DB",
              "data_lake": "Data lake", "kafka": "Event streaming", "integration": "Integration", "x_compute": "Compute (not assessed)", "x_edge": "Gateway (not assessed)", "x_search": "Search (not assessed)",
              "x_llm": "LLM (not assessed)", "x_database": "Database (not assessed)", "x_object_store": "Object store (not assessed)", "x_cache": "Cache (not assessed)", "x_messaging": "Messaging (not assessed)",
              "x_secrets": "Secrets (not assessed)", "x_pipeline": "Pipeline (not assessed)", "x_control": "Control (not assessed)", "x_external": "Existing system", "actor": "Users and channels"}

PROP_LABEL = dict(public_network_access="Public network access", tls_min="Minimum TLS version", encryption_at_rest="Encryption at rest", secrets_store="Secrets held in", auth="Authentication", logging="Security logging",
                  waf="WAF", internet_facing="Internet-facing", data_classification="Data classification", cmk="Customer-managed keys", pii="Holds personal data", pii_masking="PII masking", retention_days="Retention (days)",
                  region="Region", provisioned_by="Provisioned by", tags_complete="Mandatory tags", content_filter="Content filter", human_in_loop="Human in the loop", audit_logging="Audit prompts and responses",
                  multi_az="Zone redundant", backup="Backups", instances="Instances", tier="Criticality tier", gateway="Behind the gateway", versioned="Versioned", contract="API contract", style="Integration style")
PROP_CHOICES = dict(tls_min=["1.0", "1.1", "1.2", "1.3"], auth=["managed_identity", "oauth2", "mtls", "api_key", "password"], secrets_store=["key_vault", "env_vars", "config_file"], content_filter=["off", "standard", "strict"],
                    contract=["openapi", "asyncapi", "none"], style=["api", "event", "esb", "direct_db"], provisioned_by=["terraform", "bicep", "portal"], data_classification=["public", "internal", "confidential", "restricted"],
                    tier=["tier1", "tier2", "tier3"])
PROP_NUMBER = {"retention_days", "instances"}


def prop_schema() -> dict[str, list[dict]]:
    """Which properties each component type has, derived from the standards that apply to it. This is what the editor offers, nothing more."""
    s = get_store()
    out: dict[str, set[str]] = defaultdict(set)
    for x in s.standards:
        if x["kind"] != "policy":
            continue
        attrs = {c["attr"] for c in (x.get("check"), x.get("when")) if c and c["attr"] != "never"}
        for t in x.get("applies_to") or []:
            out[t] |= attrs
    regions = next(x["check"]["value"] for x in s.standards if x["id"] == "STD-CLD-001")
    res = {}
    for t, attrs in out.items():
        rows = []
        for a in sorted(attrs):
            kind = "number" if a in PROP_NUMBER else "choice" if (a in PROP_CHOICES or a == "region") else "bool"
            rows.append(dict(key=a, label=PROP_LABEL.get(a, a), kind=kind, options=(regions if a == "region" else PROP_CHOICES.get(a))))
        res[t] = rows
    return res


# ------------------------------------------------------------------ selections
def normalise_selections(sel: dict | None, pattern_id: str) -> dict:
    base = cat.default_selections(pattern_id)
    merged = {**base, **{k: v for k, v in (sel or {}).items() if k in cat_keys()}}
    errs = []

    def ok(key: str, allowed: list[str]) -> None:
        if merged.get(key) is not None and merged[key] not in allowed:
            errs.append(f"{key}: '{merged[key]}' is not one of {', '.join(allowed)}")

    ok("cloud", [c["id"] for c in cat.CLOUDS])
    ok("region", [r["id"] for r in cat.REGIONS])
    ok("llm", [x["id"] for x in cat.LLMS])
    ok("backend", [x["id"] for x in cat.BACKENDS])
    ok("messaging", [x["id"] for x in cat.MESSAGING])
    ok("iac", [x["id"] for x in cat.IAC])
    ok("exposure", [x["id"] for x in cat.EXPOSURE])
    ok("tier", [x["id"] for x in cat.TIERS])
    if merged.get("classification"):
        ok("classification", [x["id"] for x in cat.CLASSIFICATIONS])
    if merged.get("cloud") in cat.DEPLOYMENTS:
        ok("deployment", [d["id"] for d in cat.DEPLOYMENTS[merged["cloud"]]])
    dbs = merged.get("databases") or []
    if not isinstance(dbs, list) or any(d not in {x["id"] for x in cat.DATABASES} for d in dbs):
        errs.append("databases: unknown data store")
    bad = [p for p in (merged.get("posture") or []) if p not in cat.POSTURE_IDS]
    if bad:
        errs.append(f"posture: unknown control {', '.join(bad)}")
    for k in ("instances", "retention_days"):
        v = merged.get(k)
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 1 or v > 100000):
            errs.append(f"{k}: must be a whole number of at least 1")
    if errs:
        raise BadRequest("Invalid choices: " + "; ".join(errs))
    merged["databases"] = list(dict.fromkeys(dbs))
    merged["posture"] = [p for p in cat.POSTURE_IDS if p in set(merged.get("posture") or [])]
    merged.setdefault("tier", "tier2")
    return merged


def cat_keys() -> set[str]:
    return {"cloud", "region", "deployment", "llm", "databases", "backend", "messaging", "iac", "exposure", "classification", "posture", "instances", "retention_days", "tier", "personal_data"}


def clean_nfr(nfr: dict | None) -> dict:
    out: dict[str, Any] = {}
    for k, v in (nfr or {}).items():
        if v in (None, "", []):
            continue
        if k == "availability":
            try:
                f = float(v)
            except (TypeError, ValueError):
                raise BadRequest("availability must be a percentage such as 99.9") from None
            if not 90 <= f <= 100:
                raise BadRequest("availability must be between 90 and 100 percent")
            out[k] = f"{f:g}"
        elif k in ("rto_hours", "rpo_minutes", "latency_ms", "throughput_tps"):
            try:
                f = float(v)
            except (TypeError, ValueError):
                raise BadRequest(f"{k} must be a number") from None
            if f < 0:
                raise BadRequest(f"{k} cannot be negative")
            out[k] = int(f) if f.is_integer() else round(f, 3)
        elif k == "compliance":
            items = v if isinstance(v, list) else [x.strip() for x in str(v).split(",")]
            out[k] = [str(x).strip() for x in items if str(x).strip()]
        else:
            out[k] = v
    return out


# ------------------------------------------------------------------ build
def _new_node(n: dict, origin: str) -> dict:
    return dict(id=n["id"], label=n.get("label") or n.get("name"), name=n.get("name") or n.get("label"), role=n["role"], shape=n.get("shape", "box"), group=n.get("group"), declared=dict(n.get("declared") or {}), origin=origin,
                estate_id=n.get("estate_id"), estate_kind=n.get("estate_kind"), overrides=dict(props={}, type=None, technology=None), pos=None)


def _check_ops(ops: list[dict]) -> None:
    for i, o in enumerate(ops):
        if not isinstance(o, dict) or o.get("op") not in OPS:
            raise BadRequest(f"Edit {i + 1}: unknown operation")
        if o["op"] in ("add_node", "remove_node", "update_node", "move_node") and not ID_RX.match(str(o.get("id", ""))):
            raise BadRequest(f"Edit {i + 1}: a component id starts with a letter and has at most 32 letters, digits, '_' or '-'")
        if o["op"] == "add_node" and o.get("role") not in cat.ROLE_LABEL:
            raise BadRequest(f"Edit {i + 1}: unknown role '{o.get('role')}'")
        if o["op"] == "update_node" and o.get("role") is not None and o["role"] not in cat.ROLE_LABEL:
            raise BadRequest(f"Edit {i + 1}: unknown role '{o['role']}'")
        if o["op"] in ("add_edge", "remove_edge") and not (o.get("source") and o.get("target")):
            raise BadRequest(f"Edit {i + 1}: a connection needs a source and a target")
        if o["op"] == "move_node" and not all(isinstance(o.get(k), (int, float)) for k in ("x", "y")):
            raise BadRequest(f"Edit {i + 1}: a position needs numeric x and y")
        if o["op"] in ("add_node", "update_node") and o.get("props") is not None and not isinstance(o["props"], dict):
            raise BadRequest(f"Edit {i + 1}: props must be an object")


def build(pattern_id: str, selections: dict | None, ops: list[dict] | None = None, nfr: dict | None = None, req: dict | None = None) -> dict:
    if pattern_id not in bp_gen.BLUEPRINTS:
        raise BadRequest(f"Unknown blueprint {pattern_id}")
    sel = normalise_selections(selections, pattern_id)
    ops = list(ops or [])
    _check_ops(ops)
    g = cat.blueprint_graph(pattern_id)
    nodes: dict[str, dict] = {n["id"]: _new_node(n, "blueprint") for n in g["nodes"]}
    edges: list[dict] = [dict(source=e["source"], target=e["target"], label=e["label"], dashed=e["dashed"], blocked=e["blocked"], origin="blueprint") for e in g["edges"]]
    notes: list[str] = []
    skipped: list[dict] = []
    removed_ids: set[str] = set()

    if sel["llm"] == "none":
        for nid in [i for i, n in nodes.items() if n["role"] == "ai_llm"]:
            removed_ids.add(nid)
            del nodes[nid]
        edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]
        notes.append("No LLM was chosen, so the LLM components of the blueprint were left out.")

    # ---- structural edits and overrides, in the order the person made them
    for o in ops:
        kind = o["op"]
        if kind == "add_node":
            if o["id"] in nodes:
                skipped.append(dict(op=o, reason=f"A component with id {o['id']} already exists"))
                continue
            nodes[o["id"]] = _new_node(dict(id=o["id"], name=str(o.get("name") or cat.ROLE_LABEL[o["role"]])[:60], role=o["role"]), "added")
            nodes[o["id"]]["overrides"]["props"].update(o.get("props") or {})
            if o.get("technology"):
                nodes[o["id"]]["overrides"]["technology"] = str(o["technology"])
            removed_ids.discard(o["id"])
        elif kind == "remove_node":
            if o["id"] not in nodes:
                skipped.append(dict(op=o, reason=f"No component {o['id']} in this architecture"))
                continue
            removed_ids.add(o["id"])
            del nodes[o["id"]]
            edges = [e for e in edges if e["source"] != o["id"] and e["target"] != o["id"]]
        elif kind == "update_node":
            n = nodes.get(o["id"])
            if not n:
                skipped.append(dict(op=o, reason=f"No component {o['id']} in this architecture"))
                continue
            if o.get("name"):
                n["name"] = str(o["name"])[:60]
            if o.get("role"):
                n["role"] = o["role"]
            if "technology" in o:
                n["overrides"]["technology"] = o["technology"] or None
            if "type" in o:
                n["overrides"]["type"] = o["type"] or None
            for k, v in (o.get("props") or {}).items():
                if v is None:
                    n["overrides"]["props"].pop(k, None)
                else:
                    n["overrides"]["props"][k] = v
        elif kind == "add_edge":
            if o["source"] not in nodes or o["target"] not in nodes or o["source"] == o["target"]:
                skipped.append(dict(op=o, reason="Both ends of a connection must be different components in this architecture"))
                continue
            if any(e["source"] == o["source"] and e["target"] == o["target"] for e in edges):
                skipped.append(dict(op=o, reason="That connection already exists"))
                continue
            edges.append(dict(source=o["source"], target=o["target"], label=str(o.get("label") or "")[:40], dashed=bool(o.get("dashed")), blocked=False, origin="added"))
        elif kind == "remove_edge":
            before = len(edges)
            edges = [e for e in edges if not (e["source"] == o["source"] and e["target"] == o["target"])]
            if len(edges) == before:
                skipped.append(dict(op=o, reason="No such connection"))
        elif kind == "move_node":
            if o["id"] in nodes:
                nodes[o["id"]]["pos"] = dict(x=float(o["x"]), y=float(o["y"]))

    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        incoming[e["target"]].append(e["source"])
        outgoing[e["source"]].append(e["target"])

    # ---- derive types and properties from the choices
    ctx = dict(sel=sel, nodes=nodes, incoming=incoming, outgoing=outgoing, edges=edges, req=req or {})
    ctx["entries"] = {nid for nid, n in nodes.items() if n["role"] not in ("actor", "external") and (any(nodes[s]["role"] == "actor" for s in incoming[nid] if s in nodes) or (not incoming[nid] and n["role"] in ("edge", "api", "compute")))}
    ctx["db_index"] = 0
    out_nodes: list[dict] = []
    for nid in list(nodes):
        out_nodes.append(_derive(nodes[nid], ctx))

    # ---- controls that add a component
    added = _controls(out_nodes, edges, sel, notes)
    for n in added:
        out_nodes.append(n)

    byid = {n["id"]: n for n in out_nodes}
    # ---- property edits made by the person win over everything derived
    for n in out_nodes:
        ov = n.pop("overrides")
        if ov["type"]:
            n["type"] = ov["type"]
        if ov["technology"] is not None:
            n["technology"] = ov["technology"]
        for k, v in ov["props"].items():
            n["props"][k] = v
            n["prop_origin"][k] = "edited"
        n["assessed"] = n["type"] in cat.covered_types()
        n["type_label"] = TYPE_LABEL.get(n["type"], n["type"])
        n["role_label"] = cat.ROLE_LABEL[n["role"]]
        if n.get("estate_id"):
            n["estate"] = _estate_info(n["estate_id"], n.get("estate_kind"))
    # ---- connections get ids; positions come from the layout unless the person moved the component
    edge_out = []
    for i, e in enumerate(edges):
        if e["source"] in byid and e["target"] in byid:
            edge_out.append(dict(e, id=f"{e['source']}__{e['target']}"))
    _layout(out_nodes, edge_out, g["direction"])
    return dict(blueprint_id=pattern_id, direction=g["direction"], nodes=out_nodes, edges=edge_out, selections=sel, notes=notes, skipped_ops=skipped, removed_blueprint_nodes=sorted(removed_ids & {n["id"] for n in g["nodes"]}),
                node_size=dict(w=NODE_W, h=NODE_H))


def _estate_info(eid: str, kind: str | None) -> dict | None:
    s = get_store()
    if kind == "database":
        d = next((x for x in s.dbs if x["id"] == eid), None)
        return d and dict(id=d["id"], kind="database", name=d["name"], lifecycle=d["lifecycle"], criticality=d["criticality"], technology=d["engine"], domain=d["domain"], owner_app=d["owner_app"], classification=d["classification"])
    a = next((x for x in s.apps if x["id"] == eid), None)
    return a and dict(id=a["id"], kind="application", name=a["name"], lifecycle=a["lifecycle"], criticality=a["criticality"], technology=", ".join(a["tech"][:3]), domain=a["domain"], owner_app=a["id"])


def _derive(n: dict, ctx: dict) -> dict:
    sel, role = ctx["sel"], n["role"]
    cloud = sel["cloud"]
    posture = set(sel["posture"])
    azure = cloud == "azure"
    props: dict[str, Any] = {}
    origin: dict[str, str] = {}

    def setp(k: str, v: Any, why: str) -> None:
        if v is not None:
            props[k] = v
            origin[k] = why

    typ, tech, hosting = "x_control", None, None
    backend = next((b for b in cat.BACKENDS if b["id"] == sel["backend"]), cat.BACKENDS[0])
    dep = next((d for d in cat.DEPLOYMENTS[cloud] if d["id"] == sel["deployment"]), cat.DEPLOYMENTS[cloud][0])
    if role == "actor":
        typ = "actor"
    elif role == "external":
        typ = "x_external"
    elif role == "edge":
        typ, tech = cat.EDGE_SERVICE[cloud]
    elif role == "api":
        typ, tech = "api", backend["technology"]
        hosting = dict(label=dep["label"], technology=dep["technology"])
    elif role == "compute":
        typ, tech = dep["type"], backend["technology"]
        hosting = dict(label=dep["label"], technology=dep["technology"])
    elif role == "ai_agent":
        typ, tech = "ai_agent", backend["technology"]
        hosting = dict(label=dep["label"], technology=dep["technology"])
    elif role == "ai_llm":
        llm = next(x for x in cat.LLMS if x["id"] == sel["llm"])
        typ, tech = llm["type"] or "x_llm", llm["technology"]
    elif role == "ai_search":
        typ, tech = cat.SEARCH_SERVICE[cloud]
    elif role == "messaging":
        m = next(x for x in cat.MESSAGING if x["id"] == sel["messaging"])
        if azure:
            typ, tech = m["azure"]
        else:
            typ, tech = "x_messaging", m["alt"][cloud]
    elif role == "integration":
        style = _integration_style(n["label"])
        typ = "integration" if style else "x_pipeline"
        if style:
            setp("style", style, "derived from the blueprint label")
    elif role == "security":
        if re.search(r"key vault", n["label"], re.I):
            typ, tech = cat.SECRETS_SERVICE[cloud]
        else:
            typ = "x_control"
    elif role == "database":
        typ, tech = _pick_database(n, ctx)

    covered = typ in cat.covered_types() and azure_type(typ)
    # defaults the Azure platform applies on its own
    if covered and typ in cat.AZURE_DEFAULTS:
        for k, v in cat.AZURE_DEFAULTS[typ].items():
            setp(k, v, "Azure platform default")
    # what the blueprint's own diagram states about this node
    if n["declared"] and typ in cat.PAAS:
        for k, v in n["declared"].items():
            if k in ("public_network_access", "auth"):
                setp(k, v, "stated in the blueprint diagram")
    if covered:
        if "private_endpoints" in posture and typ in cat.PAAS:
            setp("public_network_access", False, "control: private endpoints only")
        if "tls12" in posture:
            setp("tls_min", "1.2", "control: TLS 1.2 or higher")
        if "diagnostics" in posture:
            setp("logging", True, "control: security logging")
        if "mandatory_tags" in posture:
            setp("tags_complete", True, "control: mandatory tags")
        setp("region", sel["region"], "your region choice")
        if sel["iac"] in ("terraform", "bicep"):
            setp("provisioned_by", sel["iac"], "your infrastructure-as-code choice")
        if typ in ("api_management", "app_service", "aks_cluster", "function", "api", "azure_openai", "ai_agent", "postgres", "sql_database"):
            if "managed_identity" in posture:
                setp("auth", "managed_identity", "control: managed identity")
        if typ in cat.HOSTING_TYPES or typ in ("api", "ai_agent"):
            setp("tier", sel["tier"], "your tier choice")
            if typ in cat.HOSTING_TYPES:
                if "key_vault_secrets" in posture and azure:
                    setp("secrets_store", "key_vault", "control: secrets in Key Vault")
                if "high_availability" in posture:
                    setp("multi_az", True, "control: zone redundancy")
                if sel.get("instances"):
                    setp("instances", sel["instances"], "your instance count")
                elif "high_availability" in posture:
                    setp("instances", 2, "control: at least two instances")
        if typ in cat.DATA_TYPES:
            setp("tier", sel["tier"], "your tier choice")
            if sel.get("classification"):
                setp("data_classification", sel["classification"], "your classification choice")
            if sel.get("retention_days"):
                setp("retention_days", sel["retention_days"], "your retention choice")
            if "backups" in posture:
                setp("backup", True, "control: backups")
            if "high_availability" in posture:
                setp("multi_az", True, "control: zone redundancy")
            if "customer_managed_keys" in posture:
                setp("cmk", True, "control: customer-managed keys")
            if sel.get("personal_data"):
                setp("pii", True, "the requirements mention personal data")
                if "pii_masking" in posture:
                    setp("pii_masking", True, "control: PII masking")
        if typ == "azure_openai":
            if "content_filter" in posture:
                setp("content_filter", "standard", "control: content filtering")
            if "human_in_loop" in posture:
                setp("human_in_loop", True, "control: human in the loop")
            if "audit_logging" in posture:
                setp("audit_logging", True, "control: audit prompts and responses")
        if typ == "ai_agent":
            if "human_in_loop" in posture:
                setp("human_in_loop", True, "control: human in the loop")
            if "audit_logging" in posture:
                setp("audit_logging", True, "control: audit prompts and responses")
    # properties that follow from the diagram itself
    if typ in ("api_management", "app_service", "aks_cluster", "function", "api") and role in ("edge", "compute", "api"):
        entry = n["id"] in ctx["entries"]
        setp("internet_facing", bool(entry and sel["exposure"] == "internet"), "derived: entry point and exposure choice" if entry else "derived: reached only through other components")
        if entry and "waf" in posture and typ in ("api_management", "app_service"):
            setp("waf", True, "control: WAF")
    if typ == "api":
        edge_ids = [i for i, x in ctx["nodes"].items() if x["role"] == "edge"]
        if edge_ids:
            behind = any(_reaches(ctx["outgoing"], e, n["id"]) for e in edge_ids)
            setp("gateway", behind, "derived from the connections")
        else:
            setp("gateway", False, "derived: the architecture has no gateway")
        if "api_governance" in posture:
            setp("versioned", True, "control: versioned APIs")
            setp("contract", "openapi", "control: OpenAPI contract")
    if typ == "integration" and role == "integration":
        pass
    node = dict(id=n["id"], name=n["name"], label=n["label"], role=role, type=typ, technology=tech, hosting=hosting, group=n["group"], shape=n["shape"], origin=n["origin"], props=props, prop_origin=origin,
                estate_id=n.get("estate_id"), estate_kind=n.get("estate_kind"), pos=n["pos"], overrides=n["overrides"], notes=[])
    if role == "ai_llm" and sel["llm"] in ("public_api",):
        node["notes"].append("The standards prohibit sending enterprise data to a public LLM API (STD-AI-004).")
    if not covered and role not in ("actor", "external"):
        node["notes"].append("The standards library does not describe this component, so it cannot be assessed.")
    return node


def azure_type(t: str) -> bool:
    return not t.startswith("x_") and t != "actor"


def _reaches(out: dict[str, list[str]], src: str, dst: str) -> bool:
    seen, q = {src}, deque([src])
    while q:
        cur = q.popleft()
        for nxt in out.get(cur, []):
            if nxt == dst:
                return True
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return False


def _integration_style(label: str) -> str | None:
    low = label.lower()
    if re.search(r"relay|outbox|cdc|change data|projection|event", low):
        return "event"
    if re.search(r"translator|adapter|facade|\bacl\b|anti-corruption", low):
        return "api"
    return None


def _pick_database(n: dict, ctx: dict) -> tuple[str, str]:
    sel = ctx["sel"]
    cloud = sel["cloud"]
    picks = [d for d in cat.DATABASES if d["id"] in sel["databases"]] or [cat.DATABASES[0]]
    low = n["label"].lower()
    lake = re.search(r"lake|bronze|silver|gold|delta", low)
    chosen = None
    if lake:
        chosen = next((d for d in picks if d["id"] == "data_lake"), None)
    if not chosen and re.search(r"audit|trace|memory|log\b|case context", low):
        chosen = next((d for d in picks if d["id"] == "cosmos_db"), None)
    if not chosen:
        pool = [d for d in picks if d["id"] != "data_lake"] or picks
        chosen = pool[ctx["db_index"] % len(pool)]
        ctx["db_index"] += 1
    if cloud == "azure":
        return chosen["azure"]
    return chosen["generic"], chosen["alt"][cloud]


def _controls(nodes: list[dict], edges: list[dict], sel: dict, notes: list[str]) -> list[dict]:
    """Controls that need a component of their own. Only a Key Vault today, and only when the person asked for secrets to be held there."""
    added: list[dict] = []
    if "key_vault_secrets" not in sel["posture"] or sel["cloud"] != "azure":
        return added
    hosts = [n for n in nodes if n["type"] in cat.HOSTING_TYPES or n["type"] == "ai_agent"]
    if not hosts or any(n["type"] == "key_vault" for n in nodes):
        return added
    kv_props = dict(cat.AZURE_DEFAULTS["key_vault"])
    origin = {k: "Azure platform default" for k in kv_props}
    p = set(sel["posture"])
    if "private_endpoints" in p:
        kv_props["public_network_access"], origin["public_network_access"] = False, "control: private endpoints only"
    for key, cond, val, why in (("logging", "diagnostics", True, "control: security logging"), ("tags_complete", "mandatory_tags", True, "control: mandatory tags")):
        if cond in p:
            kv_props[key], origin[key] = val, why
    if "tls12" in p:
        kv_props["tls_min"], origin["tls_min"] = "1.2", "control: TLS 1.2 or higher"
    kv_props["region"], origin["region"] = sel["region"], "your region choice"
    if sel["iac"] in ("terraform", "bicep"):
        kv_props["provisioned_by"], origin["provisioned_by"] = sel["iac"], "your infrastructure-as-code choice"
    kv = dict(id="KV-CTL", name="Key Vault", label="Key Vault", role="security", type="key_vault", technology="Azure Key Vault", hosting=None, group=None, shape="box", origin="control", props=kv_props, prop_origin=origin,
              estate_id=None, estate_kind=None, pos=None, overrides=dict(props={}, type=None, technology=None), notes=["Added because the control 'Secrets in Key Vault' is on and the blueprint has no key vault."])
    added.append(kv)
    for h in hosts:
        edges.append(dict(source=h["id"], target="KV-CTL", label="secrets", dashed=True, blocked=False, origin="control"))
    notes.append("A Key Vault was added because the control 'Secrets in Key Vault' is on and the blueprint has none.")
    return added


# ------------------------------------------------------------------ layout
def _layout(nodes: list[dict], edges: list[dict], direction: str) -> None:
    ids = [n["id"] for n in nodes]
    out: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = {i: 0 for i in ids}
    for e in edges:
        out[e["source"]].append(e["target"])
    # drop edges that close a cycle, so that depth is well defined
    color: dict[str, int] = {}
    back: set[tuple[str, str]] = set()
    incoming = {e["target"] for e in edges}
    roots = [i for i in ids if i not in incoming] or ids[:1]
    for r in roots + ids:
        if color.get(r):
            continue
        stack = [(r, iter(out[r]))]
        color[r] = 1
        while stack:
            node, it = stack[-1]
            for nxt in it:
                if color.get(nxt) == 1:
                    back.add((node, nxt))
                elif not color.get(nxt):
                    color[nxt] = 1
                    stack.append((nxt, iter(out[nxt])))
                    break
            else:
                color[node] = 2
                stack.pop()
    dag = [(e["source"], e["target"]) for e in edges if (e["source"], e["target"]) not in back]
    for _, t in dag:
        indeg[t] += 1
    depth = {i: 0 for i in ids}
    q = deque(i for i in ids if indeg[i] == 0)
    adj: dict[str, list[str]] = defaultdict(list)
    for s_, t in dag:
        adj[s_].append(t)
    while q:
        cur = q.popleft()
        for nxt in adj[cur]:
            depth[nxt] = max(depth[nxt], depth[cur] + 1)
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    connected = {e["source"] for e in edges} | {e["target"] for e in edges}
    maxd = max([depth[i] for i in connected], default=0)
    for n in nodes:
        if n["id"] not in connected:
            depth[n["id"]] = min(maxd, cat.ROLE_LAYER.get(n["role"], 2))
    cols: dict[int, list[dict]] = defaultdict(list)
    for n in nodes:
        cols[depth[n["id"]]].append(n)
    tallest = max((len(c) for c in cols.values()), default=1)
    gap_a, gap_b = (NODE_W + 70, NODE_H + 34) if direction == "LR" else (NODE_H + 60, NODE_W + 30)
    for d, col in cols.items():
        for k, n in enumerate(col):
            a = 40 + d * gap_a
            b = 40 + (k + (tallest - len(col)) / 2) * gap_b
            n["auto_pos"] = dict(x=a, y=b) if direction == "LR" else dict(x=b, y=a)
            n["pos"] = n["pos"] or n["auto_pos"]
            n["depth"] = d


# ------------------------------------------------------------------ validation
def components_of(arch: dict) -> list[dict]:
    comps = []
    for n in arch["nodes"]:
        if n["role"] == "actor":
            continue
        c = dict(n["props"])
        c.update(id=n["id"], type=n["type"], technology=n["technology"], name=n["name"])
        comps.append(c)
    return comps


def inputs_hash(inputs: dict) -> str:
    keep = {k: inputs.get(k) for k in ("blueprint_id", "selections", "nfr", "ops", "linked_apps")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _gid(prefix: str, key: str) -> str:
    return f"{prefix}:{key}"


def _sev(status: str, sev: str) -> str:
    if status == "fail":
        return "low" if sev == "info" else sev
    return "low" if sev in ("low", "info") else "medium"


POSTURE_FOR_STD = {sid: p["id"] for p in cat.POSTURE for sid in p["standards"]}
TECH_FIX = {
    "Java 8": dict(selections_set=dict(backend="java17"), label="Use Java 17 (Spring Boot 3)", alternatives=[dict(selections_set=dict(backend="dotnet8"), label="Use C# on .NET 8"), dict(selections_set=dict(backend="python"), label="Use Python 3.11 (FastAPI)")]),
    "Node.js 18": dict(selections_set=dict(backend="node20"), label="Use Node.js 20", alternatives=[dict(selections_set=dict(backend="python"), label="Use Python 3.11 (FastAPI)")]),
    "Oracle 12c": dict(databases_replace={"oracle_12c": "postgres"}, label="Replace Oracle 12c with PostgreSQL 15", alternatives=[dict(databases_replace={"oracle_12c": "oracle_19c"}, label="Upgrade to Oracle 19c"), dict(databases_replace={"oracle_12c": "cosmos_db"}, label="Replace with Cosmos DB")]),
}


def _fix_for_standard(r: dict, arch: dict, sel: dict) -> dict | None:
    sid = r["standard_id"]
    if r["kind"] == "approved_technology":
        tech = r["title"]
        f = TECH_FIX.get(tech)
        if f and ((f.get("selections_set") and sel.get("backend") != next(iter(f["selections_set"].values()))) or f.get("databases_replace")):
            return dict(f)
        return None
    if sid == "STD-AI-004":
        return dict(label="Use Azure OpenAI, reached privately", selections_set=dict(llm="azure_openai"), posture_add=["private_endpoints"])
    if sid == "STD-INT-001" and not any(n["role"] == "edge" for n in arch["nodes"]):
        return gateway_fix(arch)
    if sid in POSTURE_FOR_STD:
        p = next(x for x in cat.POSTURE if x["id"] == POSTURE_FOR_STD[sid])
        if p["id"] in sel["posture"]:
            return None  # the control is on and the standard still fails: a property was edited by hand, so a manual fix is needed
        return dict(label=f"Turn on: {p['label']}", posture_add=[p["id"]])
    if sid == "STD-SEC-010":
        return dict(label="Set a data classification", input=dict(field="selections.classification", kind="choice", label="Data classification", options=[c["id"] for c in cat.CLASSIFICATIONS]))
    if sid == "STD-DAT-002":
        return dict(label="Set a retention period", input=dict(field="selections.retention_days", kind="number", label="Retention (days)", min=1, max=36500))
    if sid == "STD-CLD-001":
        return dict(label="Choose an approved region", input=dict(field="selections.region", kind="choice", label="Region", options=[x for x in std_regions()]))
    if sid == "STD-CLD-002":
        return dict(label="Provision with Terraform", selections_set=dict(iac="terraform"))
    if sid == "STD-SEC-001":
        ops = [dict(op="update_node", id=c, props=dict(encryption_at_rest=True)) for c in r["components"]]
        return dict(label="Enable encryption at rest", ops=ops)
    if sid == "STD-SEC-015":
        ops = [dict(op="update_node", id=c, props=dict(style="api")) for c in r["components"]]
        return dict(label="Replace direct database access with an API", ops=ops)
    return None


def gateway_fix(arch: dict) -> dict:
    """Put a gateway between the users and the first services they reach. When the diagram has no users, the services that nothing else calls are the entry points."""
    by = {n["id"]: n for n in arch["nodes"]}
    actors = {n["id"] for n in arch["nodes"] if n["role"] == "actor"}
    targets = {e["target"] for e in arch["edges"]}
    fronts = [e for e in arch["edges"] if e["source"] in actors and by.get(e["target"], {}).get("role") in ("api", "compute", "ai_agent")]
    ops: list[dict] = [dict(op="add_node", id="GW-ADD", role="edge", name="API gateway")]
    for e in fronts:
        ops += [dict(op="remove_edge", source=e["source"], target=e["target"]), dict(op="add_edge", source=e["source"], target="GW-ADD")]
    entry_ids = list(dict.fromkeys(e["target"] for e in fronts)) or [n["id"] for n in arch["nodes"] if n["role"] in ("api", "compute", "ai_agent") and n["id"] not in targets]
    ops += [dict(op="add_edge", source="GW-ADD", target=t) for t in entry_ids]
    return dict(label="Add an API gateway in front of the entry points", ops=ops)


def std_regions() -> list[str]:
    return next(x["check"]["value"] for x in get_store().standards if x["id"] == "STD-CLD-001")


def validate(arch: dict, nfr: dict, tier: str, linked_apps: list[str], title: str, domain: str, req: dict | None = None, decisions: dict | None = None) -> dict:
    s = get_store()
    sel = arch["selections"]
    comps = components_of(arch)
    name_of = {n["id"]: n["name"] for n in arch["nodes"]}
    nfr = clean_nfr(nfr)
    sub = dict(id="STUDIO", title=title or "Untitled architecture", domain=domain or "", tier=tier, nfr=nfr, components=comps, linked_apps=sorted(set(linked_apps) | {n["estate_id"] for n in arch["nodes"] if n.get("estate_kind") == "application" and n.get("estate_id")}),
               summary="", stage="draft", submitter="", submitted_at="", arb_date="")
    rev = review_engine.review(sub)
    sres = rev["standards"]
    std_by_id = {r["standard_id"]: r for r in sres["results"]}
    gaps: list[dict] = []

    def gap(key: str, source: str, severity: str, title_: str, detail: str, evidence: list[dict], comps_: list[str], recommendation: str, fix: dict | None = None, standard_id: str | None = None, category: str = "") -> None:
        gaps.append(dict(id=key, source=source, severity=severity, title=title_, detail=detail, evidence=evidence, components=comps_, component_names=[name_of.get(c, c) for c in comps_], recommendation=recommendation, fix=fix,
                         standard_id=standard_id, category=category or source))

    # ---- standards (existing engine)
    for r in sres["results"]:
        if r["status"] == "pass":
            continue
        ev = [dict(kind="standard", id=r["standard_id"], label=r["rationale"])] + [dict(kind="component", id=c, label=name_of.get(c, c)) for c in r["components"][:6]]
        key = _gid("std", r["standard_id"] + (":" + r["title"] if r["kind"] == "approved_technology" else ""))
        prev = next((g for g in gaps if g["id"] == key), None)
        if prev:  # one technology used by several components is one gap
            prev["components"] += [c for c in r["components"] if c not in prev["components"]]
            prev["component_names"] = [name_of.get(c, c) for c in prev["components"]]
            prev["evidence"] += [e for e in ev if e not in prev["evidence"]]
            continue
        gap(key, "standards", _sev(r["status"], r["severity"]), f"{r['standard_id']}: {r['title']}", r["rationale"], ev, r["components"],
            r["remediation"] or r["statement"], _fix_for_standard(r, arch, sel), r["standard_id"], r["category"])

    # ---- NFR coverage and consistency (existing engine)
    nfr_fix_defaults = cat.TIER_NFR_DEFAULTS[tier]
    for f in rev["findings"]:
        if f["source"] == "nfr":
            m = re.match(r"NFR not stated: (.+)", f["title"])
            key = (m.group(1).replace(" ", "_") if m else re.sub(r"\W+", "_", f["title"].lower())[:30])
            fix = None
            if m and key in nfr_fix_defaults:
                fix = dict(label=f"Set {m.group(1)} to the {tier} default ({nfr_fix_defaults[key]})", nfr={key: nfr_fix_defaults[key]})
            elif m and key == "compliance":
                fix = dict(label="State the regulations that apply", input=dict(field="nfr.compliance", kind="text", label="Regulations (comma separated)"))
            elif m:
                fix = dict(label=f"State a {m.group(1)} target", input=dict(field=f"nfr.{key}", kind="number", label=m.group(1).capitalize(), min=0))
            elif f["title"].startswith("Availability target"):
                fix = dict(label=f"Raise availability to {cat.TIER_NFR_DEFAULTS[tier]['availability']}%", nfr=dict(availability=cat.TIER_NFR_DEFAULTS[tier]["availability"]))
            elif "single instance" in f["title"] and "high_availability" not in sel["posture"]:
                fix = dict(label="Turn on: zone redundancy and at least two instances", posture_add=["high_availability"])
            elif f["title"].startswith("RPO") and "high_availability" not in sel["posture"]:
                fix = dict(label="Turn on: zone redundancy and at least two instances", posture_add=["high_availability"])
            gap(_gid("nfr", key), "nfr", f["severity"], f["title"], f["recommendation"], f["evidence"], [], f["recommendation"], fix, None, "nfr")
        elif f["source"] == "risk":
            fid = f["evidence"][0]["id"]
            gap(_gid("risk", fid), "risk", f["severity"], f["title"], "A linked application in the estate has this finding. The design should not deepen the dependency.", f["evidence"], [], f["recommendation"], None, None, "estate risk")

    # ---- extra deterministic checks
    # technology lifecycle, from the technology catalogue
    flagged_tech = {r["title"] for r in sres["results"] if r["kind"] == "approved_technology" and r["status"] != "pass"}
    seen: set[str] = set()
    for n in arch["nodes"]:
        for t in [n["technology"]] + ([n["hosting"]["technology"]] if n.get("hosting") else []):
            if not t or t in seen or t in flagged_tech:
                continue
            note = cat.tech_notice(t)
            if note and note["lifecycle"] in ("eol", "extended"):
                seen.add(t)
                gap(_gid("tech", t), "lifecycle", "high" if note["lifecycle"] == "eol" else "low", f"{t} is {'end-of-life' if note['lifecycle'] == 'eol' else 'in extended support'}",
                    f"{t} reaches end of support in {note['support_end'] or 'an unknown month'} according to the technology catalogue. {note['estate_apps']} estate application(s) already use it.",
                    [dict(kind="technology", id=t, label=f"{note['lifecycle']}, support ends {note['support_end']}")], [x["id"] for x in arch["nodes"] if t in (x["technology"], (x.get("hosting") or {}).get("technology"))],
                    f"Choose a supported alternative to {t}, or record the exception with an end date.", None, None, "lifecycle")
    # existing systems this design depends on
    for n in arch["nodes"]:
        est = n.get("estate")
        if est and est["lifecycle"] in ("eol", "extended"):
            gap(_gid("dependency", n["id"]), "dependency", "medium" if est["lifecycle"] == "eol" else "low", f"Depends on {est['name']}, which is {'end-of-life' if est['lifecycle'] == 'eol' else 'in extended support'}",
                f"{est['name']} ({est['id']}) is a {est['criticality']} system in {est['domain']}.", [dict(kind="application" if est["kind"] == "application" else "database", id=est["id"], label=f"{est['name']}: {est['lifecycle']}")], [n["id"]],
                "Confirm the design does not deepen the dependency and agree a retirement or replacement date.", None, None, "estate risk")
    # missing components
    entries = [n for n in arch["nodes"] if n["role"] not in ("actor", "external") and n["props"].get("internet_facing") is True]
    has_edge = any(n["role"] == "edge" for n in arch["nodes"])
    if sel["exposure"] == "internet" and not has_edge and entries:
        gap("missing:gateway", "missing", "high", "Internet-facing entry point has no gateway", "Internet traffic reaches the services directly. There is no API gateway to authenticate, throttle and inspect it.",
            [dict(kind="component", id=x["id"], label=x["name"]) for x in entries[:4]], [x["id"] for x in entries], "Put an API gateway in front of the internet-facing entry points.", gateway_fix(arch), None, "missing component")
    for rid in arch["removed_blueprint_nodes"]:
        bn = next((x for x in cat.blueprint_graph(arch["blueprint_id"])["nodes"] if x["id"] == rid), None)
        if bn and bn["role"] in ("security", "ai_llm", "database", "messaging", "edge", "ai_search") and not any(x["role"] == bn["role"] for x in arch["nodes"]) and not (bn["role"] == "ai_llm" and sel["llm"] == "none"):
            gap(_gid("missing", "role-" + bn["role"]), "missing", "medium", f"Blueprint component removed: {bn['name']}", f"The blueprint includes {cat.ROLE_LABEL[bn['role']].lower()}, and this design no longer has any.",
                [dict(kind="blueprint", id=arch["blueprint_id"], label=f"{bn['label']}")], [], "Restore the component, or record why this design does not need it.", dict(label=f"Restore {bn['name']}", ops_drop=[dict(op="remove_node", id=rid)]), None, "missing component")
    if req and "Kafka or event streaming" in (req.get("matched_signals") or []) and not any(n["role"] == "messaging" for n in arch["nodes"]):
        gap("missing:messaging", "missing", "medium", "Event streaming is required but the architecture has no messaging component", "The requirements describe event streaming. No component carries the events.", [], [], "Add an event stream, or change the requirement.",
            dict(label="Add an event stream", ops=[dict(op="add_node", id="MSG-ADD", role="messaging", name="Event stream")]), None, "missing component")
    # isolated components
    edge_nodes = {e["source"] for e in arch["edges"]} | {e["target"] for e in arch["edges"]}
    for n in arch["nodes"]:
        if n["id"] not in edge_nodes and len(arch["nodes"]) > 1 and n["role"] != "actor":
            gap(_gid("conn", n["id"]), "completeness", "low", f"{n['name']} is not connected to anything", "A component with no connections is either unused or missing its connections.", [dict(kind="component", id=n["id"], label=n["name"])], [n["id"]],
                "Connect it to the components that use it, or remove it.", dict(label=f"Remove {n['name']}", ops=[dict(op="remove_node", id=n["id"])]), None, "completeness")
    # residency
    if req and req.get("residency") and sel["region"] not in EU_REGIONS:
        gap("residency:region", "residency", "high", "Region is outside Europe but the requirements call for European data residency", f"The requirements say: \"{req['residency']['evidence']}\" The chosen region is {sel['region']}.",
            [dict(kind="requirement", id="residency", label=req["residency"]["evidence"])], [], "Choose a European region.", dict(label="Choose a European region", input=dict(field="selections.region", kind="choice", label="Region", options=sorted(EU_REGIONS))), None, "residency")
    # components on a different cloud than the one chosen
    if sel["cloud"] != "azure" and any(n["type"] in ("azure_openai",) for n in arch["nodes"]):
        ids = [n["id"] for n in arch["nodes"] if n["type"] == "azure_openai"]
        gap("cloud:azure_openai", "cloud", "low", "Azure OpenAI is used from a non-Azure architecture", f"The architecture is on {next(c['label'] for c in cat.CLOUDS if c['id'] == sel['cloud'])} but the LLM is Azure OpenAI, so model calls leave that cloud.",
            [dict(kind="choice", id="llm", label="LLM: Azure OpenAI")], ids, "Confirm the cross-cloud call is acceptable, or choose an LLM on the same cloud.", None, None, "architecture")

    # ---- decisions made by the person
    decisions = decisions or {}
    for g in gaps:
        d = decisions.get(g["id"])
        g["decision"] = d
        g["state"] = (d or {}).get("status") or "open"
    gaps.sort(key=lambda g: (SEV_RANK[g["severity"]], g["source"], g["id"]))
    open_gaps = [g for g in gaps if g["state"] != "risk_accepted"]
    counts = {k: sum(1 for g in gaps if g["severity"] == k) for k in SEV_RANK}
    open_counts = {k: sum(1 for g in open_gaps if g["severity"] == k) for k in SEV_RANK}

    # ---- coverage: what the standards library could and could not look at
    judged = [n for n in arch["nodes"] if n["role"] not in ("actor", "external")]
    assessed = [n for n in judged if n["assessed"]]
    not_assessed = [dict(id=n["id"], name=n["name"], type=n["type_label"], reason=("Not an Azure resource type in the standards library." if n["type"].startswith("x_") else "No standard applies.")) for n in judged if not n["assessed"]]
    coverage = dict(assessed=len(assessed), total=len(judged), percent=round(100 * len(assessed) / len(judged)) if judged else 0, not_assessed=not_assessed)

    verdict = rev["verdict"]
    if verdict == "go" and (open_counts["critical"] or open_counts["high"]):
        verdict = "conditional"
    conditions = [f"{g['title']}: {g['recommendation']}" for g in open_gaps if g["severity"] in ("critical", "high")][:8]
    if judged and coverage["percent"] < COVERAGE_FLOOR:
        # a high score over a small assessed part of the design says little: the verdict cannot be "go"
        if verdict == "go":
            verdict = "conditional"
        conditions.append(f"Only {coverage['percent']}% of the components could be assessed by the standards library. Assess the remaining components manually before the review.")
    return dict(
        readiness=rev["readiness"], verdict=verdict, engine_verdict=rev["verdict"], standards=dict(sres, results=sres["results"]), review_counts=rev["counts"], nfr_coverage=rev["nfr_coverage"], estate_risks=rev["risks"], patterns=rev["patterns"],
        gaps=gaps, counts=counts, open_counts=open_counts, coverage=coverage, conditions=conditions, inputs=dict(tier=tier, nfr=nfr, linked_apps=sub["linked_apps"]),
        checks_run=[dict(id="standards", label="Standards compliance", detail=f"{len(sres['results'])} standards evaluated, {sres['passed']} passed, {sres['warned']} warned, {sres['failed']} failed", engine="standards.check_design"),
                    dict(id="nfr", label="Non-functional requirements", detail=f"{rev['nfr_coverage']['percent']}% of the six required targets are stated", engine="review.review"),
                    dict(id="risk", label="Estate risk of linked applications", detail=f"{len(sub['linked_apps'])} linked application(s), {len(rev['risks'])} critical or high finding(s)", engine="assessment.findings"),
                    dict(id="lifecycle", label="Technology lifecycle", detail="Technologies compared with the technology catalogue", engine="studio"),
                    dict(id="structure", label="Architecture structure", detail="Gateway, removed blueprint components, isolated components", engine="studio"),
                    dict(id="residency", label="Data residency", detail="Region compared with the residency stated in the requirements", engine="studio")],
        basis=("Properties are the design as declared: set by your choices, the blueprint's own diagram, Azure platform defaults, derivation from the connections, or your edits. Nothing was verified against a deployed environment. "
               "The readiness score and verdict come from the existing review engine; gaps from the Studio's own checks are shown beside it and can only raise the verdict's caution, never lower it."),
        notices=[dict(id="coverage", text=f"{coverage['assessed']} of {coverage['total']} components could be assessed by the standards library." + (" The rest are listed as not assessed." if not_assessed else ""))] if judged else [],
    )


# ------------------------------------------------------------------ applying a recommendation
def apply_fix(inputs: dict, fix: dict, value: Any = None) -> dict:
    """Return new inputs with the recommendation applied. Pure: the caller stores the result."""
    new = copy.deepcopy(inputs)
    sel, nfr, ops = new["selections"], new["nfr"], new["ops"]
    if fix.get("input"):
        inp = fix["input"]
        if value in (None, ""):
            raise BadRequest(f"{inp['label']} needs a value")
        if inp["kind"] == "number":
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise BadRequest(f"{inp['label']} must be a number") from None
            if "min" in inp and value < inp["min"]:
                raise BadRequest(f"{inp['label']} must be at least {inp['min']}")
            if "max" in inp and value > inp["max"]:
                raise BadRequest(f"{inp['label']} must be at most {inp['max']}")
            value = int(value) if value.is_integer() else value
        if inp["kind"] == "choice" and value not in inp.get("options", []):
            raise BadRequest(f"{inp['label']} must be one of {', '.join(inp['options'])}")
        scope, key = inp["field"].split(".", 1)
        (sel if scope == "selections" else nfr)[key] = value
    sel.update(fix.get("selections_set") or {})
    for p in fix.get("posture_add") or []:
        if p not in sel["posture"]:
            sel["posture"].append(p)
    for old, repl in (fix.get("databases_replace") or {}).items():
        sel["databases"] = list(dict.fromkeys([repl if d == old else d for d in sel["databases"]])) if old in sel["databases"] else sel["databases"]
    nfr.update(fix.get("nfr") or {})
    for d in fix.get("ops_drop") or []:
        ops[:] = [o for o in ops if not all(o.get(k) == v for k, v in d.items())]
    ops.extend(copy.deepcopy(fix.get("ops") or []))
    return new


_ = (assessment, std)
