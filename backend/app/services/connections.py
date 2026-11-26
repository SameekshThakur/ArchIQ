"""Saved platform connections: configuration, test, sync, and what each sync feeds into the rest of ArchIQ.

Configuration lives in the local database (`items` of kind "connection"). Secrets are stored server-side and are
never returned by the API; a secret may also be written as `env:NAME` to read it from the server environment.
Every sync is read-only towards the platform. Its results are applied inside ArchIQ only:

* ServiceNow rows  -> the inventory reconciler, saved as a Discovery import
* Confluence, SharePoint pages and GitHub docs -> Document intelligence (previous copies are replaced)
* Azure resources and GitHub infrastructure code -> the standards checker
* Azure (deployed) and GitHub (approved) together -> live drift, matched by resource name
* Jira issues -> open work per application
"""

from __future__ import annotations

import csv
import io
import re
import threading
from datetime import datetime, timezone
from typing import Any

from app.connectors import base
from app.connectors.platforms import CONNECTORS
from app.core.errors import BadRequest, NotFound
from app.repositories import persist
from app.repositories.store import get_store

_lock = threading.Lock()
_running: set[str] = set()
DRIFT_IGNORE = {"id", "name", "type", "source", "provisioned_by", "region", "tags_complete", "logging", "technology", "location"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connector(pid: str):
    c = CONNECTORS.get(pid)
    if not c:
        raise NotFound(f"Unknown platform '{pid}'")
    return c


# ------------------------------------------------------------------ storage
def _row(pid: str) -> dict | None:
    return next((r for r in persist.list_items("connection", 100) if r.get("platform") == pid), None)


def _save(pid: str, data: dict) -> dict:
    row = _row(pid)
    payload = {k: v for k, v in data.items() if k not in ("id", "created_at")}
    payload["platform"] = pid
    if row:
        persist.update_item("connection", row["id"], payload)
        return dict(payload, id=row["id"])
    return dict(payload, id=persist.add_item("connection", payload))


def _latest_sync(pid: str, full: bool = False) -> dict | None:
    row = next((r for r in persist.list_items("connection_sync", 60) if r.get("platform") == pid), None)
    if row and not full:
        row = {k: row[k] for k in ("id", "at", "mode", "ok", "error", "headline", "metrics", "duration_ms") if k in row}
    return row


def public(pid: str) -> dict:
    c = connector(pid)
    row = _row(pid) or {}
    secrets = row.get("secrets", {})
    status = "not_connected"
    if row:
        last = _latest_sync(pid)
        if row.get("mode") == "demo":
            status = "demo"
        elif last and not last.get("ok"):
            status = "error"
        elif (row.get("last_test") or {}).get("ok") is False:
            status = "error"
        elif last and last.get("ok"):
            status = "connected"
        else:
            status = "configured"
    return dict(c.public(), configured=bool(row), mode=row.get("mode", "live"), status=status, config=row.get("config", {}),
                secrets_set={f.key: bool(secrets.get(f.key)) for f in c.fields if f.kind == "secret"},
                secret_refs={f.key: secrets[f.key] for f in c.fields if f.kind == "secret" and str(secrets.get(f.key, "")).startswith("env:")},
                last_test=row.get("last_test"), last_sync=_latest_sync(pid), syncing=pid in _running)


def overview() -> dict:
    items = [public(p) for p in CONNECTORS]
    return dict(items=items, drift=live_drift(), summary=dict(total=len(items), connected=sum(1 for i in items if i["status"] in ("connected", "demo")),
                                                         errors=sum(1 for i in items if i["status"] == "error")))


def configure(pid: str, mode: str, config: dict[str, Any], secrets: dict[str, str | None]) -> dict:
    c = connector(pid)
    if mode not in ("live", "demo"):
        raise BadRequest("mode must be 'live' or 'demo'")
    plain = {f.key for f in c.fields if f.kind != "secret"}
    secret_keys = {f.key for f in c.fields if f.kind == "secret"}
    unknown = (set(config) - plain) | (set(secrets) - secret_keys)
    if unknown:
        raise BadRequest(f"Unknown fields: {', '.join(sorted(unknown))}")
    row = _row(pid) or {}
    stored = dict(row.get("secrets", {}))
    for k, v in secrets.items():
        if v is None:
            stored.pop(k, None)
        elif str(v).strip():
            stored[k] = str(v).strip()
    cfg = {k: str(v).strip() for k, v in config.items() if v is not None}
    _save(pid, dict(row, mode=mode, config=cfg, secrets=stored, last_test=None, updated_at=_now()))
    return public(pid)


def remove(pid: str) -> dict:
    connector(pid)
    row = _row(pid)
    if not row:
        raise NotFound(f"{pid} is not configured")
    _undo_documents(pid)
    persist.delete_item("connection", row["id"])
    for s in persist.list_items("connection_sync", 200):
        if s.get("platform") == pid:
            persist.delete_item("connection_sync", s["id"])
    return dict(removed=pid)


def _cfg(pid: str) -> tuple[dict, dict]:
    row = _row(pid)
    if not row:
        raise BadRequest("Save the connection settings first.")
    return row, dict(row.get("config", {}), **row.get("secrets", {}))


# --------------------------------------------------------------------- test
def test(pid: str) -> dict:
    c = connector(pid)
    row, cfg = _cfg(pid)
    if row.get("mode") == "demo":
        res = dict(ok=True, detail="Not live: no external call is made. Sync reads from the local estate snapshot.", at=_now())
    else:
        try:
            with base.client() as http:
                res = dict(ok=True, detail=c.test(cfg, http), at=_now())
        except base.ConnectorError as e:
            res = dict(ok=False, detail=str(e), at=_now())
        except Exception as e:  # noqa: BLE001
            res = dict(ok=False, detail=f"Unexpected error: {type(e).__name__}: {str(e)[:200]}", at=_now())
    _save(pid, dict(row, last_test=res))
    return dict(res, connection=public(pid))


# --------------------------------------------------------------------- sync
def fetch(pid: str) -> tuple[str, base.SyncData | None, str | None]:
    """Blocking: call the platform (or build the demo data). Run in a worker thread."""
    c = connector(pid)
    row, cfg = _cfg(pid)
    with _lock:
        if pid in _running:
            raise BadRequest(f"{c.name} is already syncing")
        _running.add(pid)
    try:
        if row.get("mode") == "demo":
            return "demo", c.demo(), None
        try:
            with base.client() as http:
                return "live", c.fetch(cfg, http), None
        except base.ConnectorError as e:
            return "live", None, str(e)
        except Exception as e:  # noqa: BLE001
            return "live", None, f"Unexpected error: {type(e).__name__}: {str(e)[:200]}"
    finally:
        _running.discard(pid)


def _undo_documents(pid: str) -> None:
    from app.mock_ai.generators import documents as docs

    last = _latest_sync(pid, full=True)
    for d in (last or {}).get("doc_ids", []):
        docs.remove_upload(d)


def _to_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    cols = ["name", "number", "owner", "criticality", "team", "status", "domain", "hosting"]
    w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in cols})
    return out.getvalue()


