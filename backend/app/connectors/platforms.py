"""The six platform connectors. Each has a real read-only `fetch` and a `demo` built from the sample estate."""

from __future__ import annotations

import base64
import re
from pathlib import PurePosixPath
from urllib.parse import quote, urlparse


from app.connectors.base import Connector, ConnectorError, FieldSpec, SyncData, base_url, call, csv_list, entra_token, get_json, secret
from app.repositories.store import get_store

MAX_RECORDS = 5000


def _basic(user: str, token: str) -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()}


def _auth(email: str, token: str) -> dict[str, str]:
    """Atlassian cloud uses email + API token (basic); Data Center uses a personal access token (bearer)."""
    return _basic(email, token) if email else {"Authorization": f"Bearer {token}"}


def _need(cfg: dict, *keys: str) -> None:
    missing = [k for k in keys if not (cfg.get(k) or "").strip()]
    if missing:
        raise ConnectorError("Missing: " + ", ".join(missing).replace("_", " "))


# ================================================================ ServiceNow
class ServiceNow(Connector):
    id = "servicenow"
    name = "ServiceNow CMDB"
    vendor = "ServiceNow"
    category = "cmdb"
    description = "Business applications, owners, criticality and lifecycle from the CMDB."
    provides = ["Application inventory reconciled against the estate (Discovery)"]
    fields = [
        FieldSpec("instance_url", "Instance URL", "url", placeholder="https://yourcompany.service-now.com"),
        FieldSpec("username", "Username", required=False, help="Basic authentication. Leave empty when using an OAuth token."),
        FieldSpec("password", "Password", "secret", required=False),
        FieldSpec("token", "OAuth access token", "secret", required=False, help="Instead of username and password."),
        FieldSpec("table", "Table", default="cmdb_ci_business_app", help="cmdb_ci_business_app or cmdb_ci_appl"),
        FieldSpec("query", "Filter (encoded query)", required=False, placeholder="operational_status=1", help="Optional sysparm_query."),
    ]
    setup = ["A read-only integration user with the itil or cmdb_read role", "REST API access to the chosen CMDB table"]
    FIELDS = "sys_id,name,number,owned_by,business_criticality,install_status,operational_status,support_group,business_unit,u_hosting,hosting_type"

    def _headers(self, cfg: dict) -> dict:
        if cfg.get("token"):
            return {"Authorization": f"Bearer {secret(cfg['token'])}"}
        _need(cfg, "username", "password")
        return _basic(cfg["username"], secret(cfg["password"]))

    def _url(self, cfg: dict) -> str:
        return base_url(cfg.get("instance_url", ""), "Instance URL") + f"/api/now/table/{quote(cfg.get('table') or 'cmdb_ci_business_app')}"

    def test(self, cfg, http):
        get_json(http, self._url(cfg), "ServiceNow", params=dict(sysparm_limit=1, sysparm_fields="sys_id"), headers=self._headers(cfg))
        return f"Read access to {cfg.get('table') or 'cmdb_ci_business_app'} confirmed."

    def fetch(self, cfg, http):
        url, headers, rows, offset = self._url(cfg), self._headers(cfg), [], 0
        while len(rows) < MAX_RECORDS:
            params = dict(sysparm_limit=500, sysparm_offset=offset, sysparm_fields=self.FIELDS, sysparm_display_value="true", sysparm_exclude_reference_link="true")
            if cfg.get("query"):
                params["sysparm_query"] = cfg["query"]
            page = get_json(http, url, "ServiceNow", params=params, headers=headers).get("result", [])
            rows += page
            if len(page) < 500:
                break
            offset += 500
        recs = [dict(name=r.get("name") or "", number=r.get("number") or r.get("sys_id") or "", owner=_dv(r.get("owned_by")), criticality=_dv(r.get("business_criticality")),
                     team=_dv(r.get("support_group")), status=_dv(r.get("install_status") or r.get("operational_status")), domain=_dv(r.get("business_unit")),
                     hosting=_dv(r.get("u_hosting") or r.get("hosting_type"))) for r in rows]
        recs = [r for r in recs if r["name"]]
        return SyncData(records=recs, cmdb_rows=recs, meta=dict(table=cfg.get("table") or "cmdb_ci_business_app"))

    def demo(self):
        s = get_store()
        recs = []
        for i, a in enumerate(s.apps[:60]):
            crit = a["criticality"] if i % 11 else {"critical": "high", "high": "medium", "medium": "low", "low": "medium"}[a["criticality"]]
            recs.append(dict(name=a["name"], number=f"APM{1001 + i}", owner=s.owner(a["owner_id"])["name"] if a.get("owner_id") else "", criticality=crit, team=a.get("team", ""),
                             status="Retired" if i == 17 else "Installed", domain=a["domain"], hosting=a["hosting"] if i % 13 else "On-premises"))
        for j, n in enumerate(["Broker Commission Portal", "Fraud Analytics Sandbox", "Legacy Fax Gateway"]):
            recs.append(dict(name=n, number=f"APM{1101 + j}", owner="", criticality="low", team="", status="Installed", domain="", hosting=""))
        return SyncData(records=recs, cmdb_rows=recs, meta=dict(table="cmdb_ci_business_app (demo)"))


