"""Deterministic seed generator for the "Northwind Assurance" estate.

Run:  python -m scripts.generate_seed        (from backend/)
Seed is fixed at 42 so every run produces byte-identical JSON.
The generator ends with self-checks for the story facts the rest of the platform relies on.
"""

from __future__ import annotations

import json
import networkx as nx
import random
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from faker import Faker

try:  # allow both `python -m scripts.generate_seed` and direct execution
    from scripts import seed_defs as D
    from scripts import seed_governance as G
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import seed_defs as D  # type: ignore
    import seed_governance as G  # type: ignore

SEED = 42
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "seed"
REF_DATE = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)

rng = random.Random(SEED)
Faker.seed(SEED)
fake = Faker()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def short(s: str) -> str:
    for w in (" Service", " Platform", " Engine", " Manager", " System", " Core"):
        s = s.replace(w, "")
    return s.strip()


# ============================================================ owners / caps / tech
def build_owners():
    owners = []
    for i, (name, team, domain, role) in enumerate(D.OWNERS, 1):
        owners.append(dict(id=f"OWN-{i:03d}", name=name, team=team, domain=domain, role=role,
                           email=f"{name.lower().replace(' ', '.').replace(chr(39), '')}@northwind-assurance.example"))
    return owners


def build_capabilities():
    caps = []
    for cid, name, parent, level in D.CAPABILITIES:
        caps.append(dict(id=cid, name=name, parent=parent, level=level))
    return caps


def build_technologies():
    extra = {"DB2 for i": ("database", "extended", "2028-04"), "SAP HANA": ("database", "supported", "2030-12"),
             "ADLS Gen2": ("storage", "supported", "n/a"), "Amazon S3": ("storage", "supported", "n/a")}
    tech = dict(D.TECHNOLOGIES, **extra)
    return [dict(name=n, category=c, lifecycle=l, support_end=e) for n, (c, l, e) in tech.items()], tech


# ================================================================== applications
KIND_DEFAULTS = {
    "microservice": dict(loc=(5, 60), cov=(62, 90), age=(1, 4)),
    "custom": dict(loc=(40, 400), cov=(35, 80), age=(3, 9)),
    "package": dict(loc=(60, 600), cov=(15, 50), age=(6, 12)),
    "legacy": dict(loc=(400, 2500), cov=(3, 28), age=(15, 30)),
    "platform": dict(loc=(10, 90), cov=(55, 85), age=(3, 7)),
    "saas": dict(loc=(0, 0), cov=(80, 80), age=(3, 8)),
}

HOST_PHRASE = {}


def build_apps(owners, tech_lc):
    by_name = {o["name"]: o for o in owners}
    apps, by_key = [], {}
    for i, d in enumerate(D.APPS, 1):
        kd = KIND_DEFAULTS[d["kind"]]
        crit_v, high_v = d.get("vulns", (0, 0))
        if not d.get("vulns"):
            if d["kind"] == "legacy" or d["lifecycle"] == "eol":
                crit_v, high_v = rng.randint(1, 3), rng.randint(3, 10)
            elif d["lifecycle"] == "extended":
                crit_v, high_v = rng.randint(0, 2), rng.randint(2, 8)
            else:
                crit_v, high_v = (1 if rng.random() < 0.12 else 0), rng.randint(0, 4)
        peak, cap = d.get("peak", (rng.randint(20, 400), 0))
        if not cap:
            cap = int(peak * rng.uniform(1.8, 3.6))
        owner = by_name[d["owner"]]
        caps_names = [c[1] for c in D.CAPABILITIES if c[0] in d["caps"]]
        a = dict(
            id=f"APP-{i:03d}", key=d["key"], name=d["name"], domain=d["domain"], kind=d["kind"], tech=list(d["tech"]),
            lifecycle=d["lifecycle"], criticality=d["criticality"], hosting=d["host"], capabilities=list(d["caps"]),
            owner_id=owner["id"], team=owner["team"], vendor=d.get("vendor", "In-house"),
            version=f"{rng.randint(1, 9)}.{rng.randint(0, 9)}.{rng.randint(0, 20)}", users=d["users"],
            annual_cost_k=d["cost"], loc_k=rng.randint(*kd["loc"]), test_coverage=rng.randint(*kd["cov"]),
            age_years=d.get("age", rng.randint(*kd["age"])), vulns_critical=crit_v, vulns_high=high_v,
            single_instance=bool(d.get("single", False)), dr_tier=d.get("dr", "warm"), peak_tps=peak, capacity_tps=cap,
            internet_facing=bool(d.get("internet", False)), role=d.get("role"), db_key=d.get("db"),
            description=f"{d['name']} supports {' and '.join(caps_names[:2]).lower()} within the {d['domain']} domain.",
            repo=f"northwind/{slug(d['name'])}" if d["kind"] not in ("saas",) else None,
            doc_coverage=rng.randint(25, 90),
        )
        apps.append(a)
        by_key[a["key"]] = a
    return apps, by_key


# ================================================================== databases
DB_SPECS = {
    "ORA12": ("Oracle 12c", "Policy Master DB", "relational", "on-prem", "restricted", "PAC", 4200),
    "DB2": ("DB2 z/OS", "Claims Mainframe DB2", "relational", "mainframe", "restricted", "CMF", 6800),
    "SNOW_FRD": ("Snowflake", "Fraud Feature Schema", "warehouse", "saas", "confidential", "FSE", 420),
    "MSSQL14": ("SQL Server 2014", "Claims Document Vault DB", "relational", "on-prem", "confidential", "CDV", 3100),
    "MSSQL14_SUB": ("SQL Server 2014", "Subrogation DB", "relational", "on-prem", "confidential", "SUBRO", 180),
    "COSMOS_CCOP": ("Cosmos DB", "Claims Copilot Session Store", "nosql", "azure", "confidential", "CCOP", 90),
    "ES": ("Elasticsearch 7", "Policy Search Index", "search", "azure", "internal", "PSS", 260),
    "AS400": ("DB2 for i", "Legacy Life Policy Files", "relational", "on-prem", "restricted", "LLP", 1900),
    "ORA19": ("Oracle 19c", "Rating Engine DB", "relational", "on-prem", "confidential", "RTE", 780),
    "MSSQL19": ("SQL Server 2019", "Reinsurance & Cat DB", "relational", "on-prem", "confidential", "REIP", 640),
    "HANA": ("SAP HANA", "S/4HANA Finance DB", "relational", "on-prem", "restricted", "SAP", 5200),
    "ORA19_ECC": ("Oracle 19c", "SAP ECC Database", "relational", "on-prem", "restricted", "ECC", 7400),
    "MSSQL19_DCB": ("SQL Server 2019", "Duck Creek Billing DB", "relational", "on-prem", "restricted", "DCB", 2300),
    "MSSQL19_GLR": ("SQL Server 2019", "GL Reconciler DB", "relational", "azure", "confidential", "GLR", 140),
    "MSSQL14_TRW": ("SQL Server 2014", "Treasury Workstation DB", "relational", "on-prem", "confidential", "TRW", 90),
    "ORA19_CSS": ("Oracle 19c", "Commission Statements DB", "relational", "on-prem", "internal", "CSS", 210),
    "MSSQL14_CIS": ("SQL Server 2014", "Customer Hub DB", "relational", "on-prem", "restricted", "CIS", 1700),
    "COSMOS_CNH": ("Cosmos DB", "Notification State Store", "nosql", "azure", "internal", "CNH", 75),
    "ADLS": ("ADLS Gen2", "Lakehouse Raw Zone", "object", "azure", "confidential", "DBX", 96000),
    "TERA": ("Teradata 15", "Enterprise DW", "warehouse", "on-prem", "confidential", "EDW", 88000),
    "REDIS": ("Redis 6", "Feature Cache", "cache", "azure", "internal", "FST", 12),
    "MSSQL14_MFT": ("SQL Server 2014", "MFT Transfer Registry", "relational", "on-prem", "internal", "MFT", 40),
    "MSSQL19_PAY": ("SQL Server 2019", "Payroll Staging DB", "relational", "on-prem", "restricted", "PAYI", 60),
    "MSSQL14_INTRA": ("SQL Server 2014", "Intranet Content DB", "relational", "on-prem", "internal", "INTRA", 320),
}

