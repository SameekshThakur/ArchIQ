"""Blueprint Intelligence Studio: the catalogue of choices, and how an existing blueprint becomes an editable architecture.

Nothing here invents a blueprint. The 12 blueprints stay in `blueprints.py` (diagram, components, NFR guidance, anti-patterns, standards). This module
(1) parses each blueprint's Mermaid diagram into nodes and edges, (2) gives every node a role and a type the standards engine understands, and
(3) holds the options a person can choose from (cloud, LLM, database, backend, deployment, security posture).

Honesty rules the rest of the Studio relies on:
* A component only gets a property when the platform really sets it by default (for example Azure PaaS services are reachable from the public internet
  until a private endpoint is used) or when the person chose it. Everything else stays unspecified, and the standards engine reports it as "not specified".
* Types that the standards library does not know (non-Azure services, generic services) are marked as not covered, never silently passed.
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.mock_ai.generators.blueprints import BLUEPRINTS
from app.repositories.store import get_store

# ------------------------------------------------------------------ Mermaid -> graph
_TOKEN = re.compile(
    r'\s*(?:(?P<node>[A-Za-z_]\w*)(?:\[\("(?P<cyl>[^"]*)"\)\]|\[\["(?P<stream>[^"]*)"\]\]|\["(?P<box>[^"]*)"\])?'
    r'|(?P<edge>-\.->|-\.x|-\.-|-\.\s*[\w ]+?\s*\.->|-->\|"[^"]*"\||-->))'
)


def parse_mermaid(src: str) -> dict:
    """The flowchart subset the 12 blueprints use: boxes, cylinders, streams, subgraphs, solid/dotted/blocked arrows with optional labels."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    groups: list[str] = []
    direction = "LR"
    for raw in src.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"flowchart\s+(LR|TB|TD|RL|BT)", line)
        if m:
            direction = "TB" if m.group(1) in ("TB", "TD") else "LR"
            continue
        m = re.match(r'subgraph\s+(\w+)\["([^"]*)"\]', line)
        if m:
            groups.append(m.group(2))
            continue
        if line == "end":
            if groups:
                groups.pop()
            continue
        pos, prev, pending = 0, None, None
        while pos < len(line):
            t = _TOKEN.match(line, pos)
            if not t or t.end() == pos:
                break
            pos = t.end()
            if t.group("edge"):
                pending = t.group("edge")
                continue
            nid = t.group("node")
            label = t.group("cyl") or t.group("stream") or t.group("box")
            shape = "cylinder" if t.group("cyl") is not None else "stream" if t.group("stream") is not None else "box"
            n = nodes.setdefault(nid, dict(id=nid, label=nid, shape="box", group=None))
            if label is not None:
                n.update(label=label.replace("<br/>", " "), shape=shape)
            if groups and n["group"] is None:
                n["group"] = groups[-1]
            if prev is not None and pending is not None:
                lab = re.search(r'\|"([^"]*)"\|', pending) or re.search(r"-\.\s*([\w ]+?)\s*\.->", pending)
                edges.append(dict(source=prev, target=nid, label=(lab.group(1).strip() if lab else ""), dashed=pending.startswith("-."), blocked=pending == "-.x"))
            prev, pending = nid, None
    return dict(direction=direction, nodes=list(nodes.values()), edges=edges)


# ------------------------------------------------------------------ roles
# role -> layer used for layout and for explanations in the UI
ROLE_LAYER = {"actor": 0, "edge": 1, "api": 2, "compute": 2, "ai_agent": 2, "ai_llm": 3, "ai_search": 3, "messaging": 3, "integration": 3, "database": 4, "security": 5, "external": 5}
ROLE_LABEL = {"actor": "Users and channels", "edge": "Gateway and edge", "api": "API layer", "compute": "Services", "ai_agent": "AI agent", "ai_llm": "LLM", "ai_search": "Search and retrieval",
              "messaging": "Messaging", "integration": "Integration and pipelines", "database": "Data stores", "security": "Security and network", "external": "Existing systems"}