def _dv(v) -> str:
    if isinstance(v, dict):
        return str(v.get("display_value") or v.get("value") or "")
    return str(v or "")


# ================================================================ Jira
class Jira(Connector):
    id = "jira"
    name = "Jira"
    vendor = "Atlassian"
    category = "work"
    description = "Architecture work items, linked to the applications they mention."
    provides = ["Open work per application", "Delivery status next to review findings"]
    fields = [
        FieldSpec("site_url", "Site URL", "url", placeholder="https://yourcompany.atlassian.net"),
        FieldSpec("email", "Account email", required=False, help="Jira Cloud. Leave empty for Data Center with a personal access token."),
        FieldSpec("api_token", "API token", "secret"),
        FieldSpec("projects", "Project keys", placeholder="ARCH, CLM", help="Comma-separated."),
        FieldSpec("jql", "JQL override", required=False, placeholder="project = ARCH AND updated >= -90d"),
    ]
    setup = ["An account (or service account) with Browse projects permission", "An API token (Cloud) or personal access token (Data Center)"]
    FIELDS = "summary,status,issuetype,priority,components,labels,updated,project"

    def _site(self, cfg):
        return base_url(cfg.get("site_url", ""), "Site URL")

    def _headers(self, cfg):
        _need(cfg, "api_token")
        return _auth(cfg.get("email", "").strip(), secret(cfg["api_token"]))

    def _jql(self, cfg):
        if cfg.get("jql"):
            return cfg["jql"]
        keys = csv_list(cfg.get("projects", ""))
        if not keys:
            raise ConnectorError("Give at least one project key, or a JQL query.")
        return f"project in ({', '.join(keys)}) ORDER BY updated DESC"

    def test(self, cfg, http):
        site, h = self._site(cfg), self._headers(cfg)
        try:
            me = get_json(http, f"{site}/rest/api/3/myself", "Jira", headers=h)
        except ConnectorError as e:
            if "404" not in str(e):
                raise
            me = get_json(http, f"{site}/rest/api/2/myself", "Jira", headers=h)
        return f"Signed in as {me.get('displayName') or me.get('name') or 'the configured account'}."

    def fetch(self, cfg, http):
        site, h, jql, issues = self._site(cfg), self._headers(cfg), self._jql(cfg), []
        token = None
        try:  # Jira Cloud: the enhanced search endpoint with a page token
            while len(issues) < 1000:
                params = dict(jql=jql, fields=self.FIELDS, maxResults=100)
                if token:
                    params["nextPageToken"] = token
                j = get_json(http, f"{site}/rest/api/3/search/jql", "Jira search", params=params, headers=h)
                issues += j.get("issues", [])
                token = j.get("nextPageToken")
                if not token or j.get("isLast"):
                    break
        except ConnectorError as e:  # Data Center / Server: the classic search
            if "404" not in str(e) and "410" not in str(e):
                raise
            start = 0
            while len(issues) < 1000:
                j = get_json(http, f"{site}/rest/api/2/search", "Jira search", params=dict(jql=jql, fields=self.FIELDS, maxResults=100, startAt=start), headers=h)
                issues += j.get("issues", [])
                start += 100
                if start >= j.get("total", 0):
                    break
        recs = []
        for it in issues:
            f = it.get("fields", {})
            st = f.get("status") or {}
            recs.append(dict(key=it.get("key"), summary=f.get("summary") or "", status=st.get("name") or "", category=(st.get("statusCategory") or {}).get("key", ""),
                             type=(f.get("issuetype") or {}).get("name", ""), priority=(f.get("priority") or {}).get("name", ""),
                             components=[c.get("name", "") for c in f.get("components") or []], labels=f.get("labels") or [],
                             project=(f.get("project") or {}).get("key", ""), updated=(f.get("updated") or "")[:10], url=f"{site}/browse/{it.get('key')}"))
        return SyncData(records=recs, work_items=recs, meta=dict(jql=jql))

    def demo(self):
        s = get_store()
        tpl = [("Move {a} behind the API gateway", "In Progress", "indeterminate", "Story"), ("Document recovery targets for {a}", "To Do", "new", "Task"),
               ("Raise minimum TLS to 1.2 on {a}", "Done", "done", "Task"), ("Remove direct database access from {a}", "To Do", "new", "Story"),
               ("ARB conditions follow-up: {a}", "In Progress", "indeterminate", "Task")]
        apps = sorted(s.apps, key=lambda a: -a.get("debt", 0))[:14]
        recs = []
        for i, a in enumerate(apps):
            for k in range(1 + i % 2):
                t = tpl[(i + k) % len(tpl)]
                recs.append(dict(key=f"ARCH-{101 + len(recs)}", summary=t[0].format(a=a["name"]), status=t[1], category=t[2], type=t[3], priority=["High", "Medium", "Low"][(i + k) % 3],
                                 components=[a["domain"]], labels=["architecture"], project="ARCH", updated="2026-11-0" + str(1 + (i % 9)), url=""))
        return SyncData(records=recs, work_items=recs, meta=dict(jql="project = ARCH (demo)"))


