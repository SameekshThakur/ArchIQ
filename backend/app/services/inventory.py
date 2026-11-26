"""Reconcile an uploaded CMDB / inventory export against the discovered estate (read-only: the estate is never modified)."""

from __future__ import annotations

import csv
import difflib
import io
import re

from app.core.errors import BadRequest
from app.repositories.store import get_store

MAX_ROWS = 5000
COLUMNS = {  # canonical field -> accepted header names (normalised: lowercase, non-alphanumerics removed)
    "name": ["name", "ciname", "applicationname", "application", "appname", "businessapplication", "ci"],
    "number": ["number", "ciid", "id", "assetid", "sysid"],
    "criticality": ["businesscriticality", "criticality", "bia", "businessimpact", "tier"],
    "owner": ["ownedby", "owner", "businessowner", "applicationowner", "manager"],
    "team": ["supportgroup", "team", "assignmentgroup", "supportteam"],
    "hosting": ["uhosting", "hosting", "hostingtype", "platform", "deployment", "hostingmodel"],
    "status": ["installstatus", "status", "lifecyclestatus", "operationalstatus", "state"],
    "domain": ["businessunit", "domain", "department", "businessdomain"],
}
_NOISE = re.compile(r"\b(the|app|application|system|platform|service|services)\b")


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def norm_name(s: str) -> str:
    s = re.sub(r"\(.*?\)", " ", s.lower())
    s = _NOISE.sub(" ", s.replace("&", " and "))
    return re.sub(r"[^a-z0-9]", "", s)


def norm_criticality(v: str) -> str | None:
    t = v.strip().lower()
    if not t:
        return None
    if re.search(r"critical|most|^1\b|tier ?1|p1", t):
        return "critical"
    if re.search(r"high|^2\b|tier ?2|p2", t):
        return "high"
    if re.search(r"med|moderate|^3\b|tier ?3|p3", t):
        return "medium"
    if re.search(r"low|^4\b|^5\b|tier ?[45]|p4", t):
        return "low"
    return None


def norm_hosting(v: str) -> str | None:
    t = v.strip().lower()
    if not t:
        return None
    if re.search(r"mainframe|z/?os", t):
        return "mainframe"
    if re.search(r"saas|vendor|third[- ]party", t):
        return "saas"
    if re.search(r"on[- ]?prem|data ?cent|dc\b|colo", t):
        return "on-prem"
    if re.search(r"azure|aks|cloud|aws|gcp", t):
        return "azure"
    return None


def _parse(text: str) -> tuple[list[dict], dict[str, str]]:
    """Workbooks with several sheets arrive as '## Sheet: name' blocks; use the first sheet that has an application-name column."""
    blocks = re.split(r"^## Sheet: (.+)$", text, flags=re.M)
    if len(blocks) > 1:
        tried: dict[str, list[str]] = {}
        for name, body in zip(blocks[1::2], blocks[2::2]):
            try:
                return _parse_csv(body.strip())
            except BadRequest as e:
                tried[name.strip()] = (e.details or {}).get("headers", []) if isinstance(e.details, dict) else []
        raise BadRequest("None of the sheets has an application name column", dict(sheets=tried, expected="one of: Name, CI Name, Application, Application Name"))
    return _parse_csv(text)


def _parse_csv(text: str) -> tuple[list[dict], dict[str, str]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise BadRequest("The file needs a header row and at least one data row")
    header = rows[0]
    keys = [_key(h) for h in header]
    mapping: dict[str, str] = {}
    for field, names in COLUMNS.items():
        for n in names:
            if n in keys:
                mapping[field] = header[keys.index(n)].strip()
                break
    if "name" not in mapping:
        raise BadRequest("Could not find an application name column", dict(headers=header, expected="one of: Name, CI Name, Application, Application Name"))
    idx = {f: keys.index(_key(h)) for f, h in mapping.items()}
    out = []
    for r in rows[1: MAX_ROWS + 1]:
        rec = {f: (r[i].strip() if i < len(r) else "") for f, i in idx.items()}
        if rec["name"]:
            out.append(rec)
    return out, mapping


def reconcile(filename: str, text: str) -> dict:
    s = get_store()
    rows, mapping = _parse(text)
    by_norm = {norm_name(a["name"]): a for a in s.apps}
    seen: set[str] = set()
    items: list[dict] = []
    for i, r in enumerate(rows, start=2):
        n = norm_name(r["name"])
        app, status, conf = by_norm.get(n), "matched", 1.0
        if app is None:
            best = max(by_norm, key=lambda k: difflib.SequenceMatcher(None, n, k).ratio(), default=None)
            score = difflib.SequenceMatcher(None, n, best).ratio() if best else 0
            if best and score >= 0.84:
                app, status, conf = by_norm[best], "probable", round(score, 2)
        retired = bool(re.search(r"retire|decom|disposed", r.get("status", ""), re.I))
        diffs: list[dict] = []
        if app:
            seen.add(app["id"])
            ec, ac = norm_criticality(r.get("criticality", "")), app["criticality"]
            if ec and ec != ac:
                diffs.append(dict(field="criticality", export=ec, estate=ac))
            eh, ah = norm_hosting(r.get("hosting", "")), app["hosting"]
            if eh and eh != ah:
                diffs.append(dict(field="hosting", export=eh, estate=ah))
            owner = s.owner(app["owner_id"])["name"] if app.get("owner_id") else ""
            if r.get("owner") and owner and _key(r["owner"]) != _key(owner):
                diffs.append(dict(field="owner", export=r["owner"], estate=owner))
            if retired and app["lifecycle"] not in ("retiring", "retired"):
                diffs.append(dict(field="status", export=r["status"], estate=app["lifecycle"]))
            if diffs and status == "matched":
                status = "conflict"
        else:
            status, conf = ("retired" if retired else "new"), 0.0
        items.append(dict(row=i, name=r["name"], number=r.get("number") or None, status=status, confidence=conf, asset_id=app["id"] if app else None, asset_name=app["name"] if app else None,
                          domain=r.get("domain") or (app["domain"] if app else None), owner=r.get("owner") or None, diffs=diffs))
    missing = [a for a in s.apps if a["id"] not in seen]
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    missing.sort(key=lambda a: (rank[a["criticality"]], a["name"]))
    count = lambda st: sum(1 for x in items if x["status"] == st)  # noqa: E731
    by_field: dict[str, int] = {}
    for x in items:
        for d in x["diffs"]:
            by_field[d["field"]] = by_field.get(d["field"], 0) + 1
    return dict(filename=filename, rows=len(items), columns=mapping, matched=count("matched"), conflicts=count("conflict"), probable=count("probable"), new=count("new"), retired=count("retired"),
                conflict_fields=by_field, items=items,
                missing=[dict(id=a["id"], name=a["name"], domain=a["domain"], criticality=a["criticality"], team=a["team"]) for a in missing], estate_total=len(s.apps))
