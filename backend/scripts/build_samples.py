"""Generate realistic sample input files for demos.

Run from backend/:  PYTHONPATH=. python3 -m scripts.build_samples
Writes to ../sample-files. The API serves that folder at /api/v1/files/samples, which powers the one-click \"Use this sample\" buttons.
Every file is built from the seeded Northwind estate, so what you upload reconciles with what the app already knows.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.api.v1.routers.core import _shadow_ids
from app.repositories.store import get_store

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "sample-files"

CRIT_LABEL = {"critical": "1 - Critical", "high": "2 - High", "medium": "3 - Medium", "low": "4 - Low"}
HOST_LABEL = {"azure": "Azure", "on-prem": "On-Premises", "mainframe": "Mainframe", "saas": "SaaS"}


# ------------------------------------------------------------------ CMDB export
def cmdb_rows() -> list[dict]:
    s = get_store()
    shadow = set(_shadow_ids())
    apps = [a for a in s.apps if a["id"] not in shadow]  # the CMDB never learned about the shadow systems
    by_hash = sorted(apps, key=lambda a: a["id"])
    crit_wrong = {a["id"] for a in by_hash if a["criticality"] in ("critical", "high")}
    crit_wrong = set(sorted(crit_wrong)[3:6])  # three criticality disagreements
    host_wrong = {a["id"] for a in by_hash if a["hosting"] == "azure"}
    host_wrong = set(sorted(host_wrong)[4:6])  # CMDB still says on-prem for two migrated apps
    owner_wrong = set(sorted(a["id"] for a in by_hash if a["owner_id"])[10:12])
    renamed = {"Claims Payments Hub": "Claim Payments Hub", "Northwind Customer Hub": "Northwind Customer Hub v2"}
    rows = []
    for a in apps:
        crit = a["criticality"]
        if a["id"] in crit_wrong:
            crit = {"critical": "high", "high": "medium"}[crit]
        host = a["hosting"]
        if a["id"] in host_wrong:
            host = "on-prem"
        owner = s.owner(a["owner_id"])["name"] if a["owner_id"] else ""
        if a["id"] in owner_wrong:
            owner = "Daniel Fernandes"  # left the company in Q2; never reassigned
        rows.append({
            "Name": renamed.get(a["name"], a["name"]), "Number": f"CI{a['id'][4:].zfill(7)}", "Business Criticality": CRIT_LABEL[crit], "Owned by": owner,
            "Support group": a["team"], "Install Status": "Installed", "Hosting": HOST_LABEL[host], "Business Unit": a["domain"],
            "Short description": a["description"], "Updated": "2026-10-28 09:14:07",
        })
    rows += [
        {"Name": "Broker Commission Calculator", "Number": "CI0009001", "Business Criticality": "3 - Medium", "Owned by": "Priya Menon", "Support group": "Finance Systems", "Install Status": "Installed",
         "Hosting": "On-Premises", "Business Unit": "Billing & Finance", "Short description": "Excel and VBA tool used by distribution finance to compute broker commissions.", "Updated": "2026-09-14 16:40:22"},
        {"Name": "Claims SMS Gateway", "Number": "CI0009002", "Business Criticality": "3 - Medium", "Owned by": "Ananya Rao", "Support group": "Claims Digital", "Install Status": "Installed",
         "Hosting": "SaaS", "Business Unit": "Claims", "Short description": "Third-party SMS provider used for claim status notifications.", "Updated": "2026-08-02 11:05:51"},
        {"Name": "Legacy Fax-to-PDF Bridge", "Number": "CI0009003", "Business Criticality": "4 - Low", "Owned by": "", "Support group": "Infrastructure Operations", "Install Status": "Retired",
         "Hosting": "On-Premises", "Business Unit": "Claims", "Short description": "Decommissioned fax ingestion bridge. Retained in CMDB for audit.", "Updated": "2025-12-19 08:30:00"},
    ]
    return rows


def write_cmdb() -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    rows = cmdb_rows()
    cols = list(rows[0])
    with open(OUT / "sample-cmdb-export-2026-11.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    wb = Workbook()
    ws = wb.active
    ws.title = "cmdb_ci_business_app"
    ws.append(cols)
    for r in rows:
        ws.append([r[c] for c in cols])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3A5F")
    for i, c in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(i)].width = 46 if c == "Short description" else 26
    ws.freeze_panes = "A2"
    wb.save(OUT / "sample-cmdb-export-2026-11.xlsx")


# ------------------------------------------------------------------ Word HLD
def write_hld() -> None:
    from docx import Document
    from docx.shared import Pt

    d = Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10.5)
    d.add_heading("Claims Intake Modernization: High-Level Design", 0)
    d.add_paragraph("Status: Proposed")
    d.add_paragraph("Version 1.2 · Author: Ananya Rao (Claims Digital) · Reviewers: Avadhi Jain, Rohan Kulkarni · Last updated 28 October 2026")
    d.add_heading("1. Purpose and scope", 1)
    d.add_paragraph(
        "Claims intake volumes spike by a factor of four during storm season, and the current intake path was sized for average load. This document describes the changes needed to let first notice of loss scale "
        "independently of the systems of record, and records the current-state architecture the design starts from. It covers the customer-facing intake portal, its integrations and the supporting data stores. "
        "Payments and reserving are out of scope.")
    d.add_heading("2. Current-state architecture", 1)
    d.add_paragraph("The intake path was documented from the team's working knowledge in September 2026. The statements below describe how the pieces fit together today.")
    d.add_heading("2.1 Intake portal", 2)
    d.add_paragraph("Claims Intake Portal is hosted on Azure App Service. Claims Intake Portal reads from Policy Master DB. Claims Intake Portal calls Customer API v2.")
    d.add_paragraph("Claims Intake Portal integrates with Claims Notification Service using event. Notifications to policyholders are sent from there, which keeps the portal free of messaging logic.")
    d.add_heading("2.2 Document handling", 2)
    d.add_paragraph("Photographs and adjuster reports are filed in the document store, and policyholders are told about progress through the notification hub. Customer Notification Hub is hosted on Azure App Service. Retention follows the claims records policy and is managed centrally.")
    d.add_paragraph("Guidewire ClaimCenter integrates with Claims Document Vault using api.")
    d.add_heading("2.3 Policy lookups", 2)
    d.add_paragraph("Coverage checks at intake use the policy platform. Operational detail for the policy platform, including its database, is held in its own runbook.")
    d.add_heading("3. Target architecture", 1)
    d.add_paragraph(
        "The target decouples intake from the policy and claims systems of record using an event backbone. Submissions are validated and acknowledged immediately, then processed asynchronously. "
        "Reads against Policy Master DB are replaced by a cached coverage API, removing the direct database dependency from the portal.")
    for t in ("Intake requests are accepted into a durable queue before any downstream call is made.", "Coverage checks are served from a read-optimised cache refreshed by policy change events.",
              "The portal is deployed across two availability zones with autoscaling on queue depth."):
        d.add_paragraph(t, style="List Bullet")
    d.add_heading("4. Non-functional requirements", 1)
    tbl = d.add_table(rows=1, cols=3)
    tbl.style = "Light Grid Accent 1"
    for i, h in enumerate(("Requirement", "Target", "Notes")):
        tbl.rows[0].cells[i].text = h
    for r in (("Availability", "99.95%", "Excluding planned maintenance"), ("Peak throughput", "900 requests/second", "Storm-season peak, 4x average"), ("p95 latency", "800 ms", "Acknowledgement, not completion"),
              ("RTO / RPO", "2 hours / 5 minutes", "Meets tier 2 resilience standard"), ("Compliance", "GDPR, SOX", "Personal data stays in West Europe")):
        c = tbl.add_row().cells
        for i, v in enumerate(r):
            c[i].text = v
    d.add_heading("5. Risks and open questions", 1)
    for t in ("The coverage cache must be invalidated reliably; a stale cache could approve a claim against a lapsed policy.", "Customer API v2 has 14 consumers; any change to its contract needs a coordinated rollout.",
              "It is not yet agreed who owns the intake queue operationally."):
        d.add_paragraph(t, style="List Bullet")
    d.save(OUT / "Claims-Intake-Modernization-HLD-v1.2.docx")


# ------------------------------------------------------------------ PDF runbook
def write_runbook() -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    ss = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(OUT / "Policy-Admin-Operations-Runbook.pdf"), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm, bottomMargin=20 * mm, title="Policy Admin Core Operations Runbook", author="Priya Nair")
    P = lambda t, s="BodyText": Paragraph(t, ss[s])  # noqa: E731
    flow = [
        P("Policy Admin Core: Operations Runbook", "Title"), P("Status: Current"), P("Owner: Priya Nair, Policy Platform. Last reviewed 14 October 2026. Classification: Internal."), Spacer(1, 8),
        P("1. Purpose", "Heading2"),
        P("This runbook describes how Policy Admin Core is operated, monitored and recovered. It is written for the on-call engineer and assumes familiarity with the Duck Creek Policy administration console. "
          "Business-process guidance for underwriters is maintained separately."),
        P("2. Architecture overview", "Heading2"),
        P("Policy Admin Core is hosted on on-premises Windows Server. The application tier runs as three IIS nodes behind a hardware load balancer, with a scheduled batch node for renewals and endorsements."),
        P("Policy Admin Core stores its data in Policy Master DB."),
        P("The database is an Oracle 12c instance that is also used by other applications, so schema changes must be agreed with the database owners before release."),
        P("Policy Admin Core integrates with Policy Search Service using esb. Search indexes are rebuilt nightly from the policy tables, and a failed rebuild does not affect transaction processing."),
        P("Policy Admin Core calls Customer API v2. The call is made when a policyholder record is created or amended, and the response is cached for fifteen minutes."),
        P("3. Daily checks", "Heading2"),
        P("Confirm the overnight renewal batch completed and that the exception queue holds fewer than fifty items. Check Oracle tablespace usage on Policy Master DB; alert if any tablespace exceeds eighty-five percent. "
          "Review the failed-integration dashboard and clear transient failures by replaying them from the console."),
        P("4. Recovery", "Heading2"),
        P("In a node failure the load balancer removes the node automatically; no action is needed beyond raising a ticket. For a database failure, follow the Oracle Data Guard switchover procedure maintained by the "
          "database team. The recovery time objective is four hours and the recovery point objective is fifteen minutes."),
        P("5. Known issues", "Heading2"),
        P("Windows Server 2019 patch cycles require a rolling restart and take roughly ninety minutes. The Duck Creek vendor has not yet certified the platform for Oracle 19c, which blocks the planned database upgrade."),
    ]
    doc.build(flow)


# ------------------------------------------------------------------ ADR + designs
ADR = """# ADR-0052: Event-driven claims notifications