# ================================================================ Azure
class Azure(Connector):
    id = "azure"
    name = "Azure Resource Graph"
    vendor = "Microsoft"
    category = "cloud"
    description = "Deployed cloud resources and their security settings across subscriptions."
    provides = ["Live standards checks on deployed resources", "Live drift against Terraform from GitHub"]
    fields = [
        FieldSpec("tenant_id", "Tenant ID", placeholder="00000000-0000-0000-0000-000000000000"),
        FieldSpec("client_id", "Client (application) ID"),
        FieldSpec("client_secret", "Client secret", "secret"),
        FieldSpec("subscriptions", "Subscription IDs", "textarea", help="Comma-separated."),
        FieldSpec("query", "Resource Graph query", "textarea", required=False, placeholder="Resources | where resourceGroup startswith 'rg-claims'",
                  help="Optional. The default reads every resource, up to 5,000."),
    ]
    setup = ["An app registration (service principal) with a client secret", "The Reader role on each subscription"]
    MGMT = "https://management.azure.com"

    def _token(self, cfg, http):
        return entra_token(http, cfg.get("tenant_id", "").strip(), cfg.get("client_id", "").strip(), secret(cfg.get("client_secret", "")), f"{self.MGMT}/.default")

    def test(self, cfg, http):
        subs = csv_list(cfg.get("subscriptions", ""))
        if not subs:
            raise ConnectorError("Give at least one subscription ID.")
        h = {"Authorization": f"Bearer {self._token(cfg, http)}"}
        names = [get_json(http, f"{self.MGMT}/subscriptions/{quote(s)}", "Azure subscription", params={"api-version": "2022-12-01"}, headers=h).get("displayName", s) for s in subs[:5]]
        return f"Reader access confirmed on {', '.join(names)}."

    def fetch(self, cfg, http):
        subs = csv_list(cfg.get("subscriptions", ""))
        if not subs:
            raise ConnectorError("Give at least one subscription ID.")
        h = {"Authorization": f"Bearer {self._token(cfg, http)}"}
        q = (cfg.get("query") or "Resources").strip()
        q += " | project id, name, type, location, resourceGroup, subscriptionId, kind, sku, tags, properties"
        rows, skip = [], None
        while len(rows) < MAX_RECORDS:
            body: dict = dict(subscriptions=subs, query=q, options={"$top": 1000, "resultFormat": "objectArray"})
            if skip:
                body["options"]["$skipToken"] = skip
            r = call(http, "POST", f"{self.MGMT}/providers/Microsoft.ResourceGraph/resources", "Azure Resource Graph", params={"api-version": "2022-10-01"}, headers=h, json=body).json()
            rows += r.get("data", [])
            skip = r.get("$skipToken")
            if not skip:
                break
        from app.mock_ai.rules import iac

        tpl = {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
               "resources": [dict(type=x.get("type"), name=x.get("name"), location=x.get("location"), kind=x.get("kind"), sku=x.get("sku"), tags=x.get("tags"), properties=x.get("properties") or {}) for x in rows]}
        comps = iac.parse_arm(tpl)["components"] if rows else []
        recs = [dict(name=x.get("name"), type=x.get("type"), location=x.get("location"), resource_group=x.get("resourceGroup"), subscription=x.get("subscriptionId"),
                     public_network_access=(x.get("properties") or {}).get("publicNetworkAccess")) for x in rows]
        return SyncData(records=recs, components=comps, meta=dict(subscriptions=len(subs), query=q))

    def demo(self):
        s = get_store()
        res = [r for r in s.cloud if r["provider"] == "azure"][:150]
        comps = [dict(id=r["id"], name=r["name"], type=r["type"], region=r["region"], **r["deployed"]) for r in res]
        recs = [dict(name=r["name"], type=r["type"], location=r["region"], resource_group=r["resource_group"], subscription=r["subscription"],
                     public_network_access=r["deployed"].get("public_network_access")) for r in res]
        return SyncData(records=recs, components=comps, meta=dict(subscriptions=len({r["subscription"] for r in res}), query="Resources (demo)"))