EXTRA_DBS = [
    ("SNOW_CLM", "Snowflake", "Claims Mart (Snowflake)", "warehouse", "saas", "confidential", "SNOW", 1900),
    ("SNOW_POL", "Snowflake", "Policy Mart (Snowflake)", "warehouse", "saas", "confidential", "SNOW", 2400),
    ("SNOW_C360", "Snowflake", "Customer 360 (Snowflake)", "warehouse", "saas", "restricted", "SNOW", 3100),
    ("ADLS_SILVER", "ADLS Gen2", "Lakehouse Silver Zone", "object", "azure", "confidential", "DBX", 54000),
    ("ADLS_GOLD", "ADLS Gen2", "Lakehouse Gold Zone", "object", "azure", "confidential", "DBX", 21000),
    ("S3_ARCH", "Amazon S3", "Claims Archive Bucket (S3)", "object", "aws", "restricted", "CDV", 41000),
    ("REDIS_QUOTE", "Redis 6", "Quote Cache", "cache", "azure", "internal", "PQP", 8),
    ("COSMOS_C360", "Cosmos DB", "Customer 360 Profile Store", "nosql", "azure", "restricted", "C360", 160),
]


def build_databases(apps, by_key, tech_lc):
    dbs, by_dbkey = [], {}

    def add(key, engine, name, kind, hosting, cls, owner_key, size):
        owner = by_key[owner_key]
        d = dict(id=f"DB-{len(dbs) + 1:03d}", key=key, name=name, engine=engine, kind=kind, hosting=hosting,
                 owner_app=owner["id"], domain=owner["domain"], size_gb=size, classification=cls,
                 lifecycle=tech_lc.get(engine, ("", "supported"))[1], criticality=owner["criticality"])
        dbs.append(d)
        by_dbkey[key] = d
        return d

    for key, spec in DB_SPECS.items():
        add(key, *spec[:5], spec[5], spec[6])
    for a in apps:  # generic per-app PostgreSQL
        if a["db_key"] == "PG":
            engine = "PostgreSQL 14" if "PostgreSQL 14" in a["tech"] else "PostgreSQL 15"
            key = f"PG_{a['key']}"
            add(key, engine, f"{short(a['name'])} DB", "relational", "azure", "confidential" if a["criticality"] in ("critical", "high") else "internal", a["key"], rng.randint(20, 900))
            a["db_key"] = key
    for key, engine, name, kind, hosting, cls, owner_key, size in EXTRA_DBS:
        add(key, engine, name, kind, hosting, cls, owner_key, size)
    return dbs, by_dbkey


# ====================================================================== APIs
VOCAB = {
    "Claims": ["Claim", "Coverage", "Adjuster", "Loss Event", "Reserve", "Payment", "Subrogation", "Claim Document", "Fraud Signal", "Settlement"],
    "Policy Admin": ["Policy", "Endorsement", "Quote", "Product", "Coverage Option", "Renewal", "Policy Document", "Insured Party"],
    "Underwriting": ["Risk", "Rate", "Referral", "Exposure", "Treaty", "Peril"],
    "Billing & Finance": ["Invoice", "Ledger Entry", "Payment", "Tax", "Reconciliation", "Commission", "Statement"],
    "Customer & Distribution": ["Contact", "Preference", "Consent", "Agent", "Broker", "Party", "Notification", "Campaign"],
    "Data & Analytics": ["Dataset", "Feature", "Model", "Metric", "Lineage", "Prompt"],
    "Integration & Platform": ["Event", "Subscription", "Identity", "Token", "Secret", "Ticket", "Alert"],
    "Corporate Services": ["Employee", "Payroll Run", "Travel Request", "Legal Matter"],
}
KIND_API_COUNT = {"microservice": 4, "custom": 3, "platform": 3, "package": 3, "saas": 1, "legacy": 1}