def _work_by_app(items: list[dict]) -> list[dict]:
    s = get_store()
    pats = [(a, re.compile(r"\b" + re.escape(a["name"]) + r"\b", re.I)) for a in sorted(s.apps, key=lambda a: -len(a["name"]))]
    per: dict[str, dict] = {}
    for it in items:
        hay = " ".join([it.get("summary", ""), *it.get("components", []), *it.get("labels", [])])
        app = next((a for a, p in pats if p.search(hay)), None)
        if not app:
            continue
        e = per.setdefault(app["id"], dict(app_id=app["id"], app=app["name"], open=0, done=0, keys=[]))
        e["done" if it.get("category") == "done" else "open"] += 1
        e["keys"].append(it.get("key"))
    return sorted(per.values(), key=lambda e: -e["open"])


async def apply(pid: str, mode: str, data: base.SyncData | None, error: str | None, started: float) -> dict:
    """Feed a fetched sync into ArchIQ and save the run."""
    import time

    from app.mock_ai.generators import documents as docs
    from app.mock_ai.rules import standards
    from app.services import inventory

    c = connector(pid)
    run: dict[str, Any] = dict(platform=pid, mode=mode, at=_now(), ok=error is None, error=error, metrics=[], effects=[], records=[], doc_ids=[])
    if data is not None:
        run["records"] = data.records[:50]
        run["record_count"] = len(data.records)
        run["meta"] = data.meta
        metrics = [dict(label="Records read", value=len(data.records))]
        if data.cmdb_rows:
            r = inventory.reconcile(f"{c.name} sync", _to_csv(data.cmdb_rows))
            from app.services.ai import narrate

            facts = dict(filename=r["filename"], rows=r["rows"], matched=r["matched"], conflicts=r["conflicts"], probable=r["probable"], new=r["new"], missing=len(r["missing"]),
                         missing_top=[m["name"] for m in r["missing"][:3]], fields=[f for f, _ in sorted(r["conflict_fields"].items(), key=lambda kv: -kv[1])[:3]])
            ai = await narrate("discovery.import", facts, [("Read records", f"{r['rows']} rows from {c.name}", 120), ("Match to estate", "normalised name, then fuzzy match", 380),
                                                           ("Compare attributes", "criticality, hosting, owner, lifecycle", 260)],
                               [("application", x["asset_id"], x["name"]) for x in r["items"] if x["status"] == "conflict"][:4])
            imp = dict(r, ai=ai, source=pid)
            run["import_id"] = persist.add_item("import", imp)
            metrics += [dict(label="Matched", value=r["matched"]), dict(label="Conflicts", value=r["conflicts"]), dict(label="Not in estate", value=r["new"]),
                        dict(label="Missing from CMDB", value=len(r["missing"]))]
            run["effects"].append(dict(label="Reconciled against the estate", detail=f"{r['matched']} matched, {r['conflicts']} with differing attributes, {r['new']} unknown to ArchIQ", to="/discovery"))
        if data.documents:
            _undo_documents(pid)
            for d in data.documents[:60]:
                a = docs.ingest(d["title"][:200] if len(d["title"]) >= 3 else f"{c.name} document", d["text"][:400_000], d.get("doc_type", "Confluence"), "Integration & Platform")
                run["doc_ids"].append(a["id"])
            metrics.append(dict(label="Documents added", value=len(run["doc_ids"])))
            run["effects"].append(dict(label="Added to Document intelligence", detail=f"{len(run['doc_ids'])} documents analysed for components, gaps and conflicts", to="/documents"))
        if data.components:
            chk = standards.check_design(dict(name=f"{c.name} sync", components=data.components, format=pid))
            fails = [x for x in chk["results"] if x["status"] == "fail"]
            run["components"] = data.components[:2000]
            run["standards"] = dict(score=chk.get("score"), checked=len(chk["results"]), failed=len(fails), passed=chk.get("passed", 0), warned=chk.get("warned", 0), components=len(data.components),
                                    top=[dict(standard_id=x["standard_id"], title=x["title"], severity=x["severity"], count=len(x.get("components", []))) for x in
                                         sorted(fails, key=lambda x: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x["severity"], 4), -len(x.get("components", []))))[:8]])
            metrics += [dict(label="Components checked", value=len(data.components)), dict(label="Standards failed", value=len(fails))]
            run["effects"].append(dict(label="Checked against standards", detail=f"{len(fails)} failing standards across {len(data.components)} components", to="/standards"))
        if data.work_items:
            per = _work_by_app(data.work_items)
            run["work"] = per[:30]
            metrics += [dict(label="Open items", value=sum(1 for w in data.work_items if w.get("category") != "done")), dict(label="Linked applications", value=len(per))]
            run["effects"].append(dict(label="Linked to applications", detail=f"work items mention {len(per)} applications in the estate", to=None))
        run["metrics"] = metrics
        run["headline"] = f"{len(data.records)} records read" + (f", {len(run['doc_ids'])} documents added" if run["doc_ids"] else "")
    else:
        run["headline"] = "Sync failed"
    run["duration_ms"] = int((time.time() - started) * 1000)
    run["id"] = persist.add_item("connection_sync", run)
    if pid in ("azure", "github") and live_drift():
        run["effects"].append(dict(label="Live drift updated", detail="Approved code from GitHub compared with deployed Azure resources", to="/connections"))
    old = [s for s in persist.list_items("connection_sync", 200) if s.get("platform") == pid][5:]
    for s in old:
        persist.delete_item("connection_sync", s["id"])
    return dict({k: v for k, v in run.items() if k != "components"}, connection=public(pid))


