"""In-memory repository over the seeded JSON, plus the architecture knowledge graph (networkx).

Everything in ArchIQ reads through this single store so all 15 modules agree with each other.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from functools import lru_cache
from typing import Any

import networkx as nx

from app.core.config import BACKEND_ROOT, SEED_DIR

NODE_TYPES = {"application": "App", "api": "API", "database": "Data", "capability": "Capability", "owner": "Owner", "cloud": "Cloud"}
LIFECYCLE_OF_API = {"active": "supported", "beta": "supported", "deprecated": "extended", "retired": "eol"}
SEED_FILES = ["owners", "capabilities", "technologies", "applications", "databases", "apis", "integrations", "cloud_resources",
              "workflows", "documents", "standards", "patterns", "arb_submissions", "uses_extra", "meta"]


def ensure_seed() -> None:
    """Generate the seed on first start if any file is missing (deterministic, seed 42)."""
    if all((SEED_DIR / f"{n}.json").exists() for n in SEED_FILES):
        return
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from scripts.generate_seed import main as generate

    generate()


def _load(name: str) -> Any:
    return json.loads((SEED_DIR / f"{name}.json").read_text(encoding="utf-8"))


class Store:
    def __init__(self) -> None:
        ensure_seed()
        self.meta = _load("meta")
        self.ref_date = datetime.fromisoformat(self.meta["reference_date"])
        self.owners = _load("owners")
        self.capabilities = _load("capabilities")
        self.technologies = {t["name"]: t for t in _load("technologies")}
        self.apps = _load("applications")
        self.dbs = _load("databases")
        self.apis = _load("apis")
        self.integrations = _load("integrations")
        self.cloud = _load("cloud_resources")
        self.workflows = _load("workflows")
        self.documents = _load("documents")
        self.standards = _load("standards")
        self.patterns = _load("patterns")
        self.arb = _load("arb_submissions")
        self.uses_extra = _load("uses_extra")

        self.by_id: dict[str, dict] = {}
        for typ, rows in (("application", self.apps), ("api", self.apis), ("database", self.dbs), ("cloud", self.cloud),
                          ("capability", self.capabilities), ("owner", self.owners), ("integration", self.integrations),
                          ("document", self.documents), ("workflow", self.workflows)):
            for r in rows:
                r["_type"] = typ
                self.by_id[r["id"]] = r
        self.standards_by_id = {s["id"]: s for s in self.standards}
        self.app_by_key = {a["key"]: a for a in self.apps}
        self.graph = self._build_graph()

    # ------------------------------------------------------------------ graph
    def _build_graph(self) -> nx.MultiDiGraph:
        g = nx.MultiDiGraph()
        for typ, rows in (("application", self.apps), ("api", self.apis), ("database", self.dbs), ("capability", self.capabilities),
                          ("owner", self.owners), ("cloud", self.cloud)):
            for r in rows:
                g.add_node(r["id"], type=typ, ntype=NODE_TYPES[typ], name=r["name"], domain=r.get("domain"),
                           lifecycle=self.lifecycle_of(r), criticality=r.get("criticality"))
        db_by_key = {d["key"]: d for d in self.dbs}
        for a in self.apps:
            g.add_edge(a["id"], a["owner_id"], rel="owned_by")
            for c in a["capabilities"]:
                g.add_edge(a["id"], c, rel="supports")
            if a["db_key"] and a["db_key"] in db_by_key:
                g.add_edge(a["id"], db_by_key[a["db_key"]]["id"], rel="uses")
        for u in self.uses_extra:
            g.add_edge(u["app_id"], u["db_id"], rel="uses")
        for d in self.dbs:
            g.add_edge(d["id"], self.by_id[d["owner_app"]]["owner_id"], rel="owned_by")
        for api in self.apis:
            g.add_edge(api["exposed_by"], api["id"], rel="exposes")
            g.add_edge(api["id"], api["owner_id"], rel="owned_by")
            for c in api["consumers"]:
                g.add_edge(c, api["id"], rel="consumes")
        for r in self.cloud:
            if r["app_id"]:
                g.add_edge(r["app_id"], r["id"], rel="hosted_on")
        # databases hosted on a matching cloud resource of their owning app
        want = {"PostgreSQL": "postgres", "Cosmos DB": "cosmos_db", "ADLS Gen2": "data_lake"}
        for d in self.dbs:
            for prefix, rtype in want.items():
                if d["engine"].startswith(prefix):
                    hit = next((r for r in self.cloud if r["app_id"] == d["owner_app"] and r["type"] == rtype and r["env"] == "prod"), None)
                    if hit:
                        g.add_edge(d["id"], hit["id"], rel="hosted_on")
        for i in self.integrations:
            if i["style"] == "direct_db":
                g.add_edge(i["source_id"], i["target_id"], rel="direct_db", integration=i["id"])
                continue
            via = i.get("via")
            if via:
                g.add_edge(i["source_id"], via, rel="integrates", integration=i["id"], style=i["style"], hop="to_hub")
                g.add_edge(via, i["target_id"], rel="integrates", integration=i["id"], style=i["style"], hop="from_hub")
            else:
                g.add_edge(i["source_id"], i["target_id"], rel="integrates", integration=i["id"], style=i["style"])
        return g

    # ------------------------------------------------------------- helpers
    def lifecycle_of(self, r: dict) -> str:
        if "lifecycle" in r:
            return LIFECYCLE_OF_API.get(r["lifecycle"], r["lifecycle"]) if "exposed_by" in r else r["lifecycle"]
        return "supported"

    def get(self, ident: str) -> dict | None:
        return self.by_id.get(ident)

    def owner(self, owner_id: str) -> dict:
        o = self.by_id[owner_id]
        return {"id": o["id"], "name": o["name"], "team": o["team"]}

    def name(self, ident: str) -> str:
        r = self.by_id.get(ident)
        return r["name"] if r else ident

    def cap_ancestors(self, cap_id: str) -> list[str]:
        out, cur = [], self.by_id.get(cap_id)
        while cur:
            out.append(cur["id"])
            cur = self.by_id.get(cur["parent"]) if cur.get("parent") else None
        return out

    def supports(self, app: dict, cap_id: str) -> bool:
        return any(cap_id in self.cap_ancestors(c) for c in app["capabilities"])

    def cloud_of(self, app: dict) -> str:
        return {"azure": "Azure", "aws": "AWS", "saas": "SaaS", "on-prem": "On-premises", "mainframe": "Mainframe"}[app["hosting"]]

    def asset(self, r: dict) -> dict:
        """Uniform asset summary used by lists, search and the inspector."""
        typ = r["_type"]
        base = dict(id=r["id"], type=typ, name=r["name"], domain=r.get("domain"), lifecycle=self.lifecycle_of(r),
                    criticality=r.get("criticality", "medium"))
        if typ == "application":
            base.update(owner=self.owner(r["owner_id"]), tech=r["tech"], cloud=self.cloud_of(r), kind=r["kind"], users=r["users"],
                        annual_cost_k=r["annual_cost_k"])
        elif typ == "api":
            base.update(owner=self.owner(r["owner_id"]), tech=[r["protocol"]], cloud="—", version=r["version"], protocol=r["protocol"],
                        api_status=r["lifecycle"], consumers=len(r["consumers"]), criticality=r["sla_tier"], exposed_by=self.name(r["exposed_by"]))
        elif typ == "database":
            base.update(owner=self.owner(self.by_id[r["owner_app"]]["owner_id"]), tech=[r["engine"]], cloud=r["hosting"].title(),
                        engine=r["engine"], size_gb=r["size_gb"], classification=r["classification"])
        elif typ == "cloud":
            base.update(owner={"id": "", "name": r["tags"].get("owner", "—"), "team": r["tags"].get("owner", "—")}, tech=[r["type"]],
                        cloud=r["provider"].upper(), region=r["region"], env=r["env"], resource_type=r["type"],
                        criticality=r.get("criticality") or self.by_id[r["app_id"]]["criticality"] if r["app_id"] else "medium",
                        drifted=bool(r.get("drift_meta")))
        elif typ == "integration":
            base.update(owner={"id": "", "name": "—", "team": "—"}, tech=[r["style"]], cloud="—", style=r["style"], frequency=r["frequency"],
                        source=self.name(r["source_id"]), target=self.name(r["target_id"]), domain=self.by_id[r["source_id"]].get("domain"))
        elif typ == "capability":
            base.update(owner={"id": "", "name": "—", "team": "—"}, tech=[], cloud="—", level=r["level"])
        elif typ == "owner":
            base.update(owner={"id": r["id"], "name": r["name"], "team": r["team"]}, tech=[], cloud="—", role=r["role"])
        elif typ == "document":
            base.update(owner=self.owner(r["author_id"]), tech=[r["doc_type"]], cloud="—", domain=r["domain"])
        return base


@lru_cache
def get_store() -> Store:
    return Store()
