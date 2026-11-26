"""Standards compliance engine: parses a design (JSON, YAML or prose) and evaluates declarative rules."""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

from app.core.errors import BadRequest
from app.mock_ai.rules import iac
from app.repositories.store import get_store

# --------------------------------------------------------------------- parsing
KEYWORDS = [  # (regex, component type, technology)
    (r"azure openai|aoai", "azure_openai", "Azure OpenAI"),
    (r"openai\.com|chatgpt|public llm|anthropic api|external llm", "llm_api_external", "Public LLM API"),
    (r"key ?vault", "key_vault", None),
    (r"storage account|blob storage", "storage_account", None),
    (r"\baks\b|kubernetes", "aks_cluster", None),
    (r"app service|web app", "app_service", None),
    (r"azure functions?|function app", "function", None),
    (r"postgres(?:ql)?", "postgres", "PostgreSQL 15"),
    (r"cosmos", "cosmos_db", "Cosmos DB"),
    (r"oracle 12c", "sql_database", "Oracle 12c"),
    (r"sql server 2014", "sql_database", "SQL Server 2014"),
    (r"kafka|event hub", "kafka", "Apache Kafka"),
    (r"api management|apim|gateway", "api_management", None),
    (r"direct (?:db|database)", "integration", None),
    (r"data ?lake|adls", "data_lake", None),
    (r"windows server 2012", "vm", "Windows Server 2012"),
]


def _norm_component(c: dict, i: int) -> dict:
    c = dict(c)
    c.setdefault("id", f"c{i}")
    c.setdefault("type", "unknown")
    return c


def parse_design(raw: str | dict) -> dict:
    """Return {name, components, format}. Accepts JSON, YAML, or free text."""
    if isinstance(raw, dict):
        data, fmt = raw, "json"
    elif re.search(r'^\s*resource\s+"azurerm_', raw, re.M):
        return _parse_hcl(raw)
    elif re.search(r"^\s*resource\s+\w+\s+'Microsoft\.", raw, re.M):
        return iac.parse_bicep(raw)
    else:
        text = raw.strip()
        data, fmt = None, "text"
        try:
            data, fmt = json.loads(text), "json"
            if isinstance(data, dict) and "components" not in data and ("deploymentTemplate" in str(data.get("$schema", "")) or isinstance(data.get("resources"), (list, dict))) and "Microsoft." in text:
                return iac.parse_arm(data)
        except BadRequest:
            raise
        except Exception:
            try:
                y = yaml.safe_load(text)
                if isinstance(y, dict) and ("components" in y or "name" in y):
                    data, fmt = y, "yaml"
            except Exception:
                data = None
    if isinstance(data, dict) and isinstance(data.get("components"), list):
        comps = [_norm_component(c, i) for i, c in enumerate(data["components"]) if isinstance(c, dict)]
        return dict(name=data.get("name", "Untitled design"), components=comps, format=fmt, nfr=data.get("nfr", {}))
    return _parse_text(raw if isinstance(raw, str) else json.dumps(raw), fmt)


def _parse_text(text: str, fmt: str) -> dict:
    comps: list[dict] = []
    for ln in re.split(r"[\n.;]+", text):
        low = ln.lower().strip()
        if not low:
            continue
        hit = [(t, tech) for rx, t, tech in KEYWORDS if re.search(rx, low)]
        for t, tech in hit:
            c = next((x for x in comps if x["type"] == t and x.get("technology") == tech), None)
            if c is None:
                c = dict(id=f"{t}-{len(comps) + 1}", type=t)
                if tech:
                    c["technology"] = tech
                comps.append(c)
            if re.search(r"public (?:endpoint|network|access|internet)|internet[- ]facing endpoint|direct public", low):
                c["public_network_access"] = True
            if re.search(r"private (?:endpoint|link)|no public", low):
                c["public_network_access"] = False
                c["private_endpoint"] = True
            if "api key" in low or "api-key" in low:
                c["auth"] = "api_key"
            if "managed identity" in low:
                c["auth"] = "managed_identity"
            if re.search(r"tls 1\.0|tls1\.0", low):
                c["tls_min"] = "1.0"
            elif re.search(r"tls 1\.[23]", low):
                c["tls_min"] = "1.2"
            if "direct" in low and t == "integration":
                c["style"] = "direct_db"
            if "content filter" in low:
                c["content_filter"] = "standard"
            if "human" in low and ("review" in low or "approval" in low or "in the loop" in low):
                c["human_in_loop"] = True
    first = text.strip().splitlines()[0][:80] if text.strip() else "Untitled design"
    return dict(name=first, components=comps, format=fmt, nfr={})