_RULES: list[tuple[str, str]] = [  # (regex on lower-cased label, role); first match wins
    (r"bff|backend-for-frontend", "compute"),
    (r"power bi|snowflake sink", "external"),
    (r"sharepoint|confluence|claims docs|^sources?$|legacy|mainframe|db2 z/os", "external"),
    (r"api management|apim|gateway|facade|routing layer", "edge"),
    (r"openai|aoai|^llm$", "ai_llm"),
    (r"ai search|hybrid index|vector", "ai_search"),
    (r"agent runtime|planner", "ai_agent"),
    (r"key vault|private dns|dns zone|private endpoint|^policy$|azure policy|public network access", "security"),
    (r"kafka|event hub|dead-letter|topic|domain events|event stream", "messaging"),
    (r"ingest|pipeline|cdc|change data capture|relay|outbox|schema registry|translator|adapter|projection", "integration"),
    (r"adjuster|customer$|case handler|^user$|^channels?$|web app|mobile app|^web$|^mobile$|^broker$", "actor"),
]

# the few blueprint nodes whose meaning the label alone does not give
OVERRIDES: dict[tuple[str, str], dict] = {
    ("PAT-012", "PAAS"): dict(role="database", name="Protected PaaS services"),
    ("PAT-012", "PUB"): dict(name="Public network access: disabled"),
    ("PAT-008", "DB"): dict(role="database", name="Service database (table and outbox table)"),
    ("PAT-001", "DB1"): dict(role="external"), ("PAT-001", "DB2"): dict(role="external"), ("PAT-001", "DB3"): dict(role="external"),
}

# properties the blueprint's own diagram states in a label, for example "Azure OpenAI (private endpoint)"
DECLARED_HINTS: list[tuple[str, dict]] = [
    (r"\(private endpoint\)", dict(public_network_access=False, private_endpoint=True)),
    (r"\(managed identity\)", dict(auth="managed_identity")),
]


def classify(node: dict, pattern_id: str) -> str:
    ov = OVERRIDES.get((pattern_id, node["id"]), {})
    if "role" in ov:
        return ov["role"]
    label = node["label"].lower()
    if node.get("group") in ("Experience", "Process", "System"):
        return "api"
    if node["shape"] == "stream":
        return "messaging"
    for rx, role in _RULES:
        if re.search(rx, label):
            return role
    if node["shape"] == "cylinder":
        return "database"
    if re.search(r"\bdb\b|database|store|lake|bronze|silver|gold|write model|read model|memory|feature store|table", label):
        return "database"
    if re.search(r"\bapis?\b", label):
        return "api"
    return "compute"


_PAREN_TAIL = re.compile(r"\s*\([^)]*\)\s*$")


def clean_name(label: str, role: str) -> str:
    if role == "ai_llm":
        return "LLM"
    if role == "ai_search":
        return "Search index"
    name = _PAREN_TAIL.sub("", label).strip()
    if ":" in name:
        name = name.split(":", 1)[0].strip()
    return name[:60] or label


def declared_attrs(label: str) -> dict:
    out: dict = {}
    for rx, attrs in DECLARED_HINTS:
        if re.search(rx, label, re.I):
            out.update(attrs)
    return out


@lru_cache
def _estate_index() -> dict[str, dict]:
    s = get_store()
    idx: dict[str, dict] = {}
    for a in s.apps:
        idx[a["name"].lower()] = dict(estate_id=a["id"], estate_kind="application", estate_name=a["name"], estate_technology=None, estate_apps=[a["id"]])
    for d in s.dbs:
        idx[d["name"].lower()] = dict(estate_id=d["id"], estate_kind="database", estate_name=d["name"], estate_technology=d["engine"], estate_apps=[d["owner_app"]])
    return idx


def estate_match(label: str) -> dict | None:
    """An exact (case-insensitive) match against an estate application or database name: the label, or the text inside its brackets."""
    idx = _estate_index()
    cands = [label.lower().strip()] + [m.lower().strip() for m in re.findall(r"\(([^)]*)\)", label)]
    return next((idx[c] for c in cands if c in idx), None)


# ------------------------------------------------------------------ choices
CLOUDS = [
    dict(id="azure", label="Microsoft Azure", note="The cloud the standards library is written for. Every standards check applies.", covered=True),
    dict(id="aws", label="Amazon Web Services", note="Components are not assessed by the standards library, which is Azure-specific. The validation says so.", covered=False),
    dict(id="gcp", label="Google Cloud", note="Components are not assessed by the standards library, which is Azure-specific. The validation says so.", covered=False),
    dict(id="hybrid", label="Hybrid or on-premises", note="Components are not assessed by the standards library, which is Azure-specific. The validation says so.", covered=False),
]

