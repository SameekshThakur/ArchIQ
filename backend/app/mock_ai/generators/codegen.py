"""Architecture-to-code: renders starter files and validates them server-side for the deployability checklist."""

from __future__ import annotations

import ast
import io
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile

import yaml

from app.mock_ai.generators import codegen_templates as T
from app.mock_ai.narration import render_template

OUTPUTS = {
    "terraform": "Terraform (AKS + Private Endpoint + Key Vault)",
    "bicep": "Bicep (AKS + Private Endpoint + Key Vault)",
    "openapi": "OpenAPI 3.1 contract",
    "fastapi": "FastAPI service skeleton",
    "spring": "Spring Boot service skeleton",
    "dockerfile": "Dockerfile",
    "ci": "CI pipeline (GitHub Actions)",
}
LANG = {".tf": "hcl", ".bicep": "hcl", ".yaml": "yaml", ".yml": "yaml", ".py": "python", ".java": "java", ".xml": "markdown", ".md": "markdown", ".txt": "bash", "Dockerfile": "dockerfile"}

_store: dict[str, dict] = {}


def _lang(path: str) -> str:
    if path.endswith("Dockerfile"):
        return "dockerfile"
    for ext, lang in LANG.items():
        if path.endswith(ext):
            return lang
    return "text"


def _plural(word: str) -> str:
    return word[:-1] + "ies" if word.endswith("y") else word + "s"


def generate(source: str, name: str, resource: str, outputs: list[str], region: str = "westeurope", owner: str = "Platform Engineering", include_openai: bool = False, domain: str = "Customer & Distribution") -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "service"
    res = re.sub(r"[^a-z]", "", resource.lower()) or "customer"
    Res = res.capitalize()
    plural = _plural(res)
    ctx = dict(name=slug, slug=slug, region=region, owner=owner, include_openai=include_openai, resource=res, Resource=Res, plural=plural, plural_py=plural, resource_py=res, pkg=slug.replace("-", ""),
               title=f"{Res} API" if res != "customer" else "Customer API", version="2.0.0", version_path="v2", id_example="CUS-00481723" if res == "customer" else f"{res[:3].upper()}-0001", domain=domain, origin=source)
    files: dict[str, str] = {}
    r = lambda tpl: render_template(tpl, **ctx) + "\n"  # noqa: E731
    if "terraform" in outputs:
        files["infra/terraform/providers.tf"] = T.TF_PROVIDERS
        files["infra/terraform/variables.tf"] = r(T.TF_VARIABLES)
        files["infra/terraform/main.tf"] = r(T.TF_MAIN)
        files["infra/terraform/outputs.tf"] = T.TF_OUTPUTS
    if "bicep" in outputs:
        files["infra/bicep/main.bicep"] = r(T.BICEP)
    if "openapi" in outputs:
        files[f"openapi/{slug}.yaml"] = r(T.OPENAPI_CUSTOMER if res == "customer" else T.OPENAPI_GENERIC)
    if "fastapi" in outputs:
        files["app/__init__.py"] = ""
        files["app/main.py"] = r(T.FASTAPI_MAIN)
        files["tests/test_api.py"] = r(T.FASTAPI_TEST)
        files["requirements.txt"] = T.FASTAPI_REQ
    if "spring" in outputs:
        pkg = ctx["pkg"]
        files["service-java/pom.xml"] = r(T.SPRING_POM)
        files[f"service-java/src/main/java/com/northwind/{pkg}/Application.java"] = r(T.SPRING_APP)
        files[f"service-java/src/main/java/com/northwind/{pkg}/{Res}Controller.java"] = r(T.SPRING_CONTROLLER)
        files["service-java/src/main/resources/application.yml"] = r(T.SPRING_YML)
    if "dockerfile" in outputs:
        files["Dockerfile"] = T.DOCKERFILE
    if "ci" in outputs:
        files[".github/workflows/ci.yml"] = r(T.CI)
    files["README.md"] = render_template(T.README, **ctx, files=sorted(files)) + "\n"

    checks = validate(files)
    cid = uuid.uuid4().hex[:10]
    out = dict(id=cid, name=slug, source=source, files=[dict(path=p, language=_lang(p), content=c, lines=c.count("\n") + 1) for p, c in sorted(files.items())], checklist=checks,
               passed=sum(c["status"] == "pass" for c in checks), total=len(checks))
    _store[cid] = out
    return out