Status: Accepted
Date: 2026-10-21
Deciders: Avadhi Jain (Chief Architect), Ananya Rao (Claims Digital), Arjun Desai (Integration)
Domain: Claims

## Context
Policyholders receive status updates by SMS and email when a claim moves between stages. Today each system that changes a claim sends its own notification, which has produced duplicate messages and inconsistent wording. During storm season the volume also overloads the systems that send them.

## Decision
Claim lifecycle changes are published as events and Claims Notification Service is the only sender of policyholder messages.

Claims Notification Service integrates with Kafka Event Platform using event. Claims Intake Portal integrates with Claims Notification Service using event. Fraud Scoring Engine integrates with Claims Notification Service using event.

Message templates are owned by Claims Digital and versioned in the notification repository.

## Consequences
- One place to change wording, channels and quiet hours.
- Kafka Event Platform becomes a dependency of the claim lifecycle and must be run with the resilience of a tier 1 service.
- Teams that currently send their own notifications must migrate within two quarters.

## Alternatives considered
1. Keep per-system notifications and publish a shared style guide. Rejected: does not remove duplicates.
2. Use the vendor notification module in Guidewire ClaimCenter. Rejected: only covers claims created in that system.
"""

NOTIF_DESIGN = """Claims Notification Service v2: ARB submission