# (type, technology) per cloud; "x_" types are deliberately unknown to the standards engine
DEPLOYMENTS = {
    "azure": [dict(id="aks", label="Azure Kubernetes Service", type="aks_cluster", technology="AKS"), dict(id="app_service", label="Azure App Service", type="app_service", technology="Azure App Service"),
              dict(id="functions", label="Azure Functions", type="function", technology="Azure Functions")],
    "aws": [dict(id="eks", label="Amazon EKS", type="x_compute", technology="Amazon EKS"), dict(id="ecs", label="Amazon ECS on Fargate", type="x_compute", technology="Amazon ECS"),
            dict(id="lambda", label="AWS Lambda", type="x_compute", technology="AWS Lambda")],
    "gcp": [dict(id="gke", label="Google Kubernetes Engine", type="x_compute", technology="GKE"), dict(id="cloud_run", label="Cloud Run", type="x_compute", technology="Cloud Run"),
            dict(id="cloud_functions", label="Cloud Functions", type="x_compute", technology="Cloud Functions")],
    "hybrid": [dict(id="k8s_onprem", label="Kubernetes on-premises", type="x_compute", technology="Kubernetes 1.27"), dict(id="vm_onprem", label="Virtual machines on-premises", type="x_compute", technology="Windows Server 2019")],
}
EDGE_SERVICE = {"azure": ("api_management", "Azure API Management"), "aws": ("x_edge", "Amazon API Gateway"), "gcp": ("x_edge", "Apigee"), "hybrid": ("x_edge", "Self-managed API gateway")}
SEARCH_SERVICE = {"azure": ("ai_search", "Azure AI Search"), "aws": ("x_search", "Amazon OpenSearch Service"), "gcp": ("x_search", "Vertex AI Search"), "hybrid": ("x_search", "Elasticsearch 7")}
MESSAGING = [dict(id="kafka", label="Apache Kafka (Confluent)", azure=("kafka", "Apache Kafka"), alt=dict(aws="Amazon MSK", gcp="Confluent Cloud on GCP", hybrid="Apache Kafka")),
             dict(id="eventhubs", label="Azure Event Hubs (Kafka endpoint)", azure=("kafka", "Azure Event Hubs"), alt=dict(aws="Amazon Kinesis", gcp="Google Pub/Sub", hybrid="IBM MQ 9.1"))]
SECRETS_SERVICE = {"azure": ("key_vault", "Azure Key Vault"), "aws": ("x_secrets", "AWS Secrets Manager"), "gcp": ("x_secrets", "Google Secret Manager"), "hybrid": ("x_secrets", "HashiCorp Vault")}

LLMS = [
    dict(id="azure_openai", label="Azure OpenAI", type="azure_openai", technology="Azure OpenAI", note="Approved (STD-TECH-001). Must be reached privately (STD-SEC-014)."),
    dict(id="public_api", label="Public LLM API (OpenAI, Anthropic and similar)", type="llm_api_external", technology="Public LLM API", note="Prohibited for enterprise data (STD-AI-004)."),
    dict(id="bedrock", label="Amazon Bedrock", type="x_llm", technology="Amazon Bedrock", note="Not assessed by the Azure-specific standards."),
    dict(id="vertex", label="Google Vertex AI", type="x_llm", technology="Vertex AI", note="Not assessed by the Azure-specific standards."),
    dict(id="self_hosted", label="Self-hosted open model", type="x_llm", technology="Self-hosted open model", note="Not assessed by the Azure-specific standards."),
    dict(id="none", label="No LLM", type=None, technology=None, note="Removes LLM components from the architecture."),
]

