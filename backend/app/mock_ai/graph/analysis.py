"""Graph algorithms over the architecture knowledge graph (networkx). Real computation, no hardcoded answers."""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache

import networkx as nx

from app.repositories.store import Store, get_store

CRIT_W = {"critical": 4, "high": 3, "medium": 2, "low": 1}
CHANGE_FACTOR = {"breaking_change": 1.0, "deprecation": 0.7, "version_upgrade": 0.5, "decommission": 1.25, "schema_change": 0.9}


# ------------------------------------------------------------------ derived graphs
@lru_cache
def impact_graph() -> nx.DiGraph:
    """Edge a -> b means 'a change in a can break b'."""
    s = get_store()
    g, i = s.graph, nx.DiGraph()
    i.add_nodes_from(g.nodes)
    for u, v, d in g.edges(data=True):
        rel = d["rel"]
        if rel == "consumes":
            i.add_edge(v, u, rel=rel)  # api -> consumer app
        elif rel in ("exposes", "integrates"):
            i.add_edge(u, v, rel=rel)
        elif rel in ("uses", "direct_db"):
            if g.nodes[u]["type"] == "application":
                i.add_edge(v, u, rel=rel)  # database -> app that reads it
            else:
                i.add_edge(u, v, rel="db_link")
        elif rel == "hosted_on":
            i.add_edge(v, u, rel=rel)  # cloud resource -> workload on it
    return i


@lru_cache
def app_graph() -> nx.Graph:
    """Undirected app-to-app coupling graph (integrations incl. hubs, API consumption, direct DB access)."""
    s = get_store()
    g, a = s.graph, nx.Graph()
    apps = {x["id"] for x in s.apps}
    a.add_nodes_from(apps)
    api_owner = {x["id"]: x["exposed_by"] for x in s.apis}
    db_owner = {x["id"]: x["owner_app"] for x in s.dbs}
    for u, v, d in g.edges(data=True):
        rel = d["rel"]
        if rel == "integrates" and u in apps and v in apps:
            a.add_edge(u, v)
        elif rel == "consumes" and u in apps:
            a.add_edge(u, api_owner[v])
        elif rel in ("direct_db", "uses") and u in apps and v in db_owner and db_owner[v] != u:
            a.add_edge(u, db_owner[v])
    a.remove_edges_from(nx.selfloop_edges(a))
    return a


@lru_cache
def flow_graph() -> nx.DiGraph:
    """Directed app-to-app dependency flows without hubs (for cycle / tight-coupling detection)."""
    s = get_store()
    f = nx.DiGraph()
    apps = {x["id"] for x in s.apps}
    hubs = {s.app_by_key[k]["id"] for k in ("MULE", "KAFKA", "APIM", "IIB", "MFT")}
    f.add_nodes_from(apps - hubs)
    for i in s.integrations:
        if i["source_kind"] == "app" and i["target_kind"] == "app" and i["source_id"] not in hubs and i["target_id"] not in hubs and not i.get("via"):
            f.add_edge(i["source_id"], i["target_id"])
    return f


# ------------------------------------------------------------------ impact
def impact(asset_id: str, change_type: str = "breaking_change", max_hops: int = 3) -> dict:
    s = get_store()
    ig = impact_graph()
    levels: dict[str, int] = {asset_id: 0}
    frontier = [asset_id]
    for hop in range(1, max_hops + 1):
        nxt = []
        for n in frontier:
            for m in ig.successors(n):
                if m not in levels:
                    levels[m] = hop
                    nxt.append(m)
        frontier = nxt
    root = s.by_id[asset_id]
    hop_apps: dict[int, list[str]] = defaultdict(list)
    hop_apis: dict[int, list[str]] = defaultdict(list)
    other: dict[str, list[str]] = defaultdict(list)
    for n, h in levels.items():
        if h == 0:
            continue
        t = s.graph.nodes[n]["type"]
        if t == "application":
            hop_apps[h].append(n)
        elif t == "api":
            hop_apis[h].append(n)
        else:
            other[t].append(n)
    direct_apps = sorted(hop_apps[1])
    indirect_apps = sorted(a for h in (2, 3) for a in hop_apps[h])

    # workflows: for an API, those that invoke it; otherwise those touching the asset or any directly impacted app
    wf_hits = []
    for w in s.workflows:
        if root["_type"] == "api":
            hit = asset_id in w["apis"]
        else:
            hit = asset_id in w["apps"] or bool(set(w["apps"]) & set(direct_apps))
        if hit:
            wf_hits.append(w["id"])

    teams: dict[str, dict] = {}
    for a in direct_apps + indirect_apps:
        o = s.owner(s.by_id[a]["owner_id"])
        t = teams.setdefault(o["team"], dict(team=o["team"], owner=o["name"], direct=0, indirect=0))
        t["direct" if a in direct_apps else "indirect"] += 1

    caps = sorted({c for a in direct_apps for c in s.by_id[a]["capabilities"]})
    crit_weight = sum(CRIT_W[s.by_id[a]["criticality"]] for a in direct_apps)
    crit_apps = [a for a in direct_apps if s.by_id[a]["criticality"] in ("critical", "high")]
    raw = (crit_weight * 1.6 + len(indirect_apps) * 0.35 + len(wf_hits) * 4.5 + len(crit_apps) * 2) * CHANGE_FACTOR.get(change_type, 1.0)
    score = min(100, round(100 * (1 - 2.718281828 ** (-raw / 95))))
    rating = "critical" if score >= 75 else "high" if score >= 50 else "medium" if score >= 28 else "low"
    return dict(
        asset_id=asset_id, levels=levels, direct_apps=direct_apps, indirect_apps=indirect_apps,
        hop_apps={h: sorted(v) for h, v in hop_apps.items()}, hop_apis={h: sorted(v) for h, v in hop_apis.items()},
        databases=sorted(other.get("database", [])), workflows=wf_hits, teams=sorted(teams.values(), key=lambda t: -(t["direct"] * 3 + t["indirect"])),
        capabilities=caps, critical_apps=crit_apps, risk_score=score, risk_rating=rating,
    )