def validate(files: dict[str, str]) -> list[dict]:
    checks: list[dict] = []

    def add(label: str, ok: bool | None, detail: str) -> None:
        if ok is None:
            return
        checks.append(dict(label=label, status="pass" if ok else "fail", detail=detail))

    tf = "\n".join(c for p, c in files.items() if p.endswith(".tf"))
    if tf:
        add("Terraform braces balanced", tf.count("{") == tf.count("}"), f"{tf.count('{')} opening and {tf.count('}')} closing braces")
        add("Terraform pins provider and version", 'required_version' in tf and 'version = "~>' in tf, "required_providers and required_version present")
        add("Key Vault has public access disabled (STD-SEC-014)", "public_network_access_enabled = false" in tf, "azurerm_key_vault.this")
        add("Private endpoint for Key Vault present", 'resource "azurerm_private_endpoint" "vault"' in tf, "azurerm_private_endpoint.vault")
        add("AKS is a private cluster", "private_cluster_enabled   = true" in tf, "azurerm_kubernetes_cluster.this")
        add("Mandatory tags applied (STD-CLD-003)", tf.count("tags") >= 6, "tags on all taggable resources")
    bicep = files.get("infra/bicep/main.bicep")
    if bicep:
        add("Bicep braces balanced", bicep.count("{") == bicep.count("}"), "main.bicep")
        add("Bicep Key Vault public access disabled", "publicNetworkAccess: 'Disabled'" in bicep, "Microsoft.KeyVault/vaults")
    for p, c in files.items():
        if p.endswith("openapi") or p.startswith("openapi/"):
            try:
                doc = yaml.safe_load(c)
                refs = set(re.findall(r'\$ref: "#/components/(\w+)/(\w+)"', c))
                comps = doc.get("components", {})
                missing = [f"{a}/{b}" for a, b in refs if b not in comps.get(a, {})]
                add("OpenAPI parses as YAML", True, p)
                add("OpenAPI version is 3.1.x", str(doc.get("openapi", "")).startswith("3.1"), str(doc.get("openapi")))
                add("All $ref targets resolve", not missing, "none missing" if not missing else ", ".join(missing))
                add("Every operation has an operationId", all("operationId" in op for v in doc["paths"].values() for k, op in v.items() if k in ("get", "post", "put", "patch", "delete")), f"{len(doc['paths'])} paths")
            except Exception as e:  # noqa: BLE001
                add("OpenAPI parses as YAML", False, str(e))
    py = {p: c for p, c in files.items() if p.endswith(".py") and c.strip()}
    if py:
        bad = []
        for p, c in py.items():
            try:
                ast.parse(c)
            except SyntaxError as e:
                bad.append(f"{p}: {e.msg}")
        add("Python sources compile", not bad, "all files parse" if not bad else "; ".join(bad))
    pom = files.get("service-java/pom.xml")
    if pom:
        try:
            ET.fromstring(pom)
            add("Maven POM is well-formed XML", True, "service-java/pom.xml")
        except ET.ParseError as e:
            add("Maven POM is well-formed XML", False, str(e))
    df = files.get("Dockerfile")
    if df:
        add("Container runs as non-root", "USER 10001" in df, "USER 10001")
        add("Container declares a HEALTHCHECK", "HEALTHCHECK" in df, "Dockerfile")
    ci = files.get(".github/workflows/ci.yml")
    if ci:
        try:
            doc = yaml.safe_load(ci)
            add("CI workflow is valid YAML with jobs", bool(doc.get("jobs")), f"{len(doc['jobs'])} jobs")
        except Exception as e:  # noqa: BLE001
            add("CI workflow is valid YAML with jobs", False, str(e))
    secrets = [p for p, c in files.items() if re.search(r"(?i)(password|secret|api[_-]?key)\s*[:=]\s*[\"'][^\"']{6,}", c)]
    add("No hard-coded secrets", not secrets, "none detected" if not secrets else ", ".join(secrets))
    return checks


def get(cid: str) -> dict | None:
    return _store.get(cid)


def zip_bytes(cid: str) -> bytes | None:
    g = _store.get(cid)
    if not g:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in g["files"]:
            z.writestr(f"{g['name']}/{f['path']}", f["content"])
    return buf.getvalue()