# engine type on Azure, technology per cloud
DATABASES = [
    dict(id="postgres", label="PostgreSQL 15", azure=("postgres", "PostgreSQL 15"), alt=dict(aws="Amazon RDS for PostgreSQL", gcp="Cloud SQL for PostgreSQL", hybrid="PostgreSQL 15"), generic="x_database"),
    dict(id="cosmos_db", label="Cosmos DB", azure=("cosmos_db", "Cosmos DB"), alt=dict(aws="Amazon DynamoDB", gcp="Firestore", hybrid="MongoDB 4.4"), generic="x_database"),
    dict(id="sql_server_2019", label="SQL Server 2019", azure=("sql_database", "SQL Server 2019"), alt=dict(aws="SQL Server 2019", gcp="SQL Server 2019", hybrid="SQL Server 2019"), generic="x_database"),
    dict(id="oracle_19c", label="Oracle 19c", azure=("sql_database", "Oracle 19c"), alt=dict(aws="Oracle 19c", gcp="Oracle 19c", hybrid="Oracle 19c"), generic="x_database"),
    dict(id="oracle_12c", label="Oracle 12c", azure=("sql_database", "Oracle 12c"), alt=dict(aws="Oracle 12c", gcp="Oracle 12c", hybrid="Oracle 12c"), generic="x_database"),
    dict(id="data_lake", label="Data lake (ADLS Gen2 and equivalents)", azure=("data_lake", "ADLS Gen2"), alt=dict(aws="Amazon S3", gcp="Cloud Storage", hybrid="HDFS"), generic="x_object_store"),
    dict(id="redis", label="Redis 6 (cache)", azure=("x_cache", "Redis 6"), alt=dict(aws="Redis 6", gcp="Redis 6", hybrid="Redis 6"), generic="x_cache"),
]

BACKENDS = [
    dict(id="python", label="Python 3.11 (FastAPI)", technology="Python 3.11", framework="FastAPI"),
    dict(id="java17", label="Java 17 (Spring Boot 3)", technology="Java 17", framework="Spring Boot 3"),
    dict(id="dotnet8", label="C# on .NET 8", technology=".NET 8", framework="ASP.NET Core"),
    dict(id="node20", label="Node.js 20", technology="Node.js 20", framework="Express"),
    dict(id="node18", label="Node.js 18", technology="Node.js 18", framework="Express"),
    dict(id="java8", label="Java 8", technology="Java 8", framework="Spring Boot 2.7"),
]
IAC = [dict(id="terraform", label="Terraform"), dict(id="bicep", label="Bicep"), dict(id="none", label="Not decided")]
REGIONS = [dict(id=r, label=lbl) for r, lbl in (("westeurope", "West Europe"), ("northeurope", "North Europe"), ("uksouth", "UK South"), ("eastus2", "East US 2"), ("centralindia", "Central India"), ("southeastasia", "Southeast Asia"), ("brazilsouth", "Brazil South"))]
TIERS = [dict(id="tier1", label="Tier 1: critical"), dict(id="tier2", label="Tier 2: important"), dict(id="tier3", label="Tier 3: standard")]
CLASSIFICATIONS = [dict(id=c, label=c.title()) for c in ("public", "internal", "confidential", "restricted")]
EXPOSURE = [dict(id="internal", label="Internal users only"), dict(id="internet", label="Internet-facing (customers or partners)")]

# security and operations controls. `attrs` says which property each control sets, on which component types, so a control is never just a label.
POSTURE: list[dict] = [
    dict(id="private_endpoints", label="Private endpoints only", description="Disable public network access on PaaS services and reach them through private endpoints.", standards=["STD-SEC-014"]),
    dict(id="managed_identity", label="Managed identity, no keys or passwords", description="Services authenticate with managed identities.", standards=["STD-SEC-004", "STD-SEC-007"]),
    dict(id="key_vault_secrets", label="Secrets in Key Vault", description="Application secrets are held in Key Vault. Adds a Key Vault if the architecture has none.", standards=["STD-SEC-003"]),
    dict(id="tls12", label="TLS 1.2 or higher", description="Enforce a TLS 1.2 minimum on every endpoint.", standards=["STD-SEC-002"]),
    dict(id="diagnostics", label="Security logging to the SIEM", description="Diagnostic logs are sent to the enterprise SIEM.", standards=["STD-SEC-006"]),
    dict(id="waf", label="WAF on internet-facing endpoints", description="A web application firewall in front of anything reachable from the internet.", standards=["STD-SEC-005"]),
    dict(id="content_filter", label="LLM content filtering", description="Content filtering on every LLM component.", standards=["STD-AI-002"]),
    dict(id="human_in_loop", label="Human in the loop for decisions", description="A person approves AI-driven outcomes that affect customers.", standards=["STD-AI-003"]),
    dict(id="audit_logging", label="Audit prompts and responses", description="Prompts and responses are recorded for audit.", standards=["STD-AI-005"]),
    dict(id="high_availability", label="Zone redundancy and at least two instances", description="Multi-zone deployment with two or more instances.", standards=["STD-RES-001", "STD-RES-004"]),
    dict(id="backups", label="Backups configured", description="Backups on every data store.", standards=["STD-RES-002"]),
    dict(id="mandatory_tags", label="Mandatory resource tags", description="Owner, cost centre and data classification tags.", standards=["STD-CLD-003"]),
    dict(id="api_governance", label="APIs behind the gateway, versioned, contract-first", description="Every API is published through the gateway, versioned and described by an OpenAPI contract.", standards=["STD-INT-001", "STD-INT-002", "STD-INT-004"]),
    dict(id="pii_masking", label="Mask personal data outside production", description="PII masking on data stores that hold personal data.", standards=["STD-SEC-009"]),
    dict(id="customer_managed_keys", label="Customer-managed keys", description="Customer-managed encryption keys on data stores holding restricted data.", standards=["STD-SEC-012"]),
]
POSTURE_IDS = [p["id"] for p in POSTURE]
TIER_NFR_DEFAULTS = {"tier1": dict(availability="99.95", rto_hours=1, rpo_minutes=5), "tier2": dict(availability="99.9", rto_hours=4, rpo_minutes=15), "tier3": dict(availability="99.5", rto_hours=24, rpo_minutes=60)}