def build_apis(apps, by_key, owners):
    apis, used = [], set()

    def add(name, app, version="v1", protocol="REST", lifecycle="active", special=None):
        a = dict(id=f"API-{len(apis) + 1:04d}", name=name, version=version, protocol=protocol, lifecycle=lifecycle,
                 exposed_by=app["id"], owner_id=app["owner_id"], domain=app["domain"], consumers=[],
                 gateway=rng.random() < 0.82, auth=rng.choice(["oauth2", "oauth2", "mtls", "api_key"]),
                 sla_tier=app["criticality"], requests_per_day=int(10 ** rng.uniform(3.2, 6.6)),
                 contract=rng.choice(["openapi", "openapi", "openapi", "none"]) if protocol == "REST" else ("wsdl" if protocol == "SOAP" else "graphql-sdl"),
                 special=special)
        apis.append(a)
        used.add(name)
        return a

    # Story APIs first so ids are memorable
    add("Customer API", by_key["CIS"], "v1", "REST", "deprecated", special="customer_v1")
    add("Customer API", by_key["MDM"], "v2", "REST", "active", special="customer_v2")
    apis[1]["gateway"], apis[1]["contract"], apis[1]["auth"] = True, "openapi", "oauth2"
    apis[0]["gateway"], apis[0]["contract"] = False, "none"

    candidates = []
    for a in apps:
        n = KIND_API_COUNT[a["kind"]]
        candidates += [a] * n
    rng.shuffle(candidates)
    attempts = 0
    while len(apis) < 180 and attempts < 5000:
        attempts += 1
        app = candidates[attempts % len(candidates)] if attempts < len(candidates) else rng.choice(apps)
        if app["kind"] == "saas" and rng.random() < 0.5:
            continue
        res = rng.choice(VOCAB[app["domain"]])
        name = f"{short(app['name'])} {res} API"
        if name in used:
            ver = f"v{rng.randint(2, 3)}"
            if (name, ver) in used:
                continue
            used.add((name, ver))
            version = ver
        else:
            version = "v1"
        protocol = "SOAP" if app["kind"] in ("legacy", "package") and rng.random() < 0.7 else ("GraphQL" if rng.random() < 0.07 else "REST")
        lifecycle = rng.choices(["active", "deprecated", "beta", "retired"], weights=[78, 12, 8, 2])[0]
        add(name, app, version, protocol, lifecycle)
        used.add(name)

    # consumers
    by_id = {a["id"]: a for a in apps}
    for api in apis:
        provider = by_id[api["exposed_by"]]
        if api.get("special") == "customer_v2":
            api["consumers"] = [by_key[k]["id"] for k in D.CUSTOMER_API_V2_CONSUMERS]
            continue
        if api.get("special") == "customer_v1":
            api["consumers"] = [by_key[k]["id"] for k in D.CUSTOMER_API_V1_CONSUMERS]
            continue
        k = rng.choice([1, 1, 2, 2, 3, 3, 4, 5, 6, 7])
        pool_same = [a for a in apps if a["domain"] == provider["domain"] and a["id"] != provider["id"]]
        pool_all = [a for a in apps if a["id"] != provider["id"] and a["kind"] != "platform"]
        chosen = set()
        for _ in range(k):
            pool = pool_same if (pool_same and rng.random() < 0.62) else pool_all
            chosen.add(rng.choice(pool)["id"])
        if api["lifecycle"] == "retired":
            chosen = set(sorted(chosen)[:1])
        api["consumers"] = sorted(chosen)
    return apis


# ============================================================== integrations
INT_PAYLOAD = {
    "Claims": ["Claim updates", "Loss notifications", "Reserve changes", "Payment instructions", "Fraud scores"],
    "Policy Admin": ["Policy events", "Endorsement requests", "Renewal notices", "Quote data"],
    "Underwriting": ["Risk scores", "Rate tables", "Referral decisions"],
    "Billing & Finance": ["GL postings", "Premium invoices", "Payment confirmations", "Tax data"],
    "Customer & Distribution": ["Customer profile sync", "Agent hierarchy", "Consent changes", "Commission data"],
    "Data & Analytics": ["Change data capture", "Reference data", "Feature snapshots"],
    "Integration & Platform": ["Service events", "Identity assertions", "Ticket updates"],
    "Corporate Services": ["Employee records", "Payroll files", "Travel bookings"],
}
PROTOCOL = {"api": "REST", "esb": "MQ/SOAP", "event": "Kafka", "file_batch": "SFTP", "point_to_point": "HTTP/TCP", "direct_db": "JDBC"}
FREQ = {"api": ["real-time"], "esb": ["real-time", "hourly"], "event": ["real-time"], "file_batch": ["nightly", "hourly", "weekly"],
        "point_to_point": ["real-time", "hourly", "nightly"], "direct_db": ["real-time", "nightly"]}


def build_integrations(apps, by_key, dbs, by_dbkey, apis):
    ints, seen = [], set()
    hubs = {by_key[k]["id"] for k in ("MULE", "KAFKA", "APIM", "IIB", "MFT")}
    by_id = {a["id"]: a for a in apps}

    flow = nx.DiGraph()  # direct app->app flows; random edges may not close a cycle (only the 2 explicit clusters do)

    def add(src, tgt, style, via=None, payload=None, api_id=None, skind="app", tkind="app", name=None, crit=None, check=True):
        key = (skind, src, tkind, tgt, style)
        if key in seen:
            return None
        direct_flow = skind == "app" and tkind == "app" and not via and style != "direct_db" and src not in hubs and tgt not in hubs
        if direct_flow:
            if check and src in flow and tgt in flow and nx.has_path(flow, tgt, src):
                return None
            flow.add_edge(src, tgt)
        seen.add(key)
        dom = by_id[src]["domain"] if skind == "app" else next(d for d in dbs if d["id"] == src)["domain"]
        i = dict(id="", name=name or "", source_kind=skind, source_id=src, target_kind=tkind, target_id=tgt, style=style,
                 protocol=PROTOCOL[style], via=via, frequency=rng.choice(FREQ[style]),
                 payload=payload or rng.choice(INT_PAYLOAD.get(dom, ["Reference data"])), api_id=api_id,
                 data_classification=rng.choice(["internal", "confidential", "confidential", "restricted"]),
                 criticality=crit or rng.choice(["medium", "medium", "high", "low", "critical"]), status="active")
        ints.append(i)
        return i

    K = lambda k: by_key[k]["id"]  # noqa: E731
    D_ = lambda k: by_dbkey[k]["id"]  # noqa: E731

    # --- story chain: SAP -> MuleSoft -> Salesforce -> Snowflake
    add(K("SAP"), K("MULE"), "api", payload="GL postings and customer billing data", name="SAP S/4HANA → MuleSoft Anypoint", crit="critical")
    add(K("MULE"), K("SFC"), "api", payload="Billing and account updates", name="MuleSoft Anypoint → Salesforce CRM", crit="critical")
    add(K("SFC"), K("SNOW"), "event", payload="Change data capture (Snowpipe)", name="Salesforce CRM → Snowflake Data Cloud", crit="high")
    # --- tightly coupled clusters (cycles)
    for a, b in (("PAC", "COLM"), ("COLM", "ACE"), ("ACE", "PAC"), ("GWCC", "CPH"), ("CPH", "CMF"), ("CMF", "GWCC")):
        add(K(a), K(b), "point_to_point", name=f"{by_key[a]['name']} → {by_key[b]['name']}", crit="high", check=False)

    # --- 17 direct DB integrations
    direct = []
    for k in D.ORACLE12_DIRECT:
        direct.append(("app", K(k), "db", D_("ORA12")))
    for ak, dk in (("PBI", "MSSQL14"), ("RRH", "ORA19_ECC"), ("COLM", "MSSQL19_DCB"), ("TRW", "ORA19_ECC"), ("INTRA", "MSSQL14_CIS"),
                   ("C360", "MSSQL14_CIS"), ("RSS", "ORA19"), ("SUBRO", "DB2"), ("CNH", "MSSQL14_CIS"), ("FSE", "DB2"), ("AGP", "ORA19_CSS")):
        direct.append(("app", K(ak), "db", D_(dk)))
    for sk, tk in (("ORA12", "MSSQL19_DCB"), ("MSSQL14_CIS", "ORA12"), ("ORA19_ECC", "TERA")):
        direct.append(("db", D_(sk), "db", D_(tk)))
    for sk, s, tk, t in direct:
        sname = by_id[s]["name"] if sk == "app" else next(d for d in dbs if d["id"] == s)["name"]
        tname = next(d for d in dbs if d["id"] == t)["name"]
        add(s, t, "direct_db", skind=sk, tkind=tk, name=f"{sname} → {tname}", payload="Direct table access" if sk == "app" else "Database link", crit="high")

    # --- API integrations derived from real consumption
    pairs = [(c, api) for api in apis for c in api["consumers"]]
    rng.shuffle(pairs)
    n_api = 0
    for c, api in pairs:
        if n_api >= 72:
            break
        if c in hubs or api["exposed_by"] in hubs:
            continue
        if add(c, api["exposed_by"], "api", api_id=api["id"], name=f"{by_id[c]['name']} → {by_id[api['exposed_by']]['name']}"):
            n_api += 1

    # --- other styles to reach ~220 total
    plan = [("esb", 40), ("event", 42), ("file_batch", 28), ("point_to_point", 21)]
    nonhub = [a for a in apps if a["id"] not in hubs]
    for style, n in plan:
        made, guard = 0, 0
        while made < n and guard < 4000:
            guard += 1
            s = rng.choice(nonhub)
            pool = [a for a in nonhub if a["id"] != s["id"] and (a["domain"] == s["domain"] if rng.random() < 0.55 else True)]
            t = rng.choice(pool)
            via = None
            if style == "esb":
                via = K("IIB") if (s["hosting"] in ("on-prem", "mainframe") and rng.random() < 0.55) else K("MULE")
            elif style == "event":
                if "Apache Kafka" not in s["tech"] and s["kind"] not in ("microservice", "custom"):
                    continue
                via = K("KAFKA")
            elif style == "file_batch":
                via = K("MFT") if rng.random() < 0.6 else None
            if add(s["id"], t["id"], style, via=via, name=f"{s['name']} → {t['name']}"):
                made += 1

    for n, i in enumerate(ints, 1):
        i["id"] = f"INT-{n:04d}"
        if not i["name"]:
            i["name"] = f"{i['source_id']} → {i['target_id']}"
    return ints


