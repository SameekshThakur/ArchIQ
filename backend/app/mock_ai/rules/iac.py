"""Read Azure Bicep files and ARM (JSON) templates into the same component model the standards checker uses.

This is a tolerant reader, not a compiler: it understands parameters, variables, objects, arrays, string literals and symbolic references,
which covers how infrastructure is normally written. Loops, conditions and modules are noted, never silently dropped.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.errors import BadRequest

PUBLIC_BY_DEFAULT = {"azure_openai", "storage_account", "key_vault", "sql_database", "postgres", "cosmos_db", "ai_search"}
DATA_STORES = {"storage_account", "sql_database", "postgres", "cosmos_db"}

ARM_TYPES = {
    "microsoft.keyvault/vaults": ("key_vault", None),
    "microsoft.storage/storageaccounts": ("storage_account", None),
    "microsoft.containerservice/managedclusters": ("aks_cluster", None),
    "microsoft.web/sites": ("app_service", None),
    "microsoft.dbforpostgresql/flexibleservers": ("postgres", "PostgreSQL 15"),
    "microsoft.documentdb/databaseaccounts": ("cosmos_db", "Cosmos DB"),
    "microsoft.sql/servers": ("sql_database", None),
    "microsoft.apimanagement/service": ("api_management", None),
    "microsoft.search/searchservices": ("ai_search", None),
}


class Ref(str):
    """An unresolved reference such as `storage.id` or `resourceGroup().location`."""


# ------------------------------------------------------------------ Bicep reader
class _Bicep:
    def __init__(self, text: str):
        self.s = self._strip(text)
        self.i = 0
        self.notes: list[str] = []

    @staticmethod
    def _strip(text: str) -> str:
        out, i, n, in_str = [], 0, len(text), False
        while i < n:
            ch = text[i]
            if in_str:
                out.append(ch)
                if ch == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 1
                elif ch == "'":
                    in_str = False
            elif ch == "'":
                in_str = True
                out.append(ch)
            elif text.startswith("//", i):
                while i < n and text[i] != "\n":
                    i += 1
                continue
            elif text.startswith("/*", i):
                j = text.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
            else:
                out.append(ch)
            i += 1
        return "".join(out)

    # -- value parsing
    def ws(self, newlines: bool = True) -> None:
        while self.i < len(self.s) and (self.s[self.i] in " \t\r" or (newlines and self.s[self.i] == "\n") or (newlines and self.s[self.i] == ",")):
            self.i += 1

    def value(self) -> Any:
        self.ws()
        s = self.s
        if self.i >= len(s):
            return None
        ch = s[self.i]
        if ch == "{":
            return self.obj()
        if ch == "[":
            return self.arr()
        if s.startswith("'''", self.i):
            j = s.find("'''", self.i + 3)
            v = s[self.i + 3: j if j >= 0 else len(s)]
            self.i = len(s) if j < 0 else j + 3
            return v
        if ch == "'":
            return self.string()
        m = re.match(r"-?\d+(?:\.\d+)?\b", s[self.i:])
        if m:
            self.i += m.end()
            return float(m.group()) if "." in m.group() else int(m.group())
        for lit, val in (("true", True), ("false", False), ("null", None)):
            if re.match(rf"{lit}\b", s[self.i:]):
                self.i += len(lit)
                return val
        return self.ref()

    def string(self) -> str:
        j, out = self.i + 1, []
        while j < len(self.s) and self.s[j] != "'":
            if self.s[j] == "\\" and j + 1 < len(self.s):
                j += 1
            out.append(self.s[j])
            j += 1
        self.i = j + 1
        return "".join(out)

    def ref(self) -> Ref:
        """Everything up to the end of the line or the next separator at depth 0 (handles calls like resourceId(...))."""
        start, depth, in_str = self.i, 0, False
        while self.i < len(self.s):
            ch = self.s[self.i]
            if ch == "'":
                in_str = not in_str
            elif not in_str:
                if ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    if depth == 0:
                        break
                    depth -= 1
                elif ch in "\n," and depth == 0:
                    break
            self.i += 1
        return Ref(self.s[start: self.i].strip())

    def obj(self) -> dict:
        self.i += 1
        out: dict[str, Any] = {}
        while True:
            self.ws()
            if self.i >= len(self.s):
                break
            if self.s[self.i] == "}":
                self.i += 1
                break
            if self.s[self.i] == "'":
                key = self.string()
            else:
                m = re.match(r"[\w.$-]+", self.s[self.i:])
                if not m:
                    self.i += 1
                    continue
                key = m.group()
                self.i += m.end()
            self.ws(newlines=False)
            if self.i < len(self.s) and self.s[self.i] == ":":
                self.i += 1
                out[key] = self.value()
        return out

    def arr(self) -> Any:
        if re.match(r"\[\s*for\b", self.s[self.i:]):
            self.notes.append("A loop ([for ...]) was found and is not expanded.")
            depth, in_str = 0, False
            while self.i < len(self.s):
                ch = self.s[self.i]
                if ch == "'":
                    in_str = not in_str
                elif not in_str:
                    depth += ch == "["
                    depth -= ch == "]"
                    if depth == 0:
                        self.i += 1
                        break
                self.i += 1
            return {"__loop__": True}
        self.i += 1
        out: list[Any] = []
        while True:
            self.ws()
            if self.i >= len(self.s):
                break
            if self.s[self.i] == "]":
                self.i += 1
                break
            out.append(self.value())
        return out

    # -- statements
    def parse(self) -> tuple[list[dict], dict[str, Any]]:
        env: dict[str, Any] = {}
        resources: list[dict] = []
        s = self.s
        while True:
            m = re.compile(r"^(param|var|resource|module)\s+(\w+)", re.M).search(s, self.i)
            if not m:
                break
            self.i = m.end()
            kind, name = m.group(1), m.group(2)
            if kind == "param":
                eq = s.find("=", self.i, s.find("\n", self.i) if s.find("\n", self.i) >= 0 else len(s))
                if eq >= 0:
                    self.i = eq + 1
                    env[name] = self.value()
            elif kind == "var":
                self.ws()
                if s.startswith("=", self.i):
                    self.i += 1
                    env[name] = self.value()
            elif kind == "module":
                self.notes.append(f"Module '{name}' was not analysed: its contents are not in this file.")
            else:
                t = re.compile(r"\s*'([^']+)'\s*(existing)?\s*=\s*").match(s, self.i)
                if not t:
                    continue
                self.i = t.end()
                if re.match(r"if\s*\(", s[self.i:]):
                    self.notes.append(f"Resource '{name}' is conditional and is analysed as if deployed.")
                    self.i = s.index("(", self.i)
                    depth = 0
                    while self.i < len(s):
                        depth += s[self.i] == "("
                        depth -= s[self.i] == ")"
                        self.i += 1
                        if depth == 0:
                            break
                body = self.value()
                if t.group(2) or not isinstance(body, dict) or body.get("__loop__"):
                    if isinstance(body, dict) and body.get("__loop__"):
                        self.notes.append(f"Resource '{name}' is declared in a loop and was skipped.")
                    continue
                resources.append(dict(sym=name, type=t.group(1).split("@")[0], body=body))
        return resources, env


def parse_bicep(text: str) -> dict:
    p = _Bicep(text)
    resources, env = p.parse()
    return _build("bicep", resources, env, p.notes, _title(text))


# ------------------------------------------------------------------ ARM reader
def _flatten(res: list[dict], parent_type: str = "", parent_name: str = "") -> list[dict]:
    out = []
    for r in res:
        if not isinstance(r, dict):
            continue
        rtype = r.get("type", "")
        full = rtype if "/" in rtype and not parent_type else (f"{parent_type}/{rtype}" if parent_type else rtype)
        name = str(r.get("name", ""))
        body = {k: v for k, v in r.items() if k not in ("resources", "type", "apiVersion", "name")}
        if parent_name:
            body.setdefault("scope", Ref(parent_name))
        out.append(dict(sym=name.split("/")[-1].strip("[]'() ") or name, type=full, body=body, name=name))
        out.extend(_flatten(r.get("resources", []) or [], full, name))
    return out


def parse_arm(data: dict) -> dict:
    env = {k: (v.get("defaultValue") if isinstance(v, dict) else v) for k, v in (data.get("parameters") or {}).items()}
    env.update({k: v for k, v in (data.get("variables") or {}).items()})
    res = data.get("resources") or []
    if isinstance(res, dict):  # languageVersion 2.0 templates use a symbolic-name object
        res = [dict(v, name=v.get("name", k)) for k, v in res.items()]
    return _build("arm", _flatten(res), env, [], "ARM template")


def _title(text: str) -> str:
    m = re.search(r"^\s*(?://|metadata\s+description\s*=\s*')\s*([^\n']{8,})", text, re.M)
    return (m.group(1).strip() if m else "Bicep template")[:80]


# ------------------------------------------------------------------ shared mapping
def _ci(d: Any, *path: str) -> Any:
    """Case-insensitive lookup through nested dicts."""
    for key in path:
        if not isinstance(d, dict):
            return None
        d = next((v for k, v in d.items() if k.lower() == key.lower()), None)
    return d


def _resolve(v: Any, env: dict[str, Any]) -> Any:
    if isinstance(v, str):
        m = re.fullmatch(r"\[?(?:parameters|variables)\('(\w+)'\)\]?", v.strip()) or (re.fullmatch(r"(\w+)", v.strip()) if isinstance(v, Ref) else None)
        if m and m.group(1) in env:
            return _resolve(env[m.group(1)], env) if env[m.group(1)] is not v else v
    return v


def _blob(v: Any) -> str:
    if isinstance(v, dict):
        return " ".join(f"{k} {_blob(x)}" for k, x in v.items())
    if isinstance(v, list):
        return " ".join(_blob(x) for x in v)
    return str(v)


def _find(v: Any, key: str) -> Any:
    if isinstance(v, dict):
        for k, x in v.items():
            if k.lower() == key.lower():
                return x
            r = _find(x, key)
            if r is not None:
                return r
    elif isinstance(v, list):
        for x in v:
            r = _find(x, key)
            if r is not None:
                return r
    return None


def _norm_region(v: Any) -> str | None:
    if not isinstance(v, str) or isinstance(v, Ref):
        return None
    r = re.sub(r"[\s_-]+", "", v).lower()
    return r or None


def tag_attrs(tags: dict | None) -> dict:
    keys = {str(k).lower().replace("_", "-") for k in (tags or {})}
    out = {"tags_complete": {"owner", "data-classification"} <= keys and bool({"cost-centre", "cost-center"} & keys)}
    for k, v in (tags or {}).items():
        if str(k).lower().replace("_", "-") == "data-classification" and isinstance(v, str):
            out["data_classification"] = v
    return out


def _tls(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    m = re.search(r"1[._]([0-3])", v)
    return f"1.{m.group(1)}" if m else None


def _build(fmt: str, resources: list[dict], env: dict[str, Any], notes: list[str], name: str) -> dict:
    rs = []
    for r in resources:
        b = r["body"]
        rs.append(dict(r, kind=_resolve(_ci(b, "kind"), env), props=_ci(b, "properties") if isinstance(_ci(b, "properties"), dict) else {}, loc=_resolve(_ci(b, "location"), env)))
    private_blob = " ".join(_blob(r["props"]) for r in rs if r["type"].lower() == "microsoft.network/privateendpoints")
    diag_blob = " ".join(_blob(r["body"]) + " " + str(r.get("name", "")) for r in rs if r["type"].lower().endswith("diagnosticsettings"))
    kids: dict[str, list] = {}
    for r in rs:
        par = _ci(r["body"], "parent") or _ci(r["body"], "scope")
        if par:
            kids.setdefault(str(par).split("/")[-1], []).append(r["props"])
    rai = any(r["type"].lower().endswith("/deployments") and _find(r["props"], "raiPolicyName") for r in rs)
    comps: list[dict] = []
    covered = {"microsoft.network/privateendpoints", "microsoft.resources/resourcegroups", "microsoft.cognitiveservices/accounts/deployments"}
    skipped: set[str] = set()
    for r in rs:
        t, props = r["type"].lower(), r["props"]
        if t == "microsoft.cognitiveservices/accounts":
            if str(r["kind"]).lower() != "openai":
                continue
            ctype, tech = "azure_openai", "Azure OpenAI"
        elif t == "microsoft.web/sites":
            ctype, tech = ("function", None) if "functionapp" in str(r["kind"]).lower() else ("app_service", None)
        elif t in ARM_TYPES:
            ctype, tech = ARM_TYPES[t]
        else:
            if not t.endswith("diagnosticsettings") and t not in covered and not t.startswith("microsoft.insights") and not t.startswith("microsoft.operationalinsights") and not t.startswith("microsoft.network") and not t.startswith("microsoft.managedidentity") and not t.startswith("microsoft.authorization"):
                skipped.add(r["type"])
            continue
        cid = r["sym"]
        c: dict[str, Any] = dict(id=cid, type=ctype, provisioned_by=fmt)
        if tech:
            c["technology"] = tech
        pna = _resolve(_ci(props, "publicNetworkAccess"), env)
        pub = None if pna is None else str(pna).lower() != "disabled"
        if pub is None and ctype in PUBLIC_BY_DEFAULT:
            pub = True
        if str(_ci(props, "networkAcls", "defaultAction")).lower() == "deny" and ctype in ("storage_account", "key_vault"):
            pub = False
        if pub is not None:
            c["public_network_access"] = pub
        if re.search(rf"\b{re.escape(cid)}\b", private_blob) or (r.get("name") and str(r["name"]) in private_blob):
            c["private_endpoint"] = True
        tls = _tls(_resolve(_ci(props, "minimumTlsVersion"), env) or _ci(props, "minimalTlsVersion") or _ci(props, "siteConfig", "minTlsVersion"))
        if tls:
            c["tls_min"] = tls
        elif ctype in ("key_vault", "storage_account"):
            c["tls_min"] = "1.2"
        if ctype in ("azure_openai", "ai_search", "cosmos_db"):
            c["auth"] = "managed_identity" if _resolve(_ci(props, "disableLocalAuth"), env) is True else "api_key"
        elif ctype == "storage_account":
            c["auth"] = "managed_identity" if _resolve(_ci(props, "allowSharedKeyAccess"), env) is False else "api_key"
        elif "assigned" in str(_ci(r["body"], "identity", "type")).lower():
            c["auth"] = "managed_identity"
        if ctype in ("app_service", "function"):
            settings = _ci(props, "siteConfig", "appSettings")
            blob = _blob(settings) if settings else ""
            if blob:
                if "@Microsoft.KeyVault(" in blob:
                    c["secrets_store"] = "key_vault"
                elif re.search(r"(KEY|SECRET|PASSWORD|CONNECTION)", blob, re.I):
                    c["secrets_store"] = "env_vars"
        region = _norm_region(_resolve(r["loc"], env))
        if region:
            c["region"] = region
        c.update(tag_attrs(_resolve(_ci(r["body"], "tags"), env) if isinstance(_resolve(_ci(r["body"], "tags"), env), dict) else None))
        if ctype in DATA_STORES:
            c["encryption_at_rest"] = True
        c["logging"] = bool(re.search(rf"\b{re.escape(cid)}\b", diag_blob))
        if ctype == "azure_openai" and rai:
            c["content_filter"] = "standard"
        family = [props, *kids.get(cid, []), *kids.get(str(r.get("name", "")), [])]  # e.g. blobServices settings live on a child resource
        ret = next((x for p in family for x in (_find(p, "softDeleteRetentionInDays"), _find(p, "backupRetentionDays"), _find(_find(p, "deleteRetentionPolicy") or {}, "days")) if x), None)
        if isinstance(ret, int):
            c["retention_days"] = ret
        comps.append(c)
    if skipped:
        s = sorted(skipped)
        notes.append(f"{len(s)} resource type(s) are not covered by the standards and were skipped: {', '.join(s[:5])}{'…' if len(s) > 5 else ''}.")
    if not comps and not rs:
        raise BadRequest("No Azure resources were found in this template")
    return dict(name=name, components=comps, format=fmt, nfr={}, notes=notes)