# ---------------------------------------------------------------- Terraform
HCL_TYPES = {
    "azurerm_key_vault": ("key_vault", None),
    "azurerm_storage_account": ("storage_account", None),
    "azurerm_kubernetes_cluster": ("aks_cluster", None),
    "azurerm_linux_web_app": ("app_service", None),
    "azurerm_windows_web_app": ("app_service", None),
    "azurerm_app_service": ("app_service", None),
    "azurerm_linux_function_app": ("function", None),
    "azurerm_windows_function_app": ("function", None),
    "azurerm_postgresql_flexible_server": ("postgres", "PostgreSQL 15"),
    "azurerm_cosmosdb_account": ("cosmos_db", "Cosmos DB"),
    "azurerm_mssql_server": ("sql_database", None),
    "azurerm_api_management": ("api_management", None),
    "azurerm_search_service": ("ai_search", None),
}
# Azure leaves public network access ON unless it is explicitly disabled, so absence is a finding, not a pass.
PUBLIC_BY_DEFAULT = {"azure_openai", "storage_account", "key_vault", "sql_database", "postgres", "cosmos_db", "ai_search"}
DATA_STORES = {"storage_account", "sql_database", "postgres", "cosmos_db"}


def _blocks(text: str, head: re.Pattern) -> list[tuple[re.Match, str]]:
    """Return (header match, body) for each brace-delimited block, ignoring braces inside strings."""
    out = []
    for m in head.finditer(text):
        depth, i, in_str = 1, m.end(), False
        while i < len(text) and depth:
            ch = text[i]
            if ch == '"' and text[i - 1] != "\\":
                in_str = not in_str
            elif not in_str:
                depth += ch == "{"
                depth -= ch == "}"
            i += 1
        out.append((m, text[m.end(): i - 1]))
    return out


def _tf_value(body: str, *keys: str) -> str | None:
    for k in keys:
        m = re.search(rf'^\s*{k}\s*=\s*"?([^"\n#]+?)"?\s*(?:#.*)?$', body, re.M)
        if m:
            return m.group(1).strip()
    return None


def _tf_bool(body: str, *keys: str) -> bool | None:
    v = _tf_value(body, *keys)
    return None if v is None else v.lower() == "true"