def latest(pid: str) -> dict:
    connector(pid)
    run = _latest_sync(pid, full=True)
    return dict(connection=public(pid), sync={k: v for k, v in run.items() if k != "components"} if run else None)


# ---------------------------------------------------------------- live drift
def live_drift() -> dict | None:
    az, gh = _latest_sync("azure", True), _latest_sync("github", True)
    if not (az and az.get("ok") and gh and gh.get("ok")):
        return None
    key = lambda c: str(c.get("name") or c.get("id") or "").lower()  # noqa: E731
    approved = {key(c): c for c in gh.get("components", [])}
    items, matched = [], 0
    for d in az.get("components", []):
        a = approved.get(key(d))
        if not a:
            continue
        matched += 1
        diffs = [dict(attribute=k, approved=a[k], deployed=d[k]) for k in sorted(set(a) & set(d) - DRIFT_IGNORE) if a[k] != d[k]]
        if diffs:
            items.append(dict(name=d.get("name") or d.get("id"), type=d.get("type"), changes=diffs))
    return dict(compared=matched, drifted=len(items), items=items[:100], deployed_total=len(az.get("components", [])), approved_total=len(gh.get("components", [])),
                at=max(az["at"], gh["at"]), mode="demo" if "demo" in (az.get("mode"), gh.get("mode")) else "live")