Summary
Claims Notification Service sends SMS and email updates to policyholders. v2 adds an AI assistant that drafts the message text from the claim notes, so adjusters no longer write status updates by hand.

Architecture
The service runs on AKS behind Azure API Management. API Management is internet facing and sits behind a web application firewall. Claim events arrive from Kafka. Drafts are generated by Azure OpenAI.

The Azure OpenAI resource is reached over a public endpoint and the service authenticates to it with an API key stored in the deployment's environment variables. Content filter is set to standard. Prompts are not logged.
Drafted messages are sent automatically to the policyholder without review. Customer data is held in an Azure Storage account with TLS 1.0 still enabled for the legacy SMS provider. The storage account allows direct public access for the provider's callbacks.

Non-functional requirements
Availability 99.9%, RTO 4 hours, RPO 15 minutes, p95 latency 2500 ms, throughput 40 requests per second. Compliance GDPR.
"""

TF_BAD = '''# Claims Copilot: production environment (as deployed 2026-10-30)
# Owner: AI & Automation. Managed by Terraform.

variable "location" {
  default = "westeurope"
}

locals {
  common_tags = {
    owner       = "ai-automation"
    cost_centre = "CC-4410"
    environment = "production"
  }
}

resource "azurerm_resource_group" "copilot" {
  name     = "rg-claims-copilot-prod"
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_cognitive_account" "aoai" {
  name                          = "aoai-claims-copilot-prod"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.copilot.name
  kind                          = "OpenAI"
  sku_name                      = "S0"
  custom_subdomain_name         = "aoai-claims-copilot-prod"
  public_network_access_enabled = true
  local_auth_enabled            = true
  tags                          = local.common_tags
}

resource "azurerm_cognitive_deployment" "gpt4o" {
  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.aoai.id
  rai_policy_name      = "Microsoft.Default"
  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-08-06"
  }
}

resource "azurerm_storage_account" "sessions" {
  name                          = "stclaimscopilotprod"
  resource_group_name           = azurerm_resource_group.copilot.name
  location                      = var.location
  account_tier                  = "Standard"
  account_replication_type      = "GRS"
  min_tls_version               = "TLS1_0"
  public_network_access_enabled = true
  tags = {
    owner = "ai-automation"
  }
}

resource "azurerm_key_vault" "kv" {
  name                          = "kv-claims-copilot-prod"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.copilot.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  soft_delete_retention_days    = 90
  public_network_access_enabled = false
  tags                          = local.common_tags
}

resource "azurerm_linux_web_app" "api" {
  name                = "app-claims-copilot-api"
  location            = var.location
  resource_group_name = azurerm_resource_group.copilot.name
  service_plan_id     = azurerm_service_plan.plan.id
  identity {
    type = "SystemAssigned"
  }
  app_settings = {
    AZURE_OPENAI_KEY = "5c1f0d3e-REDACTED"
    SESSION_STORE    = "stclaimscopilotprod"
  }
  site_config {
    minimum_tls_version = "1.2"
  }
  tags = local.common_tags
}

resource "azurerm_monitor_diagnostic_setting" "api" {
  name               = "send-to-law"
  target_resource_id = azurerm_linux_web_app.api.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
}
'''

TF_FIXED = '''# Claims Copilot: production environment (remediated)
# Owner: AI & Automation. Managed by Terraform. Fixes STD-SEC-014, STD-SEC-004, STD-SEC-002, STD-SEC-003, STD-CLD-003, STD-SEC-006.

variable "location" {
  default = "westeurope"
}

locals {
  common_tags = {
    owner               = "ai-automation"
    cost_centre         = "CC-4410"
    environment         = "production"
    data_classification = "confidential"
  }
}

resource "azurerm_resource_group" "copilot" {
  name     = "rg-claims-copilot-prod"
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_cognitive_account" "aoai" {
  name                          = "aoai-claims-copilot-prod"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.copilot.name
  kind                          = "OpenAI"
  sku_name                      = "S0"
  custom_subdomain_name         = "aoai-claims-copilot-prod"
  public_network_access_enabled = false
  local_auth_enabled            = false
  tags                          = local.common_tags
}

resource "azurerm_cognitive_deployment" "gpt4o" {
  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.aoai.id
  rai_policy_name      = "Microsoft.Default"
  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-08-06"
  }
}

resource "azurerm_private_endpoint" "aoai" {
  name                = "pe-aoai-claims-copilot"
  location            = var.location
  resource_group_name = azurerm_resource_group.copilot.name
  subnet_id           = azurerm_subnet.private.id
  private_service_connection {
    name                           = "aoai"
    private_connection_resource_id = azurerm_cognitive_account.aoai.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }
}

resource "azurerm_storage_account" "sessions" {
  name                          = "stclaimscopilotprod"
  resource_group_name           = azurerm_resource_group.copilot.name
  location                      = var.location
  account_tier                  = "Standard"
  account_replication_type      = "GRS"
  min_tls_version               = "TLS1_2"
  public_network_access_enabled = false
  blob_properties {
    delete_retention_policy {
      days = 365
    }
  }
  tags                          = local.common_tags
}

resource "azurerm_key_vault" "kv" {
  name                          = "kv-claims-copilot-prod"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.copilot.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  soft_delete_retention_days    = 90
  public_network_access_enabled = false
  tags                          = local.common_tags
}

resource "azurerm_linux_web_app" "api" {
  name                = "app-claims-copilot-api"
  location            = var.location
  resource_group_name = azurerm_resource_group.copilot.name
  service_plan_id     = azurerm_service_plan.plan.id
  identity {
    type = "SystemAssigned"
  }
  app_settings = {
    AZURE_OPENAI_ENDPOINT = "https://aoai-claims-copilot-prod.openai.azure.com"
    SESSION_STORE_SECRET  = "@Microsoft.KeyVault(SecretUri=https://kv-claims-copilot-prod.vault.azure.net/secrets/session-store/)"
  }
  site_config {
    minimum_tls_version = "1.2"
  }
  tags = local.common_tags
}

resource "azurerm_monitor_diagnostic_setting" "aoai" {
  name               = "send-to-law"
  target_resource_id = azurerm_cognitive_account.aoai.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
}

resource "azurerm_monitor_diagnostic_setting" "storage" {
  name               = "send-to-law"
  target_resource_id = azurerm_storage_account.sessions.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
}

resource "azurerm_monitor_diagnostic_setting" "kv" {
  name               = "send-to-law"
  target_resource_id = azurerm_key_vault.kv.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
}

resource "azurerm_monitor_diagnostic_setting" "api" {
  name               = "send-to-law"
  target_resource_id = azurerm_linux_web_app.api.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
}
'''

BICEP_BAD = '''// Claims Copilot: production environment, Bicep (as deployed 2026-10-30)
// Owner: AI & Automation.
param location string = 'West Europe'
param publicAccess bool = true
var tags = {
  owner: 'ai-automation'
  'cost-centre': 'CC-4410'
}

resource aoai 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: 'aoai-claims-copilot'
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    publicNetworkAccess: publicAccess ? 'Enabled' : 'Disabled'
    disableLocalAuth: false
  }
  tags: tags
}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'stclaimscopilot'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_GRS' }
  properties: {
    minimumTlsVersion: 'TLS1_0'
    publicNetworkAccess: 'Enabled'
  }
}

resource api 'Microsoft.Web/sites@2022-09-01' = {
  name: 'app-claims-copilot'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    siteConfig: {
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'AZURE_OPENAI_KEY', value: '5c1f-REDACTED' }
      ]
    }
  }
  tags: tags
}

resource diag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'send-to-law'
  scope: api
  properties: { workspaceId: 'x' }
}

'''

BICEP_FIXED = '''// Claims Copilot: production environment, Bicep (remediated)
// Owner: AI & Automation.
param location string = 'westeurope'
var tags = {
  owner: 'ai-automation'
  'cost-centre': 'CC-4410'
  'data-classification': 'confidential'
}
resource aoai 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: 'aoai'
  location: location
  kind: 'OpenAI'
  properties: {
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
  }
  tags: tags
}
resource pe 'Microsoft.Network/privateEndpoints@2023-04-01' = {
  name: 'pe-aoai'
  location: location
  properties: {
    privateLinkServiceConnections: [
      { name: 'aoai', properties: { privateLinkServiceId: aoai.id, groupIds: ['account'] } }
    ]
  }
}
resource dep 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: aoai
  name: 'gpt-4o'
  properties: { raiPolicyName: 'Microsoft.Default' }
}
resource d 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'law'
  scope: aoai
  properties: { workspaceId: 'x' }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'stclaimscopilot'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_GRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Disabled'
  }
  tags: tags
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 365 }
  }
}

resource storageDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'law'
  scope: storage
  properties: { workspaceId: 'x' }
}
'''

GUIDE = """ArchIQ sample files
====================