# What Azure itself does by default. Nothing else is assumed.
AZURE_DEFAULTS = {
    "azure_openai": dict(public_network_access=True), "ai_search": dict(public_network_access=True), "key_vault": dict(public_network_access=True, tls_min="1.2"),
    "storage_account": dict(public_network_access=True, tls_min="1.2", encryption_at_rest=True), "data_lake": dict(public_network_access=True, encryption_at_rest=True),
    "sql_database": dict(public_network_access=True, encryption_at_rest=True), "postgres": dict(public_network_access=True, encryption_at_rest=True), "cosmos_db": dict(public_network_access=True, encryption_at_rest=True),
}
PAAS = set(AZURE_DEFAULTS)
DATA_TYPES = {"storage_account", "sql_database", "postgres", "cosmos_db", "data_lake"}
HOSTING_TYPES = {"aks_cluster", "app_service", "function"}


@lru_cache
def covered_types() -> frozenset[str]:
    """Component types at least one standard applies to."""
    return frozenset(t for s in get_store().standards for t in (s.get("applies_to") or [])) | {"azure_openai", "llm_api_external"}


NOT_ASSESSED_ROLES = {"actor", "external"}


def tech_notice(technology: str | None) -> dict | None:
    """What the standards library and the technology catalogue say about a technology: status, standard, lifecycle, end of support."""
    if not technology:
        return None
    s = get_store()
    std = next((x for x in s.standards if x["kind"] == "approved_technology" and x["technology"].lower() == technology.lower()), None)
    t = s.technologies.get(technology)
    if not std and not t:
        return None
    users = sum(1 for a in s.apps if technology in a["tech"])
    return dict(technology=technology, standard_id=std["id"] if std else None, status=std["status"] if std else None, lifecycle=t["lifecycle"] if t else None, support_end=t.get("support_end") if t else None, estate_apps=users)


# ------------------------------------------------------------------ blueprint -> architecture
@lru_cache
def blueprint_graph(pattern_id: str) -> dict:
    bp = BLUEPRINTS[pattern_id]
    g = parse_mermaid(bp["diagram"])
    nodes = []
    for n in g["nodes"]:
        ov = OVERRIDES.get((pattern_id, n["id"]), {})
        base_role = classify(n, pattern_id)
        est = estate_match(n["label"])
        # a name match only counts when the kinds agree: a database name for a data node, an application name for a service-like node
        if est and not ((est["estate_kind"] == "database" and base_role in ("database", "external")) or (est["estate_kind"] == "application" and base_role in ("compute", "external", "api"))):
            est = None
        role = "external" if est else base_role
        node = dict(id=n["id"], label=n["label"], name=ov.get("name") or (est["estate_name"] if est else clean_name(n["label"], role)), role=role, shape=n["shape"], group=n["group"], declared=declared_attrs(n["label"]))
        if est:
            node.update(est)
        nodes.append(node)
    return dict(direction=g["direction"], nodes=nodes, edges=g["edges"])