# ================================================================ cloud resources
APPROVED_CFG = {
    "azure_openai": dict(public_network_access=False, private_endpoint=True, local_auth_disabled=True, content_filter="strict", sku="S0", min_tls="1.2"),
    "storage_account": dict(public_network_access=False, https_only=True, min_tls="1.2", replication="GRS", blob_public_access=False, soft_delete_days=30),
    "key_vault": dict(public_network_access=False, soft_delete=True, purge_protection=True, rbac=True),
    "app_service": dict(https_only=True, min_tls="1.2", vnet_integration=True, always_on=True, sku="P1v3"),
    "function": dict(https_only=True, min_tls="1.2", vnet_integration=True, sku="EP1"),
    "aks_cluster": dict(k8s_version="1.29", private_cluster=True, rbac=True, network_policy="azure", sku_tier="Standard"),
    "postgres": dict(public_network_access=False, backup_retention_days=35, high_availability="ZoneRedundant", min_tls="1.2", sku="GP_Standard_D4s_v3"),
    "cosmos_db": dict(public_network_access=False, backup="continuous", multi_region_writes=False),
    "data_lake": dict(public_network_access=False, https_only=True, hns_enabled=True, replication="ZRS"),
    "private_endpoint": dict(approval="Approved", subnet="snet-private"),
    "virtual_network": dict(ddos=True, nsg_rule_ssh="deny", flow_logs=True),
    "api_management": dict(sku="Premium", vnet_mode="Internal", min_tls="1.2"),
    "s3_bucket": dict(block_public_access=True, encryption="aws:kms", versioning=True),
    "ec2_instance": dict(imdsv2=True, public_ip=False, instance_type="m5.large"),
}
MUTATIONS = {
    "azure_openai": [("public_network_access", True, "critical"), ("local_auth_disabled", False, "high"), ("content_filter", "off", "high")],
    "storage_account": [("public_network_access", True, "critical"), ("min_tls", "1.0", "high"), ("replication", "LRS", "medium"), ("blob_public_access", True, "critical")],
    "key_vault": [("purge_protection", False, "medium"), ("public_network_access", True, "high")],
    "app_service": [("min_tls", "1.0", "high"), ("https_only", False, "high"), ("sku", "B1", "low")],
    "function": [("min_tls", "1.0", "high"), ("vnet_integration", False, "medium")],
    "aks_cluster": [("k8s_version", "1.27", "medium"), ("private_cluster", False, "high")],
    "postgres": [("public_network_access", True, "critical"), ("backup_retention_days", 7, "medium"), ("high_availability", "Disabled", "high")],
    "cosmos_db": [("public_network_access", True, "high"), ("backup", "periodic", "low")],
    "data_lake": [("public_network_access", True, "high"), ("replication", "LRS", "medium")],
    "virtual_network": [("nsg_rule_ssh", "allow-any", "critical"), ("ddos", False, "medium")],
    "s3_bucket": [("block_public_access", False, "critical"), ("versioning", False, "low")],
}
NAMING = {"azure_openai": "oai", "storage_account": "st", "key_vault": "kv", "app_service": "app", "function": "func", "aks_cluster": "aks",
          "postgres": "psql", "cosmos_db": "cosmos", "data_lake": "adls", "private_endpoint": "pe", "virtual_network": "vnet", "api_management": "apim"}