All files are built from the seeded Northwind Assurance estate, so they reconcile with what the app already knows.
Upload them from the page named in brackets (or click "Use sample" in the upload dialog).

1. sample-cmdb-export-2026-11.xlsx / .csv        [Discovery > Import inventory]
   A ServiceNow-style CMDB export of 66 applications. Expect: 56 clean matches, 5 applications with drift
   (3 criticality, 2 stale hosting, 2 stale owners), 2 renamed systems matched by name similarity (Claim Payments Hub,
   Northwind Customer Hub v2), 2 systems unknown to the estate (Broker Commission Calculator, Claims SMS Gateway),
   1 retired record, and 6 estate applications missing from the export (the shadow IT that only code discovery found).

2. Claims-Intake-Modernization-HLD-v1.2.docx         [Documents > Upload documents]
   A Word high-level design. It agrees with the estate in most places but says Customer Notification Hub runs on
   Azure App Service while the estate and several other documents say Azure AKS, which shows up as a new conflict.

3. Policy-Admin-Operations-Runbook.pdf               [Documents > Upload documents]
   A PDF runbook. It documents the Policy Admin Core to Policy Master DB dependency that no existing document
   records, so uploading it closes GAP-001 and adds a Current-status source that confirms the estate.

4. ADR-0052-Event-Driven-Claims-Notifications.md     [Documents > Upload documents]
   An accepted architecture decision record that adds Kafka-based notification relationships.