# ------------------------------------------------------------------ SPOF & coupling
@lru_cache
def spofs() -> list[dict]:
    """Single points of failure: articulation points of the app graph plus unprotected single-instance systems."""
    s = get_store()
    a = app_graph()
    arts = set(nx.articulation_points(a))
    out = []
    for n in sorted(a.nodes):
        app = s.by_id[n]
        reasons = []
        isolated = 0
        if n in arts:
            h = a.copy()
            h.remove_node(n)
            comps = sorted((len(c) for c in nx.connected_components(h)), reverse=True)
            isolated = sum(comps[1:])
            if isolated >= 1:
                reasons.append(f"Articulation point: removing it disconnects {isolated} application(s) from the rest of the estate")
        deg = a.degree(n)
        if app["single_instance"] and CRIT_W[app["criticality"]] >= 3 and deg >= 3:
            reasons.append(f"Single instance with no active-active deployment (DR tier: {app['dr_tier']}) and {deg} coupled systems")
        if app["dr_tier"] == "none" and CRIT_W[app["criticality"]] >= 3:
            reasons.append("No disaster recovery tier for a high-criticality system")
        bc = coupling()["betweenness"].get(n, 0)
        if bc >= 0.08:
            reasons.append(f"Concentration risk: {round(bc * 100)}% of shortest dependency paths between applications traverse it")
        if not reasons:
            continue
        score = isolated * 3 + round(bc * 120) + deg + CRIT_W[app["criticality"]] * 4 + (8 if app["single_instance"] else 0)
        out.append(dict(app_id=n, name=app["name"], domain=app["domain"], criticality=app["criticality"], degree=deg, isolated_apps=isolated,
                        articulation=n in arts, single_instance=app["single_instance"], dr_tier=app["dr_tier"], reasons=reasons, score=score))
    return sorted(out, key=lambda r: -r["score"])


@lru_cache
def coupling() -> dict:
    s = get_store()
    a = app_graph()
    between = nx.betweenness_centrality(a)  # exact: 69 nodes, and sampling made results depend on set iteration order
    degree = dict(a.degree())
    f = flow_graph()
    clusters = [sorted(c) for c in nx.strongly_connected_components(f) if len(c) >= 3]
    hubs = sorted(a.nodes, key=lambda n: -(degree[n] + between[n] * 100))[:8]
    return dict(
        betweenness={k: round(v, 4) for k, v in between.items()}, degree=degree, clusters=sorted(clusters, key=len, reverse=True),
        hubs=[dict(app_id=h, name=s.by_id[h]["name"], degree=degree[h], betweenness=round(between[h], 3)) for h in hubs],
    )


# ------------------------------------------------------------------ paths & chains
def shortest_path(src: str, dst: str) -> list[dict] | None:
    """Prefer a directed dependency flow (consumer->provider, producer->consumer); fall back to undirected."""
    s = get_store()
    g = s.graph
    d = nx.DiGraph()
    for u, v, data in g.edges(data=True):
        if data["rel"] in ("integrates", "consumes", "exposes", "uses", "direct_db", "hosted_on"):
            d.add_edge(u, v, rel=data["rel"], **({"style": data["style"]} if "style" in data else {}))
    path = None
    try:
        path = nx.shortest_path(d, src, dst)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        u = nx.Graph(g.to_undirected())
        try:
            path = nx.shortest_path(u, src, dst)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
    out = []
    for i, n in enumerate(path):
        step = dict(id=n, name=g.nodes[n]["name"], type=g.nodes[n]["ntype"], rel=None)
        if i:
            edges = g.get_edge_data(path[i - 1], n) or g.get_edge_data(n, path[i - 1]) or {}
            step["rel"] = next(iter(edges.values()))["rel"] if edges else "related"
        out.append(step)
    return out