def build_cloud(apps, by_key, dbs):
    res = []
    by_app = {a["id"]: a for a in apps}

    def add(rtype, name, provider, app, env, region="westeurope", tags_ok=True, cfg=None, group=None):
        cfg = dict(APPROVED_CFG.get(rtype, {}), **(cfg or {}))
        r = dict(id="", name=name, provider=provider, type=rtype, region=region, env=env, app_id=app["id"] if app else None,
                 domain=app["domain"] if app else "Integration & Platform", resource_group=group or f"rg-{slug((app or {'name': 'shared'})['name'])[:24]}-{env}",
                 subscription=f"nwa-{env}-{region[:2]}", approved=cfg, deployed=dict(cfg), managed_by="terraform",
                 tags=dict(owner=app["team"] if app else "Cloud Platform", cost_centre=f"CC-{rng.randint(1000, 9999)}", data_classification=(app or {}).get("criticality", "internal")) if tags_ok else dict(owner="unknown"),
                 created_at=(REF_DATE - timedelta(days=rng.randint(30, 1100))).isoformat(), resource_guid=str(fake.uuid4()))
        res.append(r)
        return r

    # Story resources first (stable low ids)
    ccop, aoai = by_key["CCOP"], by_key["AOAI"]
    add("azure_openai", "oai-claims-prod", "azure", ccop, "prod", group="rg-claims-ai-prod")
    add("storage_account", "stclaimscopilotprod", "azure", ccop, "prod", group="rg-claims-ai-prod")
    add("private_endpoint", "pe-oai-claims-prod", "azure", ccop, "prod", group="rg-claims-ai-prod")
    add("key_vault", "kv-claims-ai-prod", "azure", ccop, "prod", group="rg-claims-ai-prod")
    add("azure_openai", "oai-nwa-platform-prod", "azure", aoai, "prod", region="northeurope", group="rg-ai-platform-prod")

    # Hub networking and shared platform
    for region in ("westeurope", "northeurope"):
        add("virtual_network", f"vnet-hub-{region[:2]}-prod", "azure", None, "prod", region, group="rg-network-hub")
    for dom in D.DOMAINS:
        add("virtual_network", f"vnet-{slug(dom)[:14]}-prod", "azure", None, "prod", group="rg-network-spokes")
    add("aks_cluster", "aks-nwa-shared-prod", "azure", by_key["KAFKA"], "prod", group="rg-platform-prod")
    add("aks_cluster", "aks-mule-runtime-prod", "azure", by_key["MULE"], "prod", group="rg-integration-prod")
    add("api_management", "apim-nwa-prod", "azure", by_key["APIM"], "prod", group="rg-integration-prod")
    add("key_vault", "kv-nwa-platform-prod", "azure", by_key["SKM"], "prod", group="rg-platform-prod")

    # Per-application resources
    for a in apps:
        if a["hosting"] != "azure" or a["key"] in ("CCOP", "AOAI", "KAFKA", "MULE", "APIM", "SKM"):
            continue
        sl = slug(short(a["name"]))[:18]
        if a["kind"] == "platform":
            add("aks_cluster", f"aks-{sl}-prod", "azure", a, "prod")
        elif a["kind"] in ("microservice",) and rng.random() < 0.35:
            add("function", f"func-{sl}-prod", "azure", a, "prod")
        else:
            add("app_service", f"app-{sl}-prod", "azure", a, "prod")
        add("key_vault", f"kv-{sl}-prod"[:24], "azure", a, "prod")
        add("storage_account", f"st{sl.replace('-', '')}prod"[:24], "azure", a, "prod")
        add("private_endpoint", f"pe-{sl}-prod", "azure", a, "prod")
        dbrec = next((d for d in dbs if d["key"] == a["db_key"]), None)
        if dbrec and dbrec["engine"].startswith("PostgreSQL"):
            add("postgres", f"psql-{sl}-prod", "azure", a, "prod")
        elif dbrec and dbrec["engine"] == "Cosmos DB":
            add("cosmos_db", f"cosmos-{sl}-prod", "azure", a, "prod")
        elif dbrec and dbrec["engine"] == "ADLS Gen2":
            add("data_lake", f"adls{sl.replace('-', '')}prod"[:24], "azure", a, "prod")
    # lower environments
    for a in apps:
        if a["hosting"] == "azure" and a["kind"] in ("microservice", "custom") and rng.random() < 0.6:
            sl = slug(short(a["name"]))[:18]
            for env in ("dev", "test"):
                add("app_service", f"app-{sl}-{env}", "azure", a, env)
                if rng.random() < 0.5:
                    add("storage_account", f"st{sl.replace('-', '')}{env}"[:24], "azure", a, env)
    # AWS estate (analytics archive and sandbox)
    for nm, rt, ak in (("s3-nwa-claims-archive-prod", "s3_bucket", "CDV"), ("s3-nwa-datalake-landing", "s3_bucket", "DBX"), ("s3-nwa-modelling-exports", "s3_bucket", "CATM"),
                       ("ec2-nwa-analytics-sbx-01", "ec2_instance", "DBX"), ("ec2-nwa-analytics-sbx-02", "ec2_instance", "DBX")):
        add(rt, nm, "aws", by_key[ak], "prod" if "sbx" not in nm else "dev", region="eu-west-1", group="aws-nwa-analytics")

    # pad / trim to exactly 300 while keeping the story resources at the front
    names = {r["name"] for r in res}
    pad_i = 0
    while len(res) < 300:
        base = rng.choice([r for r in res[5:] if r["type"] in ("app_service", "storage_account", "key_vault", "postgres") and r["env"] == "prod"])
        pad_i += 1
        env = "uat" if pad_i % 2 else "dr"
        nm = f"{base['name'].rsplit('-', 1)[0]}-{env}"
        if nm in names:
            nm = f"{nm}{pad_i}"
        names.add(nm)
        add(base["type"], nm, base["provider"], by_app.get(base["app_id"]) if base["app_id"] else None, env, base["region"])
    removable = [r for r in res[5:] if r["env"] in ("dev", "test", "uat", "dr")]
    while len(res) > 300 and removable:
        res.remove(removable.pop())
    while len(res) > 300:
        res.pop()
    for i, r in enumerate(res, 1):
        r["id"] = f"CLD-{i:04d}"
    return res


def apply_drift(res):
    """Deployed config diverges from approved for exactly 25 resources (story resources first)."""
    picked = [res[0], res[1]]  # oai-claims-prod, stclaimscopilotprod
    pool = [r for r in res[5:] if r["type"] in MUTATIONS and r["env"] == "prod" and r["provider"] in ("azure", "aws")]
    rng.shuffle(pool)
    picked += pool[:23]
    statuses = ["open", "open", "open", "ticket_raised", "exception_granted", "open", "remediating"]
    for n, r in enumerate(picked):
        muts = MUTATIONS[r["type"]]
        if n < 2:
            m = muts[0]
        else:
            m = rng.choice(muts)
        r["deployed"][m[0]] = m[1]
        if r["type"] == "azure_openai" and m[0] == "public_network_access":
            r["deployed"]["private_endpoint"] = False
        r["drift_meta"] = dict(severity=m[2], detected_at=(REF_DATE - timedelta(hours=rng.randint(1, 24 * 40))).isoformat(),
                               status="open" if n < 2 else rng.choice(statuses), ticket=None, exception_expires=None)
        if r["drift_meta"]["status"] == "ticket_raised":
            r["drift_meta"]["ticket"] = f"INC{rng.randint(1000000, 1999999)}"
        if r["drift_meta"]["status"] == "exception_granted":
            r["drift_meta"]["exception_expires"] = (REF_DATE + timedelta(days=rng.randint(15, 90))).date().isoformat()
        if n < 2:
            r["drift_meta"]["detected_at"] = (REF_DATE - timedelta(minutes=22 + n * 40)).isoformat()
        if n in (3, 9, 14):  # a few resources drift on a second attribute too
            extra = [x for x in muts if x[0] != m[0]]
            if extra:
                r["deployed"][extra[0][0]] = extra[0][1]
    return res