5. claims-copilot-main.tf                            [Standards > Check a design, or Review agent]
   Terraform as deployed. Compliance score 44: breaks the private-endpoint rule (STD-SEC-014), allows TLS 1.0,
   keeps a secret in app settings, and is missing tags and diagnostics.

6. claims-copilot-main.fixed.tf                      [Standards > Check a design]
   The remediated version. Score 88 with no failures. Run it after the first to show the recovery.

7. claims-copilot-main.bicep / .fixed.bicep         [Standards > Check a design]
   The same before-and-after story written in Bicep, for teams that deploy with Bicep rather than Terraform.

8. claims-notifications-design.md                    [Review agent > Review a design]
   An ARB submission written as prose, with deliberate policy breaches (public OpenAI endpoint, API key,
   no human review of AI-drafted messages, TLS 1.0 storage). Expect a no-go verdict (readiness about 28).

9. agent-portal-sso-design.json                      [Review agent > Review a design, or New analysis]
   A compliant ARB submission with its non-functional requirements filled in. Expect a go verdict (readiness 91).
   Use it to show the "Ready" outcome; domain: Customer & Distribution.

Regenerate with:  cd backend && PYTHONPATH=. python3 -m scripts.build_samples
"""


def write_ready_design() -> None:
    """A design that passes: the seeded 'Agent Portal Single Sign-On' submission, with its NFRs, as JSON."""
    import json

    sub = next(a for a in get_store().arb if a["id"] == "ARB-2026-006")
    (OUT / "agent-portal-sso-design.json").write_text(json.dumps(dict(name=sub["title"], components=sub["components"], nfr=sub["nfr"]), indent=2), encoding="utf-8")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    write_cmdb()
    write_hld()
    write_runbook()
    (OUT / "ADR-0052-Event-Driven-Claims-Notifications.md").write_text(ADR, encoding="utf-8")
    (OUT / "claims-notifications-design.md").write_text(NOTIF_DESIGN, encoding="utf-8")
    (OUT / "claims-copilot-main.tf").write_text(TF_BAD, encoding="utf-8")
    (OUT / "claims-copilot-main.fixed.tf").write_text(TF_FIXED, encoding="utf-8")
    (OUT / "claims-copilot-main.bicep").write_text(BICEP_BAD, encoding="utf-8")
    (OUT / "claims-copilot-main.fixed.bicep").write_text(BICEP_FIXED, encoding="utf-8")
    write_ready_design()
    (OUT / "README.txt").write_text(GUIDE, encoding="utf-8")
    print("wrote", len(list(OUT.iterdir())), "files to", OUT)


if __name__ == "__main__":
    main()
