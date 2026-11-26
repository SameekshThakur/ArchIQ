"""Generate the Kestrel Assurance Ltd seed estate (8 applications, 1 database, Claims domain)
using ArchIQ's seed mechanism (backend/app/data/seed/*.json).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import seed_governance as G
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import seed_governance as G  # type: ignore

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "seed"
REF_DATE = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)


def write(name: str, data: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> Path:
    # 1. Owners (matched to the owning teams in Section 4.2 & 4.3 so inventory.reconcile owner comparison aligns)
    owners = [
        dict(id="OWN-001", name="Claims Platform Engineering", team="Claims Platform Engineering", domain="Claims", role="Platform Engineering", email="claims.platform@kestrel-assurance.example"),
        dict(id="OWN-002", name="Integration Services", team="Integration Services", domain="Claims", role="Integration Engineering", email="integration@kestrel-assurance.example"),
        dict(id="OWN-003", name="Payments Engineering", team="Payments Engineering", domain="Claims", role="Payments Engineering", email="payments@kestrel-assurance.example"),
        dict(id="OWN-004", name="Digital Channels", team="Digital Channels", domain="Claims", role="Digital Engineering", email="digital@kestrel-assurance.example"),
        dict(id="OWN-005", name="Compliance Technology", team="Compliance Technology", domain="Claims", role="Compliance Engineering", email="compliance@kestrel-assurance.example"),
        dict(id="OWN-006", name="Data and Analytics", team="Data and Analytics", domain="Claims", role="Data Engineering", email="data@kestrel-assurance.example"),
        dict(id="OWN-007", name="Finance Technology", team="Finance Technology", domain="Claims", role="Finance Engineering", email="finance@kestrel-assurance.example"),
        dict(id="OWN-008", name="Enterprise Architecture", team="Enterprise Architecture", domain="Claims", role="Chief Architect", email="ea@kestrel-assurance.example"),
    ]

    # 2. Capabilities
    capabilities = [
        dict(id="CAP-CLM", name="Claims Management", parent=None, level=1),
        dict(id="CAP-CLM-REG", name="Claim Registration", parent="CAP-CLM", level=2),
        dict(id="CAP-CLM-ASM", name="Claim Assessment", parent="CAP-CLM", level=2),
        dict(id="CAP-CLM-PAY", name="Claim Payment", parent="CAP-CLM", level=2),
        dict(id="CAP-CLM-REP", name="Regulatory Reporting", parent="CAP-CLM", level=2),
        dict(id="CAP-CLM-ENQ", name="Customer Enquiry", parent="CAP-CLM", level=2),
    ]

    # 3. Technologies
    technologies = [
        dict(name="WebSphere 8.5", category="middleware", lifecycle="eol", support_end="2022-04"),
        dict(name="IBM WebSphere 8.5", category="middleware", lifecycle="eol", support_end="2022-04"),
        dict(name="Java 8", category="runtime", lifecycle="extended", support_end="2030-12"),
        dict(name="Java 17", category="runtime", lifecycle="supported", support_end="2029-09"),
        dict(name="IBM Db2", category="database", lifecycle="extended", support_end="2029-04"),
        dict(name="AKS", category="platform", lifecycle="supported", support_end="n/a"),
        dict(name="Azure Service Bus", category="middleware", lifecycle="supported", support_end="n/a"),
        dict(name="Azure SQL Database", category="database", lifecycle="supported", support_end="n/a"),
        dict(name="React 18", category="framework", lifecycle="supported", support_end="2027-12"),
        dict(name="Node.js 20", category="runtime", lifecycle="supported", support_end="2026-04"),
        dict(name="RHEL 8", category="os", lifecycle="supported", support_end="2029-05"),
    ]

    # 4. Eight Applications (Section 4.2)
    # Keys are assigned so that:
    # - The 3 cycle apps (Claims Core, Payment Service, Finance Reconciliation) use keys ("SAP", "SFC", "SNOW") NOT in flow_graph() hubs.
    # - The 5 non-cycle apps use the 5 hub keys ("APIM", "KAFKA", "MULE", "IIB", "MFT") expected by analysis.flow_graph().
    applications = [
        dict(
            id="APP-001", key="SAP", name="Claims Core", domain="Claims", kind="legacy",
            tech=["WebSphere 8.5", "Java 8", "IBM Db2"], lifecycle="extended", criticality="critical",
            hosting="on-prem", capabilities=["CAP-CLM-REG", "CAP-CLM-ASM"], owner_id="OWN-001",
            team="Claims Platform Engineering", vendor="In-house", version="3.2.0", users=1400,
            annual_cost_k=2800, loc_k=850, test_coverage=22, age_years=15, vulns_critical=2, vulns_high=7,
            single_instance=True, dr_tier="none", peak_tps=320, capacity_tps=450, internet_facing=False,
            role=None, db_key="CLAIMS_DB2",
            description="15-year-old core claims processing platform on IBM WebSphere and IBM Db2.",
            repo="kestrel/claims-core", doc_coverage=40,
        ),
        dict(
            id="APP-002", key="APIM", name="Claims API Gateway", domain="Claims", kind="platform",
            tech=["Java 17", "RHEL 8"], lifecycle="supported", criticality="critical",
            hosting="on-prem", capabilities=["CAP-CLM-REG", "CAP-CLM-ENQ"], owner_id="OWN-002",
            team="Integration Services", vendor="In-house", version="2.1.0", users=0,
            annual_cost_k=420, loc_k=45, test_coverage=78, age_years=4, vulns_critical=0, vulns_high=1,
            single_instance=False, dr_tier="warm", peak_tps=600, capacity_tps=1500, internet_facing=True,
            role=None, db_key=None,
            description="API gateway exposing Claims API in front of Claims Core.",
            repo="kestrel/claims-api-gateway", doc_coverage=75,
        ),
        dict(
            id="APP-003", key="SFC", name="Payment Service", domain="Claims", kind="custom",
            tech=["Java 17", "RHEL 8"], lifecycle="supported", criticality="critical",
            hosting="azure", capabilities=["CAP-CLM-PAY"], owner_id="OWN-003",
            team="Payments Engineering", vendor="In-house", version="4.0.2", users=250,
            annual_cost_k=680, loc_k=120, test_coverage=72, age_years=5, vulns_critical=0, vulns_high=1,
            single_instance=False, dr_tier="warm", peak_tps=180, capacity_tps=500, internet_facing=False,
            role=None, db_key=None,
            description="Claims payment disbursement service hosted on private cloud.",
            repo="kestrel/payment-service", doc_coverage=70,
        ),
        dict(
            id="APP-004", key="KAFKA", name="Customer Service Portal", domain="Claims", kind="custom",
            tech=["React 18", "Node.js 20", "AKS"], lifecycle="supported", criticality="high",
            hosting="azure", capabilities=["CAP-CLM-ENQ", "CAP-CLM-REG"], owner_id="OWN-004",
            team="Digital Channels", vendor="In-house", version="5.4.1", users=180000,
            annual_cost_k=540, loc_k=95, test_coverage=82, age_years=3, vulns_critical=0, vulns_high=0,
            single_instance=False, dr_tier="hot", peak_tps=450, capacity_tps=1200, internet_facing=True,
            role=None, db_key=None,
            description="Digital portal for policyholders and customer service agents on Azure.",
            repo="kestrel/customer-service-portal", doc_coverage=85,
        ),
        dict(
            id="APP-005", key="MULE", name="Regulatory Reporting", domain="Claims", kind="custom",
            tech=["Java 8", "RHEL 8"], lifecycle="supported", criticality="high",
            hosting="on-prem", capabilities=["CAP-CLM-REP"], owner_id="OWN-005",
            team="Compliance Technology", vendor="In-house", version="2.8.0", users=45,
            annual_cost_k=390, loc_k=110, test_coverage=48, age_years=9, vulns_critical=0, vulns_high=3,
            single_instance=True, dr_tier="cold", peak_tps=40, capacity_tps=120, internet_facing=False,
            role=None, db_key=None,
            description="Produces statutory and regulatory claims reports; reads directly from Claims Db2.",
            repo="kestrel/regulatory-reporting", doc_coverage=50,
        ),
        dict(
            id="APP-006", key="IIB", name="Claims Batch Processor", domain="Claims", kind="legacy",
            tech=["Java 8", "WebSphere 8.5"], lifecycle="supported", criticality="high",
            hosting="on-prem", capabilities=["CAP-CLM-ASM", "CAP-CLM-PAY"], owner_id="OWN-001",
            team="Claims Platform Engineering", vendor="In-house", version="1.9.4", users=20,
            annual_cost_k=460, loc_k=260, test_coverage=19, age_years=14, vulns_critical=1, vulns_high=5,
            single_instance=True, dr_tier="none", peak_tps=80, capacity_tps=140, internet_facing=False,
            role=None, db_key=None,
            description="Nightly claims reserve and settlement batch processor reading directly from Claims Db2.",
            repo="kestrel/claims-batch-processor", doc_coverage=20,
        ),
        dict(
            id="APP-007", key="MFT", name="Data Warehouse", domain="Claims", kind="custom",
            tech=["RHEL 8"], lifecycle="supported", criticality="high",
            hosting="azure", capabilities=["CAP-CLM-REP"], owner_id="OWN-006",
            team="Data and Analytics", vendor="In-house", version="3.1.0", users=310,
            annual_cost_k=920, loc_k=180, test_coverage=60, age_years=7, vulns_critical=0, vulns_high=2,
            single_instance=False, dr_tier="warm", peak_tps=120, capacity_tps=400, internet_facing=False,
            role=None, db_key=None,
            description="Enterprise data warehouse in private cloud extracting nightly directly from Claims Db2.",
            repo="kestrel/data-warehouse", doc_coverage=45,
        ),
        dict(
            id="APP-008", key="SNOW", name="Finance Reconciliation", domain="Claims", kind="legacy",
            tech=["Java 8", "RHEL 8"], lifecycle="extended", criticality="medium",
            hosting="on-prem", capabilities=["CAP-CLM-PAY"], owner_id="OWN-007",
            team="Finance Technology", vendor="In-house", version="2.0.1", users=65,
            annual_cost_k=310, loc_k=140, test_coverage=30, age_years=12, vulns_critical=0, vulns_high=4,
            single_instance=True, dr_tier="cold", peak_tps=35, capacity_tps=100, internet_facing=False,
            role=None, db_key=None,
            description="Reconciles claim payments and ledger adjustments; planned for sunset.",
            repo="kestrel/finance-reconciliation", doc_coverage=35,
        ),
    ]

    # 5. One Database: Claims Db2 (IBM Db2, single instance, no DR tier recorded)
    databases = [
        dict(
            id="DB-001", key="CLAIMS_DB2", name="Claims Db2", engine="IBM Db2",
            kind="relational", hosting="on-prem", owner_app="APP-001", domain="Claims",
            size_gb=4800, classification="restricted", lifecycle="extended", criticality="critical",
            single_instance=True, dr_tier="none",
        ),
    ]

    # 6. APIs: Claims API exposed through Claims API Gateway, consumed by Customer Service Portal
    apis = [
        dict(
            id="API-0001", name="Claims API", version="v1", protocol="REST", lifecycle="active",
            exposed_by="APP-002", owner_id="OWN-002", domain="Claims",
            consumers=["APP-004"], gateway=True, auth="oauth2", sla_tier="critical",
            requests_per_day=145000, contract="openapi", special="customer_v1",
        ),
        dict(
            id="API-0002", name="Claims Event API", version="v2", protocol="REST", lifecycle="active",
            exposed_by="APP-002", owner_id="OWN-002", domain="Claims",
            consumers=["APP-004", "APP-003"], gateway=True, auth="oauth2", sla_tier="high",
            requests_per_day=64000, contract="openapi", special="customer_v2",
        ),
    ]

    # 7. Integrations (Section 4.2)
    # - Claims Core exposes Claims API through Claims API Gateway
    # - Customer Service Portal calls Claims API
    # - Regulatory Reporting, Claims Batch Processor, Data Warehouse read directly from Claims Db2
    # - Payment Service -> Claims Core (message queue)
    # - Finance Reconciliation -> Payment Service (SFTP batch)
    # - Claims Core -> Finance Reconciliation (batch adjustments) -> closes the 3-system loop!
    integrations = [
        dict(
            id="INT-0001", name="Claims Core → Claims API Gateway",
            source_kind="app", source_id="APP-001", target_kind="app", target_id="APP-002",
            style="api", protocol="REST", via=None, frequency="real-time",
            payload="Claims API backend calls", api_id="API-0001",
            data_classification="restricted", criticality="critical", status="active",
        ),
        dict(
            id="INT-0002", name="Customer Service Portal → Claims API Gateway",
            source_kind="app", source_id="APP-004", target_kind="app", target_id="APP-002",
            style="api", protocol="REST", via=None, frequency="real-time",
            payload="Claim enquiries and FNOL submissions", api_id="API-0001",
            data_classification="confidential", criticality="high", status="active",
        ),
        dict(
            id="INT-0003", name="Regulatory Reporting → Claims Db2",
            source_kind="app", source_id="APP-005", target_kind="db", target_id="DB-001",
            style="direct_db", protocol="JDBC", via=None, frequency="nightly",
            payload="Direct table access", api_id=None,
            data_classification="restricted", criticality="high", status="active",
        ),
        dict(
            id="INT-0004", name="Claims Batch Processor → Claims Db2",
            source_kind="app", source_id="APP-006", target_kind="db", target_id="DB-001",
            style="direct_db", protocol="JDBC", via=None, frequency="nightly",
            payload="Direct table access", api_id=None,
            data_classification="restricted", criticality="high", status="active",
        ),
        dict(
            id="INT-0005", name="Data Warehouse → Claims Db2",
            source_kind="app", source_id="APP-007", target_kind="db", target_id="DB-001",
            style="direct_db", protocol="JDBC", via=None, frequency="nightly",
            payload="Direct table access (nightly extract)", api_id=None,
            data_classification="restricted", criticality="high", status="active",
        ),
        dict(
            id="INT-0006", name="Payment Service → Claims Core",
            source_kind="app", source_id="APP-003", target_kind="app", target_id="APP-001",
            style="event", protocol="MQ", via=None, frequency="real-time",
            payload="Payment status message queue", api_id=None,
            data_classification="restricted", criticality="critical", status="active",
        ),
        dict(
            id="INT-0007", name="Finance Reconciliation → Payment Service",
            source_kind="app", source_id="APP-008", target_kind="app", target_id="APP-003",
            style="file_batch", protocol="SFTP", via=None, frequency="nightly",
            payload="SFTP batch settlement reconciliation", api_id=None,
            data_classification="confidential", criticality="medium", status="active",
        ),
        dict(
            id="INT-0008", name="Claims Core → Finance Reconciliation",
            source_kind="app", source_id="APP-001", target_kind="app", target_id="APP-008",
            style="file_batch", protocol="SFTP", via=None, frequency="nightly",
            payload="Batch reserve and payment adjustments", api_id=None,
            data_classification="confidential", criticality="medium", status="active",
        ),
    ]

    # 8. Cloud resources (Kestrel's approved-versus-deployed estate records for drift when Azure connector is in demo mode)
    cloud_resources = [
        dict(
            id="CLD-0001", name="stkestrelclaimsprd01", provider="azure", type="storage_account",
            region="centralindia", env="prod", app_id="APP-004", domain="Claims",
            resource_group="rg-kestrel-claims-prd", subscription="kestrel-prd-ci",
            approved=dict(public_network_access=False, https_only=True, min_tls="1.2", replication="GRS", blob_public_access=False, soft_delete_days=30),
            deployed=dict(public_network_access=True, https_only=True, min_tls="1.2", replication="LRS", blob_public_access=False, soft_delete_days=30),
            managed_by="terraform",
            tags=dict(owner="Claims Platform Engineering", cost_centre="CC-4410", data_classification="confidential"),
            created_at="2026-06-15T09:00:00+00:00", resource_guid="00000000-0000-0000-0000-000000000001",
            drift_meta=dict(severity="critical", detected_at="2026-11-05T08:30:00+00:00", status="open", ticket=None, exception_expires=None),
        ),
        dict(
            id="CLD-0002", name="kv-kestrel-claims-prd", provider="azure", type="key_vault",
            region="centralindia", env="prod", app_id="APP-004", domain="Claims",
            resource_group="rg-kestrel-claims-prd", subscription="kestrel-prd-ci",
            approved=dict(public_network_access=False, soft_delete=True, purge_protection=True, rbac=True),
            deployed=dict(public_network_access=False, soft_delete=True, purge_protection=False, rbac=True),
            managed_by="terraform",
            tags=dict(owner="Claims Platform Engineering", cost_centre="CC-4410", data_classification="confidential"),
            created_at="2026-06-15T09:00:00+00:00", resource_guid="00000000-0000-0000-0000-000000000002",
            drift_meta=dict(severity="medium", detected_at="2026-11-04T14:15:00+00:00", status="open", ticket=None, exception_expires=None),
        ),
        dict(
            id="CLD-0003", name="vnet-kestrel-claims-prd", provider="azure", type="virtual_network",
            region="centralindia", env="prod", app_id="APP-004", domain="Claims",
            resource_group="rg-kestrel-claims-prd", subscription="kestrel-prd-ci",
            approved=dict(ddos=True, nsg_rule_ssh="deny", flow_logs=True),
            deployed=dict(ddos=True, nsg_rule_ssh="deny", flow_logs=True),
            managed_by="terraform",
            tags=dict(owner="Claims Platform Engineering", cost_centre="CC-4410", data_classification="confidential"),
            created_at="2026-06-15T09:00:00+00:00", resource_guid="00000000-0000-0000-0000-000000000003",
        ),
    ]

    # 9. Workflows
    workflows = [
        dict(
            id="WF-001", name="Claim Submission and Enquiries", domain="Claims",
            steps=[dict(app_id="APP-004", api_id="API-0001"), dict(app_id="APP-002", api_id="API-0001"), dict(app_id="APP-001", api_id=None)],
            apis=["API-0001"], apps=["APP-004", "APP-002", "APP-001"], volume_per_day=18500, sla_minutes=15,
        ),
        dict(
            id="WF-002", name="Claim Payment and Finance Reconciliation", domain="Claims",
            steps=[dict(app_id="APP-001", api_id=None), dict(app_id="APP-003", api_id=None), dict(app_id="APP-008", api_id=None)],
            apis=[], apps=["APP-001", "APP-003", "APP-008"], volume_per_day=4200, sla_minutes=240,
        ),
        dict(
            id="WF-003", name="Nightly Claims Batch and Regulatory Reporting", domain="Claims",
            steps=[dict(app_id="APP-001", api_id=None), dict(app_id="APP-006", api_id=None), dict(app_id="APP-005", api_id=None), dict(app_id="APP-007", api_id=None)],
            apis=[], apps=["APP-001", "APP-006", "APP-005", "APP-007"], volume_per_day=1200, sla_minutes=1440,
        ),
    ]

    # 10. Documents: empty in seed so all documents come from live Confluence / GitHub connectors (or uploaded markdown)
    documents: list[dict] = []

    # 11. Standards: include centralindia in STD-CLD-001 approved regions so centralindia passes STD-CLD-001 while eastus fails
    standards = []
    for s in G.STANDARDS:
        s_copy = dict(s)
        if s_copy["id"] == "STD-CLD-001":
            s_copy["statement"] = "Workloads must run in approved regions (Central India, West Europe, North Europe, UK South, East US 2)."
            s_copy["check"] = dict(attr="region", op="in", value=["centralindia", "westeurope", "northeurope", "uksouth", "eastus2"])
        standards.append(s_copy)

    patterns = [dict(id=i, name=n, category=c, summary=s, tags=t, adoption_count=u, status="approved") for i, n, c, s, t, u in G.PATTERNS]

    arb_submissions = [
        dict(
            id="ARB-2026-001", title="Claims Notification Service on Azure", domain="Claims",
            submitter="Claims Platform Engineering", submitter_id="OWN-001", stage="ai_reviewed",
            submitted_at="2026-10-28", arb_date="2026-11-18", linked_apps=["APP-001", "APP-002", "APP-004"],
            tier="tier1",
            summary="New event-driven Claims Notification Service on Azure consuming Claims API via Claims API Gateway.",
            nfr=dict(availability="99.95", rto_hours=2, rpo_minutes=15, latency_ms=500, throughput_tps=300, compliance=["IRDAI", "ISO27001"]),
            components=[
                dict(id="notif_storage", type="storage_account", encryption_at_rest=True, public_network_access=False, tls_min="1.2", region="centralindia", tags_complete=True, data_classification="confidential", retention_days=90, backup=True, logging=True, provisioned_by="terraform"),
                dict(id="apim", type="api_management", internet_facing=True, waf=True, tls_min="1.2"),
                dict(id="api", type="api", gateway=True, versioned=True, contract="openapi", auth="oauth2"),
            ],
        )
    ]

    uses_extra: list[dict] = []

    write("owners", owners)
    write("capabilities", capabilities)
    write("technologies", technologies)
    write("applications", applications)
    write("databases", databases)
    write("apis", apis)
    write("integrations", integrations)
    write("cloud_resources", cloud_resources)
    write("workflows", workflows)
    write("documents", documents)
    write("standards", standards)
    write("patterns", patterns)
    write("arb_submissions", arb_submissions)
    write("uses_extra", uses_extra)
    write("meta", dict(
        seed=42, reference_date=REF_DATE.isoformat(), enterprise="Kestrel Assurance Ltd",
        counts=dict(
            applications=len(applications), apis=len(apis), databases=len(databases),
            integrations=len(integrations), cloud_resources=len(cloud_resources),
            capabilities=len(capabilities), owners=len(owners), documents=len(documents),
            standards=len(standards), patterns=len(patterns), drift=2,
            arb=len(arb_submissions), workflows=len(workflows),
        ),
    ))
    return OUT


if __name__ == "__main__":
    out = main()
    print(f"Kestrel seed written to {out}")