# ================================================================ GitHub
IAC_EXT = {".tf", ".bicep"}
DOC_RE = re.compile(r"(^|/)(docs?|adr|adrs|architecture|decisions)/.*\.md$|^readme\.md$", re.I)


class GitHub(Connector):
    id = "github"
    name = "GitHub"
    vendor = "GitHub"
    category = "code"
    description = "Approved infrastructure code (Terraform, Bicep) and architecture decision records from repositories."
    provides = ["Standards checks on infrastructure code", "ADRs and docs into Document intelligence", "Approved side of live drift"]
    fields = [
        FieldSpec("api_url", "API URL", "url", default="https://api.github.com", help="GitHub Enterprise Server: https://<host>/api/v3"),
        FieldSpec("token", "Access token", "secret", help="Fine-grained token with read access to contents."),
        FieldSpec("repositories", "Repositories", "textarea", placeholder="org/infra-claims, org/architecture-decisions", help="owner/repo, comma-separated."),
        FieldSpec("branch", "Branch", required=False, help="Default branch when empty."),
    ]
    setup = ["A fine-grained personal access token or GitHub App with Contents: read", "Access to each listed repository"]

    def _h(self, cfg):
        _need(cfg, "token")
        return {"Authorization": f"Bearer {secret(cfg['token'])}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    def _repos(self, cfg):
        repos = csv_list(cfg.get("repositories", ""))
        if not repos or any(r.count("/") != 1 for r in repos):
            raise ConnectorError("List repositories as owner/repo, separated by commas.")
        return repos

    def test(self, cfg, http):
        api, h = base_url(cfg.get("api_url") or "https://api.github.com", "API URL"), self._h(cfg)
        names = [get_json(http, f"{api}/repos/{r}", f"GitHub {r}", headers=h)["full_name"] for r in self._repos(cfg)[:5]]
        return f"Read access confirmed on {', '.join(names)}."

    def fetch(self, cfg, http):
        api, h = base_url(cfg.get("api_url") or "https://api.github.com", "API URL"), self._h(cfg)
        recs, docs, comps = [], [], []
        from app.mock_ai.rules import standards

        for repo in self._repos(cfg):
            meta = get_json(http, f"{api}/repos/{repo}", f"GitHub {repo}", headers=h)
            branch = cfg.get("branch") or meta.get("default_branch") or "main"
            tree = get_json(http, f"{api}/repos/{repo}/git/trees/{quote(branch)}", f"GitHub {repo} file list", params=dict(recursive=1), headers=h).get("tree", [])
            files = [t for t in tree if t.get("type") == "blob" and (t.get("size") or 0) <= 200_000 and "/.terraform/" not in "/" + t["path"]]
            iac_files = [t for t in files if PurePosixPath(t["path"]).suffix.lower() in IAC_EXT][:40]
            doc_files = [t for t in files if DOC_RE.search(t["path"])][:20]
            raw = dict(h, Accept="application/vnd.github.raw")
            by_dir: dict[str, list[str]] = {}
            for t in iac_files:
                text = call(http, "GET", f"{api}/repos/{repo}/contents/{quote(t['path'])}", f"GitHub {t['path']}", params=dict(ref=branch), headers=raw).text
                key = t["path"] if t["path"].endswith(".bicep") else str(PurePosixPath(t["path"]).parent)
                by_dir.setdefault(key, []).append(text)
                recs.append(dict(repository=repo, path=t["path"], kind="infrastructure code", size=t.get("size")))
            for key, texts in by_dir.items():
                try:
                    d = standards.parse_design("\n\n".join(texts))
                    comps += [dict(c, source=f"{repo}/{key}") for c in d["components"]]
                except Exception:  # an unparseable module is listed, not fatal
                    continue
            for t in doc_files:
                text = call(http, "GET", f"{api}/repos/{repo}/contents/{quote(t['path'])}", f"GitHub {t['path']}", params=dict(ref=branch), headers=raw).text
                if len(text.strip()) >= 40:
                    docs.append(dict(title=f"{repo.split('/')[1]}: {PurePosixPath(t['path']).stem.replace('-', ' ').replace('_', ' ')}"[:200], text=text, doc_type="ADR" if "adr" in t["path"].lower() or "decision" in t["path"].lower() else "Confluence", url=""))
                recs.append(dict(repository=repo, path=t["path"], kind="document", size=t.get("size")))
        return SyncData(records=recs, documents=docs, components=comps, meta=dict(repositories=len(self._repos(cfg))))

    def demo(self):
        from app.mock_ai.rules import drift

        s = get_store()
        res = [r for r in s.cloud if r["provider"] == "azure"][:150]
        comps, recs = [], []
        for r in res:
            comps.append(dict(id=r["id"], name=r["name"], type=r["type"], region=r["region"], source=f"northwind/infra-{r['domain'].split()[0].lower()}", **r["approved"]))
        groups = sorted({r["resource_group"] for r in res})
        for g in groups:
            recs.append(dict(repository="northwind/infrastructure", path=f"envs/prod/{g}/main.tf", kind="infrastructure code", size=None))
        sample = res[0]
        docs = [dict(title="architecture-decisions: 0007 private endpoints for AI services", doc_type="ADR", url="",
                     text=f"# ADR-0007: Private endpoints for AI services\n\nStatus: Accepted\n\n## Context\nAI services such as {sample['name']} process confidential claim data.\n\n## Decision\nAll Azure OpenAI and storage accounts are reached only through private endpoints. Public network access is disabled. Minimum TLS is 1.2.\n\n## Consequences\nApplications call AI services from inside the virtual network. Exceptions need design-authority approval.\n\n```hcl\n{drift.render_hcl(sample, sample['approved'])}\n```"),
                dict(title="architecture-decisions: 0011 events over direct database access", doc_type="ADR", url="",
                     text="# ADR-0011: Events instead of direct database access\n\nStatus: Accepted\n\n## Context\nSeveral claims applications read the Policy Master DB directly, coupling them to its schema.\n\n## Decision\nNew consumers subscribe to policy events on the Kafka Event Platform or call the Customer API. No new direct database integrations are approved.\n\n## Consequences\nExisting direct integrations are moved in modernization wave 2.")]
        recs += [dict(repository="northwind/architecture-decisions", path=f"docs/adr/{d['title'].split(': ')[1][:4]}.md", kind="document", size=None) for d in docs]
        return SyncData(records=recs, documents=docs, components=comps, meta=dict(repositories=2))


# ================================================================ Confluence
class Confluence(Connector):
    id = "confluence"
    name = "Confluence"
    vendor = "Atlassian"
    category = "docs"
    description = "Architecture pages: designs, standards and decisions, read into Document intelligence."
    provides = ["Pages analysed for components, gaps and conflicts (Documents)"]
    fields = [
        FieldSpec("base_url", "Confluence URL", "url", placeholder="https://yourcompany.atlassian.net/wiki"),
        FieldSpec("email", "Account email", required=False, help="Confluence Cloud. Leave empty for Data Center with a personal access token."),
        FieldSpec("api_token", "API token", "secret"),
        FieldSpec("spaces", "Space keys", placeholder="ARCH, EA", help="Comma-separated."),
        FieldSpec("max_pages", "Maximum pages", required=False, default="25"),
    ]
    setup = ["An account with view access to the listed spaces", "An API token (Cloud) or personal access token (Data Center)"]

    def _base(self, cfg):
        return base_url(cfg.get("base_url", ""), "Confluence URL")

    def _h(self, cfg):
        _need(cfg, "api_token")
        return _auth(cfg.get("email", "").strip(), secret(cfg["api_token"]))

    def test(self, cfg, http):
        j = get_json(http, f"{self._base(cfg)}/rest/api/space", "Confluence", params=dict(limit=5), headers=self._h(cfg))
        return f"Read access confirmed ({len(j.get('results', []))} spaces visible)."

    def fetch(self, cfg, http):
        from app.services.files import _html

        spaces = csv_list(cfg.get("spaces", ""))
        if not spaces:
            raise ConnectorError("Give at least one space key.")
        cap = max(1, min(int(cfg.get("max_pages") or 25), 200))
        cql = "type=page AND space in (" + ",".join(f'"{s}"' for s in spaces) + ") ORDER BY lastmodified DESC"
        base, h, pages, start = self._base(cfg), self._h(cfg), [], 0
        while len(pages) < cap:
            j = get_json(http, f"{base}/rest/api/content/search", "Confluence search", params=dict(cql=cql, expand="body.storage,space,version", limit=min(25, cap - len(pages)), start=start), headers=h)
            res = j.get("results", [])
            pages += res
            if len(res) == 0 or not (j.get("_links") or {}).get("next"):
                break
            start += len(res)
        docs, recs = [], []
        for p in pages:
            text = _html(((p.get("body") or {}).get("storage") or {}).get("value", ""))
            link = base + ((p.get("_links") or {}).get("webui") or "")
            recs.append(dict(title=p.get("title"), space=(p.get("space") or {}).get("key"), updated=((p.get("version") or {}).get("when") or "")[:10], url=link, chars=len(text)))
            if len(text) >= 40:
                docs.append(dict(title=p.get("title") or "Untitled page", text=text, doc_type="Confluence", url=link))
        return SyncData(records=recs, documents=docs, meta=dict(spaces=spaces))

    def demo(self):
        s = get_store()
        apps = sorted(s.apps, key=lambda a: -a.get("debt", 0))[:3]
        docs = [dict(title=f"{a['name']}: solution overview", doc_type="Confluence", url="",
                     text=f"{a['name']} solution overview\n\n{a['name']} is a {a['criticality']}-criticality application in {a['domain']}, hosted {a['hosting']}. It is owned by {a.get('team', 'its platform team')}.\n\n"
                          f"Integrations: it publishes events to Kafka Event Platform and reads customer data through Customer API v2. Some reports still query Policy Master DB directly.\n\n"
                          f"Availability target: 99.9%. Recovery targets are to be confirmed. Security: single sign-on through the Identity Platform.") for a in apps]
        recs = [dict(title=d["title"], space="ARCH", updated="2026-11-02", url="", chars=len(d["text"])) for d in docs]
        return SyncData(records=recs, documents=docs, meta=dict(spaces=["ARCH (demo)"]))


# ================================================================ SharePoint
DOC_EXT = {".docx", ".pdf", ".md", ".txt", ".xlsx", ".html", ".htm"}


class SharePoint(Connector):
    id = "sharepoint"
    name = "SharePoint"
    vendor = "Microsoft"
    category = "docs"
    description = "ARB templates, high-level designs and standards documents from a SharePoint library."
    provides = ["Word, PDF and Excel documents into Document intelligence"]
    fields = [
        FieldSpec("tenant_id", "Tenant ID"),
        FieldSpec("client_id", "Client (application) ID"),
        FieldSpec("client_secret", "Client secret", "secret"),
        FieldSpec("site_url", "Site URL", "url", placeholder="https://yourcompany.sharepoint.com/sites/Architecture"),
        FieldSpec("folder", "Folder in the document library", required=False, placeholder="ARB/Submissions", help="Empty reads the library root."),
        FieldSpec("max_files", "Maximum files", required=False, default="20"),
    ]
    setup = ["An app registration with Microsoft Graph Sites.Selected (or Sites.Read.All) application permission, admin-consented", "Read access granted to the chosen site"]
    GRAPH = "https://graph.microsoft.com/v1.0"

    def _site(self, cfg, http, h):
        u = urlparse(base_url(cfg.get("site_url", ""), "Site URL"))
        return get_json(http, f"{self.GRAPH}/sites/{u.hostname}:{u.path or '/'}", "SharePoint site", headers=h)

    def _h(self, cfg, http):
        return {"Authorization": "Bearer " + entra_token(http, cfg.get("tenant_id", "").strip(), cfg.get("client_id", "").strip(), secret(cfg.get("client_secret", "")), "https://graph.microsoft.com/.default")}

    def test(self, cfg, http):
        site = self._site(cfg, http, self._h(cfg, http))
        return f"Read access confirmed on the site {site.get('displayName') or site.get('name')}."

    def fetch(self, cfg, http):
        from app.services import files as F

        h = self._h(cfg, http)
        site = self._site(cfg, http, h)
        folder = (cfg.get("folder") or "").strip().strip("/")
        url = f"{self.GRAPH}/sites/{site['id']}/drive/root" + (f":/{quote(folder)}:/children" if folder else "/children")
        cap = max(1, min(int(cfg.get("max_files") or 20), 100))
        items = get_json(http, url, "SharePoint folder", headers=h, params={"$top": 200}).get("value", [])
        picked = [i for i in items if "file" in i and PurePosixPath(i.get("name", "")).suffix.lower() in DOC_EXT and (i.get("size") or 0) <= 10_000_000][:cap]
        docs, recs = [], []
        for it in picked:
            data = call(http, "GET", f"{self.GRAPH}/sites/{site['id']}/drive/items/{it['id']}/content", f"SharePoint {it['name']}", headers=h).content
            note = ""
            try:
                text = F.extract(it["name"], data)["text"]
                docs.append(dict(title=PurePosixPath(it["name"]).stem[:200], text=text, doc_type="SharePoint", url=it.get("webUrl", "")))
            except Exception as e:  # noqa: BLE001 - one unreadable file should not stop the sync
                text, note = "", str(e)[:120]
            recs.append(dict(name=it["name"], size=it.get("size"), modified=(it.get("lastModifiedDateTime") or "")[:10], url=it.get("webUrl", ""), chars=len(text), note=note))
        return SyncData(records=recs, documents=docs, meta=dict(site=site.get("displayName"), folder=folder or "/"))

    def demo(self):
        docs = [dict(title="ARB submission: Agent portal single sign-on", doc_type="SharePoint", url="",
                     text="Architecture Review Board submission\n\nTechnology: Agent Portal single sign-on.\nWhat it does: lets broker agents sign in with their own identity provider through the Identity Platform.\n"
                          "Data: agent profile and policy summaries; no health data.\nIntegrations: Identity Platform (OIDC), Customer API v2.\nHosting: Azure App Service in West Europe, private endpoints.\n"
                          "Monitoring: Azure Monitor. Support: Digital Channels team.\nLicensing: none (internal build).\nNon-functional: availability 99.9%, recovery time 4 hours; recovery point not stated."),
                dict(title="Integration standards v3", doc_type="SharePoint", url="",
                     text="Integration standards\n\nAll new integrations go through the API gateway or the Kafka Event Platform. Direct database access between applications is not allowed. "
                          "APIs are versioned; breaking changes need a new major version and a deprecation window of six months.")]
        recs = [dict(name=d["title"] + ".docx", size=None, modified="2026-11-04", url="", chars=len(d["text"]), note="") for d in docs]
        return SyncData(records=recs, documents=docs, meta=dict(site="Architecture (demo)", folder="ARB"))


CONNECTORS: dict[str, Connector] = {c.id: c for c in (ServiceNow(), Jira(), Azure(), GitHub(), Confluence(), SharePoint())}