# ================================================================== workflows
def build_workflows(apps, by_key, apis):
    wfs = []
    cust2 = next(a for a in apis if a.get("special") == "customer_v2")
    api_by_app = {}
    for a in apis:
        if not a.get("special"):
            api_by_app.setdefault(a["exposed_by"], []).append(a["id"])
    for i, (name, dom, keys, uses_c2) in enumerate(D.WORKFLOWS, 1):
        steps = []
        api_ids = []
        for k in keys:
            app = by_key[k]
            step = dict(app_id=app["id"], api_id=None)
            if uses_c2 and app["id"] in cust2["consumers"] and cust2["id"] not in api_ids:
                step["api_id"] = cust2["id"]
                api_ids.append(cust2["id"])
            elif api_by_app.get(app["id"]) and rng.random() < 0.6:
                step["api_id"] = rng.choice(api_by_app[app["id"]])
                api_ids.append(step["api_id"])
            steps.append(step)
        wfs.append(dict(id=f"WF-{i:03d}", name=name, domain=dom, steps=steps, apis=sorted(set(api_ids)),
                        apps=[s["app_id"] for s in steps], volume_per_day=int(10 ** rng.uniform(2.5, 5.4)),
                        sla_minutes=rng.choice([5, 15, 60, 240, 1440])))
    return wfs


# ================================================================== documents
PHR = {
    "stores_in": " stores its data in ", "reads_from": " reads from ", "calls": " calls ", "integrates": " integrates with ",
    "hosted_on": " is hosted on ", "system_of_record": " is the system of record for ",
}


def host_phrase(a):
    t = " ".join(a["tech"])
    if a["hosting"] == "mainframe":
        return "the z/OS mainframe"
    if a["hosting"] == "saas":
        return "the vendor-hosted SaaS tenant"
    if a["hosting"] == "azure":
        return "Azure AKS" if a["kind"] in ("platform", "microservice") else "Azure App Service"
    if "WebSphere" in t:
        return "on-premises WebSphere"
    if "Windows" in t:
        return "on-premises Windows Server"
    return "on-premises Linux servers"


