"""Connector framework: field specs, a safe HTTP helper, and what a sync returns.

Every connector is read-only. It never writes to the platform it reads. A connector has two ways to run:
`fetch` calls the real platform with the credentials the user saved, and `demo` builds the same shape of data
from the sample estate, so the whole flow can be shown without access.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

TIMEOUT = 25.0
transport: httpx.BaseTransport | None = None  # tests inject a mock transport here


class ConnectorError(Exception):
    """A failure the user can act on (bad credentials, wrong URL, no permission)."""


@dataclass
class FieldSpec:
    key: str
    label: str
    kind: str = "text"  # text | url | secret | textarea
    required: bool = True
    placeholder: str = ""
    help: str = ""
    default: str = ""

    def public(self) -> dict:
        return dict(key=self.key, label=self.label, kind=self.kind, required=self.required, placeholder=self.placeholder, help=self.help, default=self.default)


@dataclass
class SyncData:
    records: list[dict] = field(default_factory=list)  # normalised rows shown in the UI
    documents: list[dict] = field(default_factory=list)  # {title, text, doc_type, url}
    components: list[dict] = field(default_factory=list)  # design components for the standards checker
    cmdb_rows: list[dict] = field(default_factory=list)  # rows for the inventory reconciler
    work_items: list[dict] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class Connector:
    id = ""
    name = ""
    vendor = ""
    category = ""  # cmdb | work | cloud | code | docs
    description = ""
    provides: list[str] = []
    fields: list[FieldSpec] = []
    setup: list[str] = []  # what the platform admin must create, in plain words

    def test(self, cfg: dict[str, str], http: httpx.Client) -> str:  # returns a one-line confirmation
        raise NotImplementedError

    def fetch(self, cfg: dict[str, str], http: httpx.Client) -> SyncData:
        raise NotImplementedError

    def demo(self) -> SyncData:
        raise NotImplementedError

    def public(self) -> dict:
        return dict(id=self.id, name=self.name, vendor=self.vendor, category=self.category, description=self.description, provides=self.provides,
                    fields=[f.public() for f in self.fields], setup=self.setup)


# ------------------------------------------------------------------ helpers
def client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True, transport=transport, headers={"User-Agent": "ArchIQ-connector/1.0", "Accept": "application/json"})


def secret(value: str) -> str:
    """A secret may be stored as `env:NAME`, which reads it from the server environment instead of the database."""
    if value.startswith("env:"):
        v = os.environ.get(value[4:].strip(), "")
        if not v:
            raise ConnectorError(f"The environment variable {value[4:].strip()} is not set on the server.")
        return v
    return value


def base_url(value: str, label: str) -> str:
    v = (value or "").strip().rstrip("/")
    u = urlparse(v)
    local = u.hostname in ("localhost", "127.0.0.1")
    if u.scheme != "https" and not (u.scheme == "http" and local):
        raise ConnectorError(f"{label} must start with https://")
    if not u.hostname:
        raise ConnectorError(f"{label} is not a valid address.")
    return v


def call(http: httpx.Client, method: str, url: str, what: str, **kw: Any) -> httpx.Response:
    try:
        r = http.request(method, url, **kw)
    except httpx.TimeoutException as e:
        raise ConnectorError(f"{what}: the platform did not answer within {TIMEOUT:.0f} seconds.") from e
    except httpx.HTTPError as e:
        raise ConnectorError(f"{what}: could not reach {urlparse(url).hostname} ({type(e).__name__}). Check the address and the network or proxy.") from e
    if r.status_code in (401,):
        raise ConnectorError(f"{what}: the credentials were rejected (401).")
    if r.status_code == 403:
        raise ConnectorError(f"{what}: the account has no permission for this (403).")
    if r.status_code == 404:
        raise ConnectorError(f"{what}: not found (404). Check the address, name or ID.")
    if r.status_code == 429:
        raise ConnectorError(f"{what}: rate limited by the platform (429). Try again later.")
    if r.status_code >= 400:
        raise ConnectorError(f"{what}: the platform returned {r.status_code}. {_short(r.text)}")
    return r


def get_json(http: httpx.Client, url: str, what: str, **kw: Any) -> Any:
    r = call(http, "GET", url, what, **kw)
    try:
        return r.json()
    except ValueError as e:
        raise ConnectorError(f"{what}: the answer was not JSON. Is the address right?") from e


def _short(text: str) -> str:
    return " ".join((text or "").split())[:200]


def csv_list(value: str) -> list[str]:
    return [x.strip() for x in (value or "").replace("\n", ",").split(",") if x.strip()]


def entra_token(http: httpx.Client, tenant: str, client_id: str, client_secret: str, scope: str) -> str:
    """Client-credentials token from Microsoft Entra ID (Azure AD)."""
    if not tenant or not client_id or not client_secret:
        raise ConnectorError("Tenant ID, client ID and client secret are all required.")
    r = call(http, "POST", f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", "Sign-in to Microsoft Entra ID",
             data=dict(grant_type="client_credentials", client_id=client_id, client_secret=client_secret, scope=scope))
    tok = r.json().get("access_token")
    if not tok:
        raise ConnectorError("Sign-in to Microsoft Entra ID returned no token.")
    return tok