def story_chain() -> list[dict]:
    """SAP -> MuleSoft -> Salesforce -> Snowflake, verified against real integration edges."""
    s = get_store()
    keys = ["SAP", "MULE", "SFC", "SNOW"]
    ids = [s.app_by_key[k]["id"] for k in keys]
    chain = []
    for i, n in enumerate(ids):
        step = dict(id=n, name=s.by_id[n]["name"], type="App", integration=None, style=None)
        if i:
            hit = next((x for x in s.integrations if x["source_id"] == ids[i - 1] and x["target_id"] == n), None)
            if hit:
                step.update(integration=hit["id"], style=hit["style"], payload=hit["payload"])
        chain.append(step)
    return chain


def chain_for(node_id: str) -> list[dict]:
    """App -> API -> Data -> Business Capability -> Owner -> Cloud for any node."""
    s = get_store()
    node = s.by_id[node_id]
    t = node["_type"]
    app = None
    if t == "application":
        app = node
    elif t == "api":
        app = s.by_id[node["exposed_by"]]
    elif t == "database":
        app = s.by_id[node["owner_app"]]
    elif t == "cloud" and node["app_id"]:
        app = s.by_id[node["app_id"]]
    elif t == "capability":
        app = next((a for a in s.apps if node_id in a["capabilities"]), None)
    elif t == "owner":
        app = next((a for a in s.apps if a["owner_id"] == node_id), None)
    if not app:
        return []
    apis = sorted((x for x in s.apis if x["exposed_by"] == app["id"]), key=lambda x: -len(x["consumers"]))
    db = next((d for d in s.dbs if d["key"] == app["db_key"]), None)
    cap = s.by_id[app["capabilities"][0]]
    cloud = next((r for r in s.cloud if r["app_id"] == app["id"] and r["env"] == "prod"), None)
    chain = [("App", app["id"], app["name"])]
    if apis:
        chain.append(("API", apis[0]["id"], f"{apis[0]['name']} {apis[0]['version']}"))
    if db:
        chain.append(("Data", db["id"], db["name"]))
    chain.append(("Capability", cap["id"], cap["name"]))
    chain.append(("Owner", app["owner_id"], s.by_id[app["owner_id"]]["name"]))
    if cloud:
        chain.append(("Cloud", cloud["id"], cloud["name"]))
    else:
        chain.append(("Cloud", app["id"], s.cloud_of(app)))
    return [dict(type=a, id=b, name=c) for a, b, c in chain]


# ------------------------------------------------------------------ neighbourhood
LAYER_TYPES = {"app": "application", "api": "api", "data": "database", "capability": "capability", "owner": "owner", "cloud": "cloud"}


def subgraph(layers: list[str] | None, focus: str | None, hops: int, limit: int = 900) -> dict:
    s: Store = get_store()
    g = s.graph
    allowed = {LAYER_TYPES[x] for x in (layers or LAYER_TYPES.keys()) if x in LAYER_TYPES}
    if focus and focus in g:
        und = g.to_undirected(as_view=True)
        nodes = {focus} | set(nx.single_source_shortest_path_length(und, focus, cutoff=max(1, hops)).keys())
        nodes = {n for n in nodes if n == focus or g.nodes[n]["type"] in allowed}
    else:
        nodes = {n for n, d in g.nodes(data=True) if d["type"] in allowed}
        # connected-component pruning of orphan cloud/owner nodes keeps the canvas readable
        nodes = {n for n in nodes if g.degree(n) > 0}
    if len(nodes) > limit:
        ranked = sorted(nodes, key=lambda n: -g.degree(n))
        nodes = set(ranked[:limit])
    deg = dict(g.degree())
    edges, seen = [], set()
    for u, v, d in g.edges(data=True):
        if u in nodes and v in nodes:
            k = (u, v, d["rel"])
            if k in seen:
                continue
            seen.add(k)
            edges.append(dict(id=f"{u}>{v}:{d['rel']}", source=u, target=v, rel=d["rel"], style=d.get("style")))
    return dict(
        nodes=[dict(id=n, name=g.nodes[n]["name"], type=g.nodes[n]["ntype"], domain=g.nodes[n]["domain"], lifecycle=g.nodes[n]["lifecycle"],
                    criticality=g.nodes[n]["criticality"], degree=deg[n]) for n in nodes],
        edges=edges, total_nodes=g.number_of_nodes(), total_edges=g.number_of_edges(),
    )