def build_documents(apps, by_key, dbs, by_dbkey, apis, ints, owners):
    by_id = {a["id"]: a for a in apps}
    db_by_id = {d["id"]: d for d in dbs}
    api_by_id = {a["id"]: a for a in apis}
    docs = []
    HOSTS = {a["id"]: host_phrase(a) for a in apps}
    owner_by_domain = {}
    for o in owners:
        owner_by_domain.setdefault(o["domain"], []).append(o)

    def facts(app):
        f = []
        f.append(("hosted_on", app["name"], HOSTS[app["id"]]))
        db = next((d for d in dbs if d["key"] == app["db_key"]), None)
        if db and app["key"] != "PAC":  # Policy Admin -> Oracle link is deliberately undocumented
            f.append(("stores_in", app["name"], db["name"]))
        for i in ints:
            if i["source_id"] == app["id"] and i["source_kind"] == "app":
                if i["style"] == "direct_db":
                    f.append(("reads_from", app["name"], db_by_id[i["target_id"]]["name"]))
                elif i["target_kind"] == "app" and i["target_id"] in by_id:
                    f.append(("integrates", app["name"], by_id[i["target_id"]]["name"] + f" using {i['style'].replace('_', '-')}"))
        for api in apis:
            if app["id"] in api["consumers"] and not api.get("special"):
                f.append(("calls", app["name"], f"{api['name']} {api['version']}" if api["version"] != "v1" else api["name"]))
        return f

    def render(title, kind, scope, meta, extra_lines=None, prob=0.62):
        lines = [f"# {title}", "", f"Status: {meta['status']}. Last reviewed {meta['updated'][:10]}. Owner: {meta['owner']}.", "",
                 "## 1. Purpose", meta["purpose"], "", "## 2. Architecture overview"]
        for a in scope:
            lines.append(f"### {a['name']}")
            chosen = [f for f in facts(a) if rng.random() < prob or f[0] == "hosted_on"]
            sents = [f"{s}{PHR[r]}{o}." for r, s, o in chosen[:6]]
            lines.append(" ".join(sents) if sents else f"{a['name']} supports {', '.join(c[1] for c in D.CAPABILITIES if c[0] in a['capabilities'][:1])}.")
            lines.append("")
        for l in extra_lines or []:
            lines.append(l)
        lines += ["", "## 3. Open issues",
                  f"- Capacity planning for {rng.choice(scope)['name']} is not yet agreed.",
                  f"- Resilience testing of {rng.choice(scope)['name']} has not been repeated since the last release.",
                  "- Interface ownership between domains should be confirmed with the design authority."]
        return "\n".join(lines)

    def add_doc(title, dtype, source, domain, age_days, text, owner=None, tags=None, adr=None):
        n = len(docs) + 1
        upd = REF_DATE - timedelta(days=age_days)
        o = owner or rng.choice(owner_by_domain.get(domain, owners))
        docs.append(dict(id=f"DOC-{n:03d}", title=title, doc_type=dtype, source=source, domain=domain, author_id=o["id"],
                         created_at=(upd - timedelta(days=rng.randint(30, 400))).isoformat(), updated_at=upd.isoformat(),
                         path={"confluence": f"/wiki/spaces/ARCH/pages/{rng.randint(100000, 999999)}", "sharepoint": f"/sites/Architecture/Shared Documents/{slug(title)}.docx",
                               "git": f"northwind/architecture-docs/{slug(title)}.md"}[source],
                         text=text, tags=tags or [], adr=adr))

    # ---- deliberate contradictions & the story chain
    cip, gwcc, pac, sfc, mdm, cis = (by_key[k] for k in ("CIP", "GWCC", "PAC", "SFC", "MDM", "CIS"))
    mk = lambda st, upd, purpose, owner: dict(status=st, updated=(REF_DATE - timedelta(days=upd)).isoformat(), purpose=purpose, owner=owner)  # noqa: E731
    add_doc("Claims Intake Portal HLD v1.2", "HLD", "confluence", "Claims", 980,
            render("Claims Intake Portal HLD v1.2", "HLD", [cip], mk("Superseded", 980, "High-level design of the digital claim intake channel.", "Ananya Rao"), [f"{cip['name']} calls Customer API v1."], 0.5), tags=["claims", "intake"])
    add_doc("Claims Intake Portal LLD v2.0", "LLD", "confluence", "Claims", 64,
            render("Claims Intake Portal LLD v2.0", "LLD", [cip], mk("Approved", 64, "Low-level design after the Customer API v2 migration.", "Ananya Rao"), [f"{cip['name']} calls Customer API v2."], 0.5), tags=["claims", "intake"])
    add_doc("Guidewire ClaimCenter Target State HLD (Draft)", "HLD", "sharepoint", "Claims", 410,
            render("Guidewire ClaimCenter Target State HLD", "HLD", [gwcc], mk("Draft", 410, "Aspirational cloud target state for ClaimCenter.", "Rohan Kulkarni"), [], 0.4).replace(f"{gwcc['name']} is hosted on on-premises WebSphere.", f"{gwcc['name']} is hosted on Azure AKS."), tags=["claims", "target-state"])
    add_doc("ClaimCenter Operations Runbook", "Confluence", "confluence", "Claims", 45,
            render("ClaimCenter Operations Runbook", "Runbook", [gwcc], mk("Current", 45, "Operational procedures for ClaimCenter.", "Rohan Kulkarni"), [], 0.5), tags=["claims", "ops"])
    add_doc("Policy Admin Core DR Plan 2022", "LLD", "sharepoint", "Policy Admin", 1020,
            render("Policy Admin Core DR Plan 2022", "LLD", [pac], mk("Outdated", 1020, "Disaster recovery plan written before the platform upgrade.", "Sarah Whitfield"), [f"{pac['name']} stores its data in SQL Server 2014."], 0.3), tags=["policy", "dr"])
    add_doc("Policy Platform Target State 2024", "HLD", "confluence", "Policy Admin", 300,
            render("Policy Platform Target State 2024", "HLD", [pac], mk("Draft", 300, "Target-state proposal for the policy platform data tier.", "Marcus Chen"), [f"{pac['name']} stores its data in PostgreSQL 15."], 0.3), tags=["policy", "target-state"])
    add_doc("Customer Data Strategy 2023", "Confluence", "confluence", "Customer & Distribution", 700,
            render("Customer Data Strategy 2023", "Strategy", [sfc], mk("Outdated", 700, "Customer data strategy from the CRM consolidation programme.", "Aisha Khan"), [f"{sfc['name']} is the system of record for customer data."], 0.3), tags=["customer", "mdm"])
    add_doc("MDM Programme Charter 2024", "Confluence", "confluence", "Customer & Distribution", 210,
            render("MDM Programme Charter 2024", "Charter", [mdm], mk("Approved", 210, "Charter for the customer master programme.", "Elena Petrova"), [f"{mdm['name']} is the system of record for customer data."], 0.3), tags=["customer", "mdm"])
    add_doc("Northwind Customer Hub Overview", "SharePoint", "sharepoint", "Customer & Distribution", 1300,
            render("Northwind Customer Hub Overview", "Overview", [cis], mk("Outdated", 1300, "Legacy customer hub overview.", "Elena Petrova"), [f"{cis['name']} is the system of record for customer data."], 0.3), tags=["customer", "legacy"])
    sap, mule, snow = by_key["SAP"], by_key["MULE"], by_key["SNOW"]
    add_doc("Finance and Customer Integration HLD", "HLD", "confluence", "Integration & Platform", 52,
            render("Finance and Customer Integration HLD", "HLD", [sap, mule, sfc, snow], mk("Approved", 52, "Describes the SAP to Snowflake data flow through MuleSoft and Salesforce.", "Rahul Mehta"),
                   [f"{sap['name']} integrates with {mule['name']} using api.", f"{mule['name']} integrates with {sfc['name']} using api.", f"{sfc['name']} integrates with {snow['name']} using event."], 0.4), tags=["integration", "finance"])

    # ---- ADRs
    adrs = [
        ("ADR-0031", "Adopt Kafka as the enterprise event backbone", "Integration & Platform", "accepted", "Kafka Event Platform becomes the standard for cross-domain events."),
        ("ADR-0034", "Use Azure OpenAI for generative AI workloads", "Data & Analytics", "accepted", "Azure OpenAI behind the AI Gateway is the only approved LLM service."),
        ("ADR-0036", "Require private endpoints for PaaS services", "Integration & Platform", "accepted", "All PaaS holding enterprise data is reached via Private Endpoint (STD-SEC-014)."),
        ("ADR-0038", "Retire Oracle 12c by end of FY27", "Policy Admin", "accepted", "Policy Master DB migrates to PostgreSQL 15 and direct DB consumers move to APIs."),
        ("ADR-0040", "MuleSoft for system and process APIs", "Integration & Platform", "accepted", "MuleSoft Anypoint hosts system and process APIs; experience APIs live in Azure API Management."),
        ("ADR-0041", "Customer API v2 replaces v1", "Customer & Distribution", "accepted", "Customer API v1 is deprecated; consumers migrate to Customer API v2."),
        ("ADR-0043", "Strangler-fig facade for the claims mainframe", "Claims", "proposed", "A REST facade fronts Claims Mainframe Core and capabilities migrate incrementally."),
        ("ADR-0044", "Consolidate customer master onto Customer Master (MDM)", "Customer & Distribution", "proposed", "Customer Master (MDM) becomes the single system of record for customer data."),
        ("ADR-0045", "Terraform as the only IaC tool", "Integration & Platform", "accepted", "Terraform modules are the standard; Bicep allowed for Azure-native landing zone components."),
        ("ADR-0046", "Human approval for AI-assisted claim decisions", "Claims", "accepted", "AI may recommend but never finalise a claim decision (STD-AI-003)."),
        ("ADR-0047", "Snowflake for governed analytics", "Data & Analytics", "accepted", "Snowflake is the analytics serving layer; Databricks handles engineering and ML."),
        ("ADR-0048", "Decommission Windows Server 2012 estate", "Integration & Platform", "superseded", "Superseded by ADR-0049 sunset plan with firm dates."),
    ]
    for aid, title, dom, status, decision in adrs:
        scope = [by_key["MULE"], by_key["KAFKA"]] if "Kafka" in title or "MuleSoft" in title else rng.sample([a for a in apps if a["domain"] == dom] or apps, 2)
        text = "\n".join([f"# {aid}: {title}", "", f"Status: {status}", "", "## Context", f"The estate has grown organically and {scope[0]['name']} and {scope[1]['name']} illustrate the inconsistency this decision addresses.", "",
                          "## Decision", f"Decision: {decision}", "", "## Consequences", "- Teams must plan migration work in their roadmaps.", "- Exceptions require design authority approval."])
        add_doc(f"{aid}: {title}", "ADR", "git", dom, rng.randint(40, 520), text, tags=["adr"], adr=dict(number=aid, status=status, decision=decision, date=(REF_DATE - timedelta(days=rng.randint(40, 520))).date().isoformat()))

    # ---- fill remaining docs (HLD/LLD/Confluence/SharePoint/diagram/README)
    plan = [("HLD", "confluence", 6), ("LLD", "confluence", 8), ("Confluence", "confluence", 8), ("SharePoint", "sharepoint", 6), ("diagram", "sharepoint", 5), ("PDF", "sharepoint", 3), ("README", "git", 5)]
    for dtype, source, n in plan:
        for _ in range(n):
            dom = rng.choice(D.DOMAINS)
            pool = [a for a in apps if a["domain"] == dom]
            scope = rng.sample(pool, min(len(pool), rng.randint(2, 4)))
            age = rng.choice([rng.randint(15, 200), rng.randint(15, 200), rng.randint(200, 600), rng.randint(600, 1300)])
            label = {"HLD": "High-Level Design", "LLD": "Low-Level Design", "Confluence": "Solution Overview", "SharePoint": "Architecture Note", "diagram": "Context Diagram", "PDF": "Vendor Architecture Pack", "README": "Service README"}[dtype]
            title = f"{scope[0]['name']} {label}"
            if any(d["title"] == title for d in docs):
                title = f"{scope[0]['name']} and {scope[-1]['name']} {label}"
            body = render(title, dtype, scope, mk("Current" if age < 400 else "Outdated", age, f"{label} for the {dom} domain.", rng.choice(owner_by_domain.get(dom, owners))["name"]), None, 0.6)
            if dtype == "README":
                body = f"# {scope[0]['name']}\n\n```\nDB_HOST=policy-master-db.nwa.internal\n```\n\n" + body
            add_doc(title, dtype, source, dom, age, body, tags=[slug(dom)])
    return docs[:60] if len(docs) >= 60 else docs