def _strip_comments(text: str) -> str:
    """Remove #, // and /* */ comments without touching text inside strings."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif ch == "#" or text.startswith("//", i):
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


def _balanced(s: str, start: int, open_ch: str, close_ch: str) -> int:
    """Index just past the bracket that closes the one at s[start], ignoring strings."""
    depth, i, in_str = 0, start, False
    while i < len(s):
        ch = s[i]
        if ch == '"' and s[i - 1] != "\\":
            in_str = not in_str
        elif not in_str:
            depth += ch == open_ch
            depth -= ch == close_ch
            if depth == 0:
                return i + 1
        i += 1
    return len(s)


def _expr(body: str, key: str) -> str | None:
    """The right-hand side of `key = ...` (a map, a merge(...) call, a reference or a literal)."""
    m = re.search(rf"^\s*{key}\s*=\s*", body, re.M)
    if not m:
        return None
    rest = body[m.end():]
    if rest.startswith("{"):
        return rest[: _balanced(rest, 0, "{", "}")]
    mm = re.match(r"\w+\(", rest)
    if mm:
        return rest[: _balanced(rest, mm.end() - 1, "(", ")")]
    return rest.split("\n", 1)[0].strip()


def _split_args(s: str) -> list[str]:
    parts, depth, cur, in_str = [], 0, [], False
    for i, ch in enumerate(s):
        if ch == '"' and (i == 0 or s[i - 1] != "\\"):
            in_str = not in_str
        if not in_str:
            depth += ch in "({["
            depth -= ch in ")}]"
            if ch == "," and depth == 0:
                parts.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _eval_map(expr: str | None, locals_: dict[str, dict], var_maps: dict[str, dict]) -> dict[str, str] | None:
    """Evaluate the small subset of HCL used for tags: map literals, local.x, var.x and merge(...) of those."""
    if not expr:
        return None
    e = expr.strip()
    if e.startswith("merge("):
        out: dict[str, str] = {}
        for a in _split_args(e[len("merge("): -1]):
            out.update(_eval_map(a, locals_, var_maps) or {})
        return out
    m = re.match(r"local\.(\w+)", e)
    if m:
        return locals_.get(m.group(1), {})
    m = re.match(r"var\.(\w+)", e)
    if m:
        return var_maps.get(m.group(1), {})
    if e.startswith("{"):
        return dict(re.findall(r'"?([\w.-]+)"?\s*[=:]\s*"([^"]*)"', e[1:-1]))
    return None


def _tf_map(body: str, key: str, locals_: dict[str, dict], var_maps: dict[str, dict] | None = None) -> dict[str, str] | None:
    return _eval_map(_expr(body, key), locals_, var_maps or {})


def _norm_region(v: str | None, variables: dict[str, str]) -> str | None:
    if not v:
        return None
    m = re.match(r"var\.(\w+)", v)
    if m:
        v = variables.get(m.group(1), "")
    return re.sub(r"[\s_-]+", "", v).lower() or None


def _parse_hcl(raw_text: str) -> dict:
    text = _strip_comments(raw_text)
    notes: list[str] = []
    variables: dict[str, str] = {}
    var_maps: dict[str, dict] = {}
    for m, body in _blocks(text, re.compile(r'variable\s+"(\w+)"\s*\{')):
        d = _expr(body, "default")
        if d and d.startswith(("{", "merge(")):
            var_maps[m.group(1)] = _eval_map(d, {}, {}) or {}
        elif d:
            variables[m.group(1)] = d.strip().strip('"')
    # a variable's default stands in for the variable wherever it is used as a plain value
    text = re.sub(r"(?<=[=(,])\s*var\.(\w+)\b(?!\.)", lambda mo: f" {variables[mo.group(1)]}" if mo.group(1) in variables else mo.group(0), text)
    locals_: dict[str, dict] = {}
    for _, body in _blocks(text, re.compile(r"^locals\s*\{", re.M)):
        for name in re.findall(r"^\s*(\w+)\s*=", body, re.M):
            ev = _eval_map(_expr(body, name), locals_, var_maps)
            if ev is not None:
                locals_[name] = ev
    for m, _ in _blocks(text, re.compile(r'^module\s+"([\w-]+)"\s*\{', re.M)):
        notes.append(f"Module '{m.group(1)}' was not analysed: its contents are not in this file.")
    res = _blocks(text, re.compile(r'^resource\s+"(\w+)"\s+"([\w-]+)"\s*\{', re.M))
    rid = lambda m: f"{m.group(1)}.{m.group(2)}"  # noqa: E731
    private = {re.sub(r"\.id$", "", ref) for _, b in res for ref in re.findall(r"private_connection_resource_id\s*=\s*([\w.]+)", b)}
    diag = {re.sub(r"\.id$", "", ref) for _, b in res for ref in re.findall(r"target_resource_id\s*=\s*([\w.]+)", b)}
    locked = {re.sub(r"\.id$", "", ref) for m, b in res if m.group(1) == "azurerm_storage_account_network_rules" and re.search(r'default_action\s*=\s*"?Deny', b, re.I)
              for ref in re.findall(r"storage_account_id\s*=\s*([\w.]+)", b)}
    rai = any("rai_policy_name" in b for _, b in res)
    comps = []
    for m, body in res:
        rtype = m.group(1)
        if rtype == "azurerm_cognitive_account":
            if (_tf_value(body, "kind") or "").lower() != "openai":
                continue
            ctype, tech = "azure_openai", "Azure OpenAI"
        elif rtype in HCL_TYPES:
            ctype, tech = HCL_TYPES[rtype]
        else:
            continue
        c: dict = dict(id=m.group(2), type=ctype, provisioned_by="terraform")
        if tech:
            c["technology"] = tech
        pub = _tf_bool(body, "public_network_access_enabled")
        if pub is None:
            v = _tf_value(body, "public_network_access")
            pub = None if v is None else v.lower() == "enabled"
        if pub is None and ctype in PUBLIC_BY_DEFAULT:
            pub = True
        if rid(m) in locked:
            pub = False
        if pub is not None:
            c["public_network_access"] = pub
        if rid(m) in private:
            c["private_endpoint"] = True
        tls = _tf_value(body, "min_tls_version", "minimum_tls_version", "min_tls_version")
        if tls:
            mt = re.search(r"1[._]([0-3])", tls)
            c["tls_min"] = f"1.{mt.group(1)}" if mt else tls
        elif ctype in ("key_vault", "storage_account"):
            c["tls_min"] = "1.2"  # platform minimum
        if ctype in ("azure_openai", "ai_search", "cosmos_db", "storage_account"):
            local_auth = _tf_bool(body, "local_authentication_enabled", "local_auth_enabled", "shared_access_key_enabled", "local_authentication_disabled")
            disabled_key = bool(re.search(r"local_authentication_disabled\s*=\s*true", body))
            c["auth"] = "managed_identity" if (local_auth is False or disabled_key) else "api_key"
        elif re.search(r"identity\s*\{[^}]*type\s*=\s*\"[^\"]*Assigned", body):
            c["auth"] = "managed_identity"
        settings = "".join(b for _, b in _blocks(body, re.compile(r"app_settings\s*=\s*\{")))
        if ctype in ("app_service", "function") and settings:
            c["secrets_store"] = "key_vault" if "@Microsoft.KeyVault(" in settings else ("env_vars" if re.search(r"(KEY|SECRET|PASSWORD|CONNECTION)", settings, re.I) else None)
            if c["secrets_store"] is None:
                del c["secrets_store"]
        region = _norm_region(_tf_value(body, "location"), variables)
        if region:
            c["region"] = region
        tags = _tf_map(body, "tags", locals_, var_maps)
        keys = {k.lower().replace("_", "-") for k in (tags or {})}
        c["tags_complete"] = {"owner", "cost-centre", "cost-center", "data-classification"} & keys >= {"owner", "data-classification"} and bool({"cost-centre", "cost-center"} & keys)
        if tags and ("data_classification" in tags or "data-classification" in tags):
            c["data_classification"] = tags.get("data_classification") or tags.get("data-classification")
        if ctype in DATA_STORES:
            c["encryption_at_rest"] = True  # Azure encrypts data at rest by default
        if ctype in ("azure_openai", "storage_account", "key_vault", "sql_database", "postgres", "cosmos_db", "ai_search", "app_service", "aks_cluster", "function"):
            c["logging"] = rid(m) in diag
        if ctype == "azure_openai" and rai:
            c["content_filter"] = "standard"
        ret = _tf_value(body, "soft_delete_retention_days", "retention_days", "backup_retention_days")
        if not ret:
            dm = re.search(r"delete_retention_policy\s*\{[^}]*?\bdays\s*=\s*(\d+)", body)
            ret = dm.group(1) if dm else None
        if ret and ret.isdigit():
            c["retention_days"] = int(ret)
        if re.search(r"^\s*(count|for_each)\s*=", body, re.M):
            notes.append(f"{rid(m)} uses count or for_each and is analysed as a single instance.")
        comps.append(c)
    first = next((ln.lstrip("#/ ").strip() for ln in raw_text.splitlines() if ln.strip().startswith(("#", "//")) and len(ln.strip("#/ ")) > 8), "Terraform configuration")
    skipped = sorted({m.group(1) for m, _ in res if m.group(1).startswith("azurerm_") and m.group(1) not in HCL_TYPES and m.group(1) != "azurerm_cognitive_account"})
    known_other = {"azurerm_resource_group", "azurerm_private_endpoint", "azurerm_monitor_diagnostic_setting", "azurerm_cognitive_deployment", "azurerm_storage_account_network_rules", "azurerm_service_plan", "azurerm_log_analytics_workspace",
                   "azurerm_subnet", "azurerm_virtual_network", "azurerm_user_assigned_identity", "azurerm_role_assignment"}
    extra = [s for s in skipped if s not in known_other]
    if extra:
        notes.append(f"{len(extra)} resource type(s) are not covered by the standards and were skipped: {', '.join(extra[:6])}{'…' if len(extra) > 6 else ''}.")
    return dict(name=first[:80], components=comps, format="terraform", nfr={}, notes=notes)


# ------------------------------------------------------------------ evaluation
def _cond(c: dict, rule: dict | None) -> bool:
    if not rule:
        return True
    v = c.get(rule["attr"])
    return _op(rule["op"], v, rule.get("value"))[0]


def _op(op: str, v: Any, expected: Any) -> tuple[bool, bool]:
    """returns (ok, evidenced)"""
    if op == "present":
        return v not in (None, "", []), True
    if v is None:
        return False, False
    if op == "eq":
        return v == expected, True
    if op == "ne":
        return v != expected, True
    if op == "in":
        return v in expected, True
    if op == "not_in":
        return v not in expected, True
    if op == "gte":
        try:
            return float(v) >= float(expected), True
        except (TypeError, ValueError):
            return False, True
    if op == "lte":
        try:
            return float(v) <= float(expected), True
        except (TypeError, ValueError):
            return False, True
    return True, True


def _fmt(v: Any) -> str:
    return "enabled" if v is True else "disabled" if v is False else str(v)


def check_design(design: dict, only: list[str] | None = None) -> dict:
    s = get_store()
    comps = design["components"]
    results: list[dict] = []
    for std in s.standards:
        if only and std["id"] not in only:
            continue
        if std["kind"] == "approved_technology":
            matched = [c for c in comps if (c.get("technology") or "").lower() == std["technology"].lower()]
            for c in matched:
                st = std["status"]
                status = {"approved": "pass", "deprecated": "warn", "prohibited": "fail"}[st]
                msg = {"approved": f"{std['technology']} is approved.", "deprecated": f"{std['technology']} is deprecated and tolerated for existing systems only.",
                       "prohibited": f"{std['technology']} is prohibited for use in this design."}[st]
                results.append(dict(standard_id=std["id"], title=std["title"], category=std["category"], kind=std["kind"], severity=std["severity"],
                                    status=status, components=[c["id"]], rationale=msg, remediation=std["statement"] if status != "pass" else "", statement=std["statement"]))
            continue
        chk = std.get("check")
        if not chk:
            continue
        applicable = [c for c in comps if c["type"] in std["applies_to"] and _cond(c, std.get("when"))]
        if not applicable:
            continue
        fails, warns, oks = [], [], []
        for c in applicable:
            if chk["attr"] == "never":
                fails.append(c)
                continue
            ok, evidenced = _op(chk["op"], c.get(chk["attr"]), chk.get("value"))
            (oks if ok else (fails if evidenced else warns)).append(c)
        status = "fail" if fails else "warn" if warns else "pass"
        bad = fails or warns
        parts = []
        for c in bad:
            if chk["attr"] == "never":
                parts.append(f"{c['id']} is an external public LLM endpoint")
            elif c in warns:
                parts.append(f"{c['id']} ({c['type']}): '{chk['attr']}' is not specified in the design")
            else:
                parts.append(f"{c['id']} ({c['type']}) has {chk['attr']} = {_fmt(c.get(chk['attr']))}")
        rationale = "; ".join(parts) if parts else f"All {len(applicable)} applicable component(s) comply."
        if std["id"] == "STD-SEC-014" and fails:
            if any(c["type"] == "azure_openai" for c in fails):
                rationale = "Azure OpenAI is approved; direct public endpoint violates policy. " + rationale
        results.append(dict(standard_id=std["id"], title=std["title"], category=std["category"], kind=std["kind"], severity=std["severity"], status=status,
                            components=[c["id"] for c in (bad or applicable)], rationale=rationale, remediation=std["remediation"] if bad else "", statement=std["statement"]))
    order = {"fail": 0, "warn": 1, "pass": 2}
    sev = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    results.sort(key=lambda r: (order[r["status"]], sev.get(r["severity"], 5), r["standard_id"]))
    p = sum(r["status"] == "pass" for r in results)
    w = sum(r["status"] == "warn" for r in results)
    f = sum(r["status"] == "fail" for r in results)
    score = round(100 * (p + 0.5 * w) / (p + w + f)) if (p + w + f) else 100

    aoai = [c for c in comps if c["type"] == "azure_openai"]
    if aoai and any(c.get("public_network_access") is True for c in aoai):
        headline = "Azure OpenAI is approved; direct public endpoint violates policy."
    elif aoai:
        headline = "Azure OpenAI is approved and the design reaches it privately, in line with policy."
    elif f:
        headline = f"{f} standard{'s' if f != 1 else ''} violated across {len(comps)} components."
    else:
        headline = "The design complies with all applicable standards."
    return dict(design_name=design["name"], format=design["format"], components=len(comps), results=results, passed=p, warned=w, failed=f,
                score=score, headline=headline, notes=design.get("notes", []))