def blueprint_roles(pattern_id: str) -> list[str]:
    return sorted({n["role"] for n in blueprint_graph(pattern_id)["nodes"]})


def blueprint_defaults(pattern_id: str) -> dict:
    """Choices that reproduce the blueprint as authored: what its own component table names."""
    bp = BLUEPRINTS[pattern_id]
    techs = " ".join(c["technology"] for c in bp["components"]).lower()
    roles = set(blueprint_roles(pattern_id))
    d: dict = dict(cloud="azure", deployment="aks" if "aks" in techs or "kubernetes" in techs else "app_service")
    if "ai_llm" in roles:
        d["llm"] = "azure_openai"
    if "database" in roles:
        picks = []
        for key, rx in (("postgres", r"postgres"), ("cosmos_db", r"cosmos|elasticsearch"), ("data_lake", r"adls|delta|lake"), ("sql_server_2019", r"sql server")):
            if re.search(rx, techs):
                picks.append(key)
        d["databases"] = picks or ["postgres"]
    d["backend"] = "java17" if re.search(r"java|spring", techs) and "python" not in techs else "node20" if "node.js" in techs and "python" not in techs else "python"
    if "messaging" in roles:
        d["messaging"] = "kafka"
    return d


def default_selections(pattern_id: str | None = None) -> dict:
    base = dict(cloud="azure", region="westeurope", deployment="aks", llm="azure_openai", databases=["postgres"], backend="python", messaging="kafka", iac="terraform", exposure="internal",
                classification=None, posture=[], instances=None, retention_days=None)
    if pattern_id:
        base.update({k: v for k, v in blueprint_defaults(pattern_id).items()})
    return base


def catalog() -> dict:
    s = get_store()
    cover = covered_types()
    pats = {p["id"]: p for p in s.patterns}
    bps = []
    for pid, bp in BLUEPRINTS.items():
        g = blueprint_graph(pid)
        meta = pats[pid]
        bps.append(dict(id=pid, name=meta["name"], category=meta["category"], summary=meta["summary"], title=bp["title"], status=meta["status"], adoption_count=meta["adoption_count"], tags=meta["tags"],
                        roles=blueprint_roles(pid), nodes=len(g["nodes"]), edges=len(g["edges"]), defaults=default_selections(pid), standards=bp["standards"]))
    return dict(
        blueprints=bps, clouds=CLOUDS, deployments=DEPLOYMENTS, llms=[dict(l, notice=tech_notice(l["technology"])) for l in LLMS],
        databases=[dict(id=d["id"], label=d["label"], notice=tech_notice(d["azure"][1])) for d in DATABASES],
        backends=[dict(b, notice=tech_notice(b["technology"])) for b in BACKENDS], messaging=[dict(id=m["id"], label=m["label"]) for m in MESSAGING],
        iac=IAC, regions=REGIONS, approved_regions=next(x["check"]["value"] for x in s.standards if x["id"] == "STD-CLD-001"), tiers=TIERS, classifications=CLASSIFICATIONS, exposure=EXPOSURE, posture=POSTURE,
        palette=PALETTE, roles=ROLE_LABEL, covered_types=sorted(cover),
        coverage_note="The standards library describes Azure resource types. Components on other clouds, and generic services, are shown in the architecture but cannot be assessed by it.",
    )


# components a person can add in the editor
PALETTE = [
    dict(kind="service", role="compute", label="Service", description="Application service on the chosen deployment option"),
    dict(kind="api", role="api", label="API", description="An API published through the gateway"),
    dict(kind="gateway", role="edge", label="API gateway", description="Gateway and edge"),
    dict(kind="llm", role="ai_llm", label="LLM", description="Language model"),
    dict(kind="search", role="ai_search", label="Search index", description="Retrieval and vector search"),
    dict(kind="agent", role="ai_agent", label="AI agent", description="Planner and executor"),
    dict(kind="database", role="database", label="Data store", description="Database or lake"),
    dict(kind="messaging", role="messaging", label="Event stream", description="Kafka topic or Event Hub"),
    dict(kind="secrets", role="security", label="Key vault", description="Secrets and keys"),
    dict(kind="actor", role="actor", label="User or channel", description="People and channels"),
    dict(kind="external", role="external", label="Existing system", description="A system outside this design"),
]