# ================================================================== governance
def build_governance(by_key, owners):
    arbs = []
    owner_id = {o["name"]: o["id"] for o in owners}
    for a in G.ARB:
        a = dict(a)
        a["submitter_id"] = owner_id[a["submitter"]]
        a["linked_apps"] = [by_key[k]["id"] for k in a.pop("apps")]
        arbs.append(a)
    patterns = [dict(id=i, name=n, category=c, summary=s, tags=t, adoption_count=u, status="approved") for i, n, c, s, t, u in G.PATTERNS]
    return G.STANDARDS, patterns, arbs


# ====================================================================== main
def write(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def self_check(apps, dbs, apis, ints, cloud, workflows, docs, by_key):
    assert len(apps) >= 65, len(apps)
    assert len(dbs) == 45, len(dbs)
    assert len(apis) == 180, len(apis)
    assert len(cloud) == 300, len(cloud)
    direct = [i for i in ints if i["style"] == "direct_db"]
    assert len(direct) == 17, len(direct)
    ora = next(d for d in dbs if d["engine"] == "Oracle 12c")
    users = {i["source_id"] for i in direct if i["target_id"] == ora["id"] and i["source_kind"] == "app"}
    users |= {a["id"] for a in apps if a["db_key"] == ora["key"]}
    assert len(users) == 9, len(users)
    claims_caps = {c[0] for c in D.CAPABILITIES if c[0].startswith("CAP-CLM")}
    claims_users = [a for a in apps if a["id"] in users and set(a["capabilities"]) & claims_caps]
    assert len(claims_users) == 4, [a["name"] for a in claims_users]
    c2 = next(a for a in apis if a.get("special") == "customer_v2")
    assert len(c2["consumers"]) == 14
    assert sum(1 for w in workflows if c2["id"] in w["apis"]) == 6
    assert len([r for r in cloud if r.get("drift_meta")]) == 25
    assert 55 <= len(docs) <= 60 or len(docs) == 60, len(docs)


def main() -> Path:
    owners = build_owners()
    caps = build_capabilities()
    techs, tech_map = build_technologies()
    tech_lc = {n: (c, l) for n, (c, l, _) in tech_map.items()}
    apps, by_key = build_apps(owners, tech_lc)
    dbs, by_dbkey = build_databases(apps, by_key, tech_lc)
    apis = build_apis(apps, by_key, owners)
    ints = build_integrations(apps, by_key, dbs, by_dbkey, apis)
    cloud = apply_drift(build_cloud(apps, by_key, dbs))
    workflows = build_workflows(apps, by_key, apis)
    docs = build_documents(apps, by_key, dbs, by_dbkey, apis, ints, owners)
    standards, patterns, arbs = build_governance(by_key, owners)

    # extra datastore usage (uses edges) beyond each app's primary DB
    uses_extra = []
    for ak, dk in (("CAM", "SNOW_CLM"), ("PBI", "SNOW_CLM"), ("PBI", "SNOW_POL"), ("RRH", "SNOW_POL"), ("C360", "SNOW_C360"), ("DBX", "ADLS_SILVER"),
                   ("DBX", "ADLS_GOLD"), ("CDV", "S3_ARCH"), ("PQP", "REDIS_QUOTE"), ("FSE", "SNOW_FRD")):
        uses_extra.append(dict(app_id=by_key[ak]["id"], db_id=by_dbkey[dk]["id"]))

    self_check(apps, dbs, apis, ints, cloud, workflows, docs, by_key)

    write("owners", owners)
    write("capabilities", caps)
    write("technologies", techs)
    write("applications", apps)
    write("databases", dbs)
    write("apis", apis)
    write("integrations", ints)
    write("cloud_resources", cloud)
    write("workflows", workflows)
    write("documents", docs)
    write("standards", standards)
    write("patterns", patterns)
    write("arb_submissions", arbs)
    write("uses_extra", uses_extra)
    write("meta", dict(seed=SEED, reference_date=REF_DATE.isoformat(), enterprise="Northwind Assurance",
                       counts=dict(applications=len(apps), apis=len(apis), databases=len(dbs), integrations=len(ints),
                                   cloud_resources=len(cloud), capabilities=len(caps), owners=len(owners), documents=len(docs),
                                   standards=len(standards), patterns=len(patterns), drift=25, arb=len(arbs), workflows=len(workflows))))
    return OUT


if __name__ == "__main__":
    out = main()
    print(f"Seed written to {out}")
