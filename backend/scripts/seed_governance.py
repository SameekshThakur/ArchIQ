"""Static governance data: standards catalogue, pattern metadata, ARB submissions."""

from __future__ import annotations

PAAS_TYPES = ["azure_openai", "storage_account", "key_vault", "sql_database", "postgres", "cosmos_db", "data_lake", "ai_search"]
DATA_TYPES = ["storage_account", "sql_database", "postgres", "cosmos_db", "data_lake"]
COMPUTE_TYPES = ["app_service", "aks_cluster", "function"]


def S(id, title, category, kind, severity, statement, applies=None, check=None, remediation="", technology=None, status=None, when=None):
    return dict(
        id=id, title=title, category=category, kind=kind, severity=severity, statement=statement,
        applies_to=applies or [], check=check, when=when, remediation=remediation, technology=technology, status=status,
        owner="Architecture Review Board", effective="2024-01-01",
    )


STANDARDS = [
    # ---- security
    S("STD-SEC-001", "Encryption at rest for data stores", "security", "policy", "high", "All stores holding enterprise data must enable encryption at rest.", DATA_TYPES, dict(attr="encryption_at_rest", op="eq", value=True), "Enable platform encryption at rest (TDE / SSE) on the resource."),
    S("STD-SEC-002", "TLS 1.2 or higher in transit", "security", "policy", "high", "All network endpoints must enforce TLS 1.2 or higher.", PAAS_TYPES + COMPUTE_TYPES + ["api_management"], dict(attr="tls_min", op="in", value=["1.2", "1.3"]), "Set the minimum TLS version to 1.2 and disable legacy protocols."),
    S("STD-SEC-003", "Secrets held in Key Vault", "security", "policy", "high", "Application secrets must be stored in Azure Key Vault, not in configuration or environment variables.", COMPUTE_TYPES, dict(attr="secrets_store", op="eq", value="key_vault"), "Move secrets to Key Vault and reference them through managed identity."),
    S("STD-SEC-004", "Managed identity or OAuth for service authentication", "security", "policy", "high", "Service-to-service access must use managed identity or OAuth 2.0; static API keys are not permitted.", COMPUTE_TYPES + ["azure_openai", "api"], dict(attr="auth", op="in", value=["managed_identity", "oauth2", "mtls"]), "Disable local/key authentication and assign a managed identity with least-privilege roles."),
    S("STD-SEC-005", "WAF in front of internet-facing endpoints", "security", "policy", "high", "Internet-facing applications must be fronted by a Web Application Firewall.", ["app_service", "api_management", "web_app"], dict(attr="waf", op="eq", value=True), "Place Azure Front Door / Application Gateway WAF in front of the endpoint.", when=dict(attr="internet_facing", op="eq", value=True)),
    S("STD-SEC-006", "Security logging to the enterprise SIEM", "security", "policy", "medium", "Security-relevant logs must stream to the enterprise SIEM.", PAAS_TYPES + COMPUTE_TYPES, dict(attr="logging", op="eq", value=True), "Enable diagnostic settings and forward to the Sentinel workspace."),
    S("STD-SEC-007", "No shared or password credentials", "security", "policy", "high", "Shared accounts and password-based service credentials are prohibited.", ["sql_database", "postgres", "app_service", "api"], dict(attr="auth", op="ne", value="password"), "Replace password authentication with Entra ID or managed identity."),
    S("STD-SEC-009", "PII masked outside production", "security", "policy", "medium", "Personal data must be masked in non-production environments.", DATA_TYPES, dict(attr="pii_masking", op="eq", value=True), "Apply dynamic data masking or synthetic data in lower environments.", when=dict(attr="pii", op="eq", value=True)),
    S("STD-SEC-010", "Data classification declared", "security", "policy", "low", "Every data store must declare a data classification.", DATA_TYPES, dict(attr="data_classification", op="present"), "Tag the resource with a data classification label."),
    S("STD-SEC-012", "Customer-managed keys for restricted data", "security", "policy", "medium", "Restricted data must be encrypted with customer-managed keys.", DATA_TYPES, dict(attr="cmk", op="eq", value=True), "Bind the resource to a Key Vault key and enable CMK.", when=dict(attr="data_classification", op="eq", value="restricted")),
    S("STD-SEC-014", "PaaS services reached via Private Endpoint only", "security", "policy", "critical", "PaaS services holding enterprise data must disable public network access and be reached through a Private Endpoint.", PAAS_TYPES, dict(attr="public_network_access", op="eq", value=False), "Set public network access to Disabled and create a Private Endpoint in the workload subnet."),
    S("STD-SEC-015", "No direct cross-domain database access", "security", "policy", "high", "Applications must not read or write another domain's database directly; use APIs or events.", ["integration"], dict(attr="style", op="ne", value="direct_db"), "Expose the data through an API or publish change events and consume those instead."),
    # ---- integration
    S("STD-INT-001", "APIs published through the gateway", "integration", "policy", "medium", "All APIs consumed outside their owning team must be published through the API gateway.", ["api"], dict(attr="gateway", op="eq", value=True), "Register the API in Azure API Management and route consumers through it."),
    S("STD-INT-002", "APIs are versioned", "integration", "policy", "medium", "APIs must carry an explicit version and a deprecation policy.", ["api"], dict(attr="versioned", op="eq", value=True), "Adopt URI or header versioning and publish a deprecation schedule."),
    S("STD-INT-003", "Cross-domain integration via API or event", "integration", "policy", "high", "Cross-domain integration must use an API or an event; file drops and point-to-point links need an exception.", ["integration"], dict(attr="style", op="in", value=["api", "event", "esb"]), "Re-platform the integration onto an API or Kafka topic."),
    S("STD-INT-004", "Contract-first APIs", "integration", "policy", "low", "APIs must have an OpenAPI/AsyncAPI contract.", ["api"], dict(attr="contract", op="in", value=["openapi", "asyncapi"]), "Publish an OpenAPI 3.x contract and validate it in CI."),
    S("STD-INT-005", "Async messaging for fire-and-forget flows", "integration", "policy", "low", "Notifications and non-blocking flows should be asynchronous.", [], None, "Publish an event rather than calling the consumer synchronously."),
    # ---- data
    S("STD-DAT-001", "System of record declared per entity", "data", "policy", "medium", "Each business entity must have exactly one declared system of record.", [], None, "Nominate one system of record and mark the others as consumers."),
    S("STD-DAT-002", "Retention policy applied", "data", "policy", "low", "Data stores must define and enforce a retention policy.", DATA_TYPES, dict(attr="retention_days", op="present"), "Define retention in line with the regulatory schedule."),
    S("STD-DAT-003", "Lineage registered in the catalog", "data", "policy", "low", "Critical datasets must be registered with lineage in the data catalog.", [], None, "Register the dataset in Collibra and link upstream sources."),
    S("STD-DAT-004", "Personal data minimisation", "data", "policy", "medium", "Only the personal data required for the purpose may be collected or propagated.", [], None, "Remove unneeded attributes from payloads and replicas."),
    # ---- cloud
    S("STD-CLD-001", "Approved cloud regions", "cloud", "policy", "medium", "Workloads must run in approved regions (West Europe, North Europe, UK South, East US 2).", COMPUTE_TYPES + PAAS_TYPES, dict(attr="region", op="in", value=["westeurope", "northeurope", "uksouth", "eastus2"]), "Redeploy to an approved region or raise a data-residency exception."),
    S("STD-CLD-002", "Infrastructure provisioned as code", "cloud", "policy", "medium", "Cloud resources must be provisioned by Terraform or Bicep through the pipeline.", COMPUTE_TYPES + PAAS_TYPES, dict(attr="provisioned_by", op="in", value=["terraform", "bicep"]), "Import the resource into IaC and disable portal changes."),
    S("STD-CLD-003", "Mandatory resource tags", "cloud", "policy", "low", "Resources must carry owner, cost-centre and data-classification tags.", COMPUTE_TYPES + PAAS_TYPES, dict(attr="tags_complete", op="eq", value=True), "Apply the tag policy initiative."),
    S("STD-CLD-004", "Deployed into the landing zone", "cloud", "policy", "medium", "Workloads deploy into a governed landing-zone subscription.", [], None, "Move the workload into the matching landing-zone subscription."),
    # ---- AI
    S("STD-AI-002", "Content filtering enabled for LLM workloads", "ai", "policy", "high", "LLM deployments must enable content filtering at standard or strict level.", ["azure_openai"], dict(attr="content_filter", op="in", value=["standard", "strict"]), "Attach a content filter policy to the deployment."),
    S("STD-AI-003", "Human in the loop for claim decisions", "ai", "policy", "high", "AI must not make or finalise claim, underwriting or pricing decisions without human review.", ["azure_openai", "ai_agent"], dict(attr="human_in_loop", op="eq", value=True), "Add an approval step before AI output affects a customer decision."),
    S("STD-AI-004", "No external public LLM APIs", "ai", "policy", "critical", "Calls to external public LLM APIs are prohibited; use the enterprise Azure OpenAI service.", ["llm_api_external"], dict(attr="never", op="eq", value=True), "Route inference through Azure OpenAI behind the AI Gateway."),
    S("STD-AI-005", "Prompts and responses audited", "ai", "policy", "medium", "Prompts and completions must be logged for audit with PII redaction.", ["azure_openai", "ai_agent"], dict(attr="audit_logging", op="eq", value=True), "Enable the AI Gateway audit sink."),
    # ---- resilience
    S("STD-RES-001", "Multi-zone deployment for tier-1 services", "resilience", "policy", "high", "Tier-1 services must be deployed across availability zones.", COMPUTE_TYPES + ["sql_database", "postgres", "cosmos_db"], dict(attr="multi_az", op="eq", value=True), "Enable zone redundancy for the service.", when=dict(attr="tier", op="in", value=["tier1", "critical"])),
    S("STD-RES-002", "Backups configured and tested", "resilience", "policy", "medium", "Data stores must have automated backups with a tested restore.", DATA_TYPES, dict(attr="backup", op="eq", value=True), "Enable automated backup and schedule a quarterly restore test."),
    S("STD-RES-003", "RTO and RPO declared", "resilience", "policy", "medium", "Every design must declare RTO and RPO targets.", [], None, "Add RTO/RPO to the NFR section and validate against the tier."),
    S("STD-RES-004", "No single instance for tier-1 workloads", "resilience", "policy", "high", "Tier-1 workloads must not run as a single instance.", COMPUTE_TYPES, dict(attr="instances", op="gte", value=2), "Run at least two instances behind a load balancer.", when=dict(attr="tier", op="in", value=["tier1", "critical"])),
    # ---- approved technology radar
    S("STD-TECH-001", "Azure OpenAI", "technology", "approved_technology", "info", "Azure OpenAI is the approved enterprise LLM service.", technology="Azure OpenAI", status="approved"),
    S("STD-TECH-002", "Apache Kafka (Confluent)", "technology", "approved_technology", "info", "Kafka is the approved event backbone.", technology="Apache Kafka", status="approved"),
    S("STD-TECH-003", "PostgreSQL 15", "technology", "approved_technology", "info", "PostgreSQL 15 is the approved open-source relational database.", technology="PostgreSQL 15", status="approved"),
    S("STD-TECH-004", "MuleSoft Anypoint", "technology", "approved_technology", "info", "MuleSoft is approved for system and process APIs.", technology="MuleSoft Anypoint", status="approved"),
    S("STD-TECH-005", "Java 8", "technology", "approved_technology", "medium", "Java 8 is deprecated; tolerated until 2027 for existing systems only.", technology="Java 8", status="deprecated"),
    S("STD-TECH-006", "Oracle 12c", "technology", "approved_technology", "high", "Oracle 12c is out of vendor support and prohibited for new use.", technology="Oracle 12c", status="prohibited"),
    S("STD-TECH-007", "SQL Server 2014", "technology", "approved_technology", "high", "SQL Server 2014 is out of support and prohibited.", technology="SQL Server 2014", status="prohibited"),
    S("STD-TECH-008", "Windows Server 2012", "technology", "approved_technology", "high", "Windows Server 2012 is out of support and prohibited.", technology="Windows Server 2012", status="prohibited"),
    S("STD-TECH-009", "Node.js 18", "technology", "approved_technology", "medium", "Node.js 18 is end of life; upgrade to Node.js 20.", technology="Node.js 18", status="deprecated"),
    # ---- approved patterns
    S("STD-PAT-001", "API-led connectivity for synchronous integration", "patterns", "pattern", "info", "Synchronous cross-domain integration follows system, process and experience API layering."),
    S("STD-PAT-002", "Event-driven architecture for cross-domain propagation", "patterns", "pattern", "info", "State changes that other domains care about are published as events on Kafka."),
    S("STD-PAT-003", "Strangler-fig for legacy replacement", "patterns", "pattern", "info", "Legacy systems are replaced incrementally behind a facade, never by big-bang cut-over."),
]

PATTERNS = [
    ("PAT-001", "API-led connectivity", "integration", "Layered system, process and experience APIs that decouple consumers from systems of record.", ["api", "mulesoft", "gateway"], 24),
    ("PAT-002", "Event-driven architecture", "integration", "Domain events on a durable log so producers and consumers evolve independently.", ["kafka", "events", "async"], 18),
    ("PAT-003", "Strangler-fig migration", "modernization", "Incrementally route capabilities from a legacy system to a new implementation behind a facade.", ["legacy", "migration"], 11),
    ("PAT-004", "CQRS and read models", "data", "Separate write models from query-optimised read models fed by events.", ["cqrs", "read-model"], 7),
    ("PAT-005", "Retrieval-augmented generation (RAG)", "ai", "Ground LLM answers in enterprise content through retrieval over a governed index.", ["rag", "llm", "azure-openai"], 9),
    ("PAT-006", "Agentic AI reference architecture", "ai", "Tool-using agents with guardrails, human approval and full audit over enterprise APIs.", ["agents", "llm", "guardrails"], 4),
    ("PAT-007", "Saga orchestration", "integration", "Coordinate multi-service business transactions with compensating actions.", ["saga", "orchestration"], 6),
    ("PAT-008", "Transactional outbox", "integration", "Publish events atomically with a database change using an outbox table.", ["outbox", "reliability"], 8),
    ("PAT-009", "Anti-corruption layer", "modernization", "Translate between a legacy model and a clean domain model at the boundary.", ["acl", "legacy"], 5),
    ("PAT-010", "Backend-for-frontend", "integration", "A tailored API facade per experience channel.", ["bff", "api"], 10),
    ("PAT-011", "Medallion lakehouse", "data", "Bronze, silver and gold layers with governed promotion of data quality.", ["lakehouse", "databricks"], 6),
    ("PAT-012", "Zero-trust private connectivity", "security", "Private endpoints, managed identity and policy-enforced network isolation for PaaS.", ["private-endpoint", "zero-trust"], 15),
]


def comp(id, type, **attrs):
    return dict(id=id, type=type, **attrs)


ARB = [
    dict(id="ARB-2026-001", title="Claims Copilot GenAI Assistant", domain="Claims", submitter="Olivia Brennan", stage="ai_reviewed",
         submitted_at="2026-10-21", arb_date="2026-11-12", apps=["CCOP", "AOAI", "AIGW"], tier="tier2",
         summary="Generative AI assistant that helps adjusters check coverage and summarise claim files.",
         nfr=dict(availability="99.9", rto_hours=4, rpo_minutes=15, latency_ms=2500, throughput_tps=40, compliance=["GDPR", "SOC2"]),
         components=[
             comp("llm", "azure_openai", technology="Azure OpenAI", public_network_access=True, auth="api_key", content_filter="standard", human_in_loop=False, audit_logging=False, region="westeurope", tls_min="1.2", logging=True, provisioned_by="terraform"),
             comp("search", "ai_search", public_network_access=False),
             comp("kv", "key_vault", public_network_access=False),
             comp("api", "app_service", secrets_store="env_vars", auth="managed_identity", tls_min="1.2", region="westeurope", logging=True, internet_facing=False, provisioned_by="terraform", tier="tier2"),
             comp("apim", "api_management", internet_facing=True, waf=True, tls_min="1.2"),
         ]),
    dict(id="ARB-2026-002", title="Customer 360 Event Streaming", domain="Customer & Distribution", submitter="Elena Petrova", stage="arb_scheduled",
         submitted_at="2026-10-14", arb_date="2026-11-10", apps=["C360", "KAFKA", "MDM", "SFC"], tier="tier1",
         summary="Publish customer change events on Kafka and build a unified customer view for downstream domains.",
         nfr=dict(availability="99.95", rto_hours=2, rpo_minutes=5, latency_ms=500, throughput_tps=1200, compliance=["GDPR"]),
         components=[
             comp("kafka", "kafka", technology="Apache Kafka", tls_min="1.2", logging=True, public_network_access=False),
             comp("svc", "aks_cluster", secrets_store="key_vault", auth="managed_identity", tls_min="1.2", multi_az=True, instances=3, tier="tier1", region="westeurope", logging=True, provisioned_by="terraform"),
             comp("store", "cosmos_db", encryption_at_rest=True, public_network_access=False, backup=True, multi_az=True, tier="tier1", data_classification="restricted", cmk=True, retention_days=2555, pii=True, pii_masking=True, region="westeurope", tls_min="1.2", logging=True, provisioned_by="terraform"),
             comp("apim", "api_management", internet_facing=False, tls_min="1.2"),
             comp("api", "api", gateway=True, versioned=True, contract="openapi", auth="oauth2"),
         ]),
    dict(id="ARB-2026-003", title="Oracle 12c Retirement: Policy Master DB", domain="Policy Admin", submitter="Sarah Whitfield", stage="draft",
         submitted_at="2026-11-02", arb_date=None, apps=["PAC", "PDG", "UWB", "COLM", "ACE"], tier="tier1",
         summary="Migrate the Policy Master database off Oracle 12c and decouple direct consumers.",
         nfr=dict(availability="99.95", rto_hours=1, compliance=["SOX"]),
         components=[
             comp("target", "postgres", technology="PostgreSQL 15", encryption_at_rest=True, public_network_access=False, backup=True, multi_az=True, tier="tier1", data_classification="restricted", cmk=False, retention_days=3650, pii=True, pii_masking=False, region="westeurope", tls_min="1.2", logging=True, provisioned_by="terraform"),
             comp("int1", "integration", style="direct_db", source="Underwriting Workbench"),
             comp("int2", "integration", style="direct_db", source="Collections Manager"),
             comp("int3", "integration", style="file_batch", source="Agent Commission Engine"),
             comp("oldsrc", "sql_database", technology="Oracle 12c", encryption_at_rest=True, public_network_access=False),
         ]),
    dict(id="ARB-2026-004", title="Claims Intake Modernisation (API-led)", domain="Claims", submitter="Ananya Rao", stage="conditions",
         submitted_at="2026-09-30", arb_date="2026-10-22", apps=["CIP", "GWCC", "CNS", "FSE"], tier="tier1",
         summary="Introduce system and process APIs in front of ClaimCenter and retire the direct Oracle 12c reads.",
         nfr=dict(availability="99.95", rto_hours=2, rpo_minutes=5, latency_ms=800, throughput_tps=350, compliance=["GDPR", "SOC2"]),
         components=[
             comp("apim", "api_management", internet_facing=True, waf=True, tls_min="1.2"),
             comp("exp", "app_service", secrets_store="key_vault", auth="managed_identity", tls_min="1.2", multi_az=True, instances=3, tier="tier1", internet_facing=True, waf=True, region="westeurope", logging=True, provisioned_by="terraform"),
             comp("proc", "aks_cluster", secrets_store="key_vault", auth="managed_identity", tls_min="1.2", multi_az=True, instances=2, tier="tier1", region="westeurope", logging=True, provisioned_by="bicep"),
             comp("sysapi", "api", gateway=True, versioned=True, contract="openapi", auth="oauth2"),
             comp("int", "integration", style="direct_db", source="Fraud Scoring Engine"),
             comp("db", "postgres", technology="PostgreSQL 15", encryption_at_rest=True, public_network_access=False, backup=True, multi_az=True, tier="tier1", data_classification="confidential", retention_days=2555, region="westeurope", tls_min="1.2", logging=True, provisioned_by="terraform"),
         ]),
    dict(id="ARB-2026-005", title="Underwriting Rules Externalisation", domain="Underwriting", submitter="Lucia Fernandez", stage="approved",
         submitted_at="2026-08-12", arb_date="2026-09-03", apps=["UWB", "RSS", "RTE"], tier="tier2",
         summary="Move underwriting rules into a versioned decision service exposed by API.",
         nfr=dict(availability="99.9", rto_hours=4, rpo_minutes=30, latency_ms=300, throughput_tps=250, compliance=["SOC2"]),
         components=[
             comp("svc", "aks_cluster", secrets_store="key_vault", auth="managed_identity", tls_min="1.2", multi_az=True, instances=3, tier="tier2", region="northeurope", logging=True, provisioned_by="terraform"),
             comp("api", "api", gateway=True, versioned=True, contract="openapi", auth="oauth2"),
             comp("db", "postgres", technology="PostgreSQL 15", encryption_at_rest=True, public_network_access=False, backup=True, data_classification="confidential", retention_days=2555, region="northeurope", tls_min="1.2", logging=True, provisioned_by="terraform"),
         ]),
    dict(id="ARB-2026-006", title="Agent Portal Single Sign-On", domain="Customer & Distribution", submitter="Daniel Okafor", stage="approved",
         submitted_at="2026-07-22", arb_date="2026-08-14", apps=["AGP", "IDP"], tier="tier2",
         summary="Federate the agent portal with the enterprise identity platform.",
         nfr=dict(availability="99.9", rto_hours=4, rpo_minutes=60, latency_ms=400, throughput_tps=120, compliance=["SOC2"]),
         components=[
             comp("web", "app_service", secrets_store="key_vault", auth="oauth2", tls_min="1.2", internet_facing=True, waf=True, region="westeurope", logging=True, provisioned_by="terraform", tier="tier2"),
             comp("kv", "key_vault", public_network_access=False, tls_min="1.2", logging=True, region="westeurope", provisioned_by="terraform"),
         ]),
    dict(id="ARB-2026-007", title="Regulatory Reporting Lakehouse", domain="Billing & Finance", submitter="Priya Venkataraman", stage="arb_scheduled",
         submitted_at="2026-10-18", arb_date="2026-11-19", apps=["RRH", "SNOW", "DBX", "SAP"], tier="tier2",
         summary="Consolidate regulatory reporting onto a medallion lakehouse with governed lineage.",
         nfr=dict(availability="99.5", rto_hours=8, rpo_minutes=240, throughput_tps=60, compliance=["SOX", "Solvency II"]),
         components=[
             comp("lake", "data_lake", encryption_at_rest=True, public_network_access=True, backup=True, data_classification="restricted", cmk=True, retention_days=3650, pii=False, region="westeurope", tls_min="1.2", logging=True, provisioned_by="terraform"),
             comp("job", "function", secrets_store="key_vault", auth="managed_identity", tls_min="1.2", region="westeurope", logging=True, provisioned_by="terraform"),
         ]),
    dict(id="ARB-2026-008", title="Mainframe Claims API Facade", domain="Claims", submitter="Victor Alvarez", stage="ai_reviewed",
         submitted_at="2026-10-27", arb_date="2026-11-17", apps=["CMF", "CPH", "GWCC"], tier="tier1",
         summary="Strangler-fig facade exposing mainframe claim settlement as REST APIs.",
         nfr=dict(availability="99.95", rto_hours=2, rpo_minutes=15, latency_ms=900, throughput_tps=180, compliance=["SOX"]),
         components=[
             comp("facade", "aks_cluster", secrets_store="key_vault", auth="managed_identity", tls_min="1.2", multi_az=True, instances=1, tier="tier1", region="westeurope", logging=True, provisioned_by="terraform"),
             comp("api", "api", gateway=True, versioned=True, contract="openapi", auth="mtls"),
             comp("mq", "integration", style="point_to_point", source="Claims Mainframe Core"),
         ]),
    dict(id="ARB-2026-009", title="Customer Notification Consolidation", domain="Customer & Distribution", submitter="Aisha Khan", stage="rejected",
         submitted_at="2026-06-30", arb_date="2026-07-24", apps=["CNH", "CNS"], tier="tier3",
         summary="Introduce a third notification service for marketing campaigns.",
         nfr=dict(availability="99.5", compliance=["GDPR"]),
         components=[
             comp("svc", "app_service", secrets_store="env_vars", auth="password", tls_min="1.0", region="westeurope", logging=False, provisioned_by="portal", tier="tier3"),
             comp("llm", "llm_api_external", technology="Public LLM API", never=False),
         ]),
    dict(id="ARB-2026-010", title="Fraud Detection Real-time Scoring", domain="Claims", submitter="Olivia Brennan", stage="draft",
         submitted_at="2026-11-03", arb_date=None, apps=["FSE", "DBX", "KAFKA", "FST"], tier="tier1",
         summary="Stream claim events to a real-time fraud model with sub-second scoring.",
         nfr=dict(availability="99.95", latency_ms=400, throughput_tps=900, compliance=["GDPR"]),
         components=[
             comp("kafka", "kafka", technology="Apache Kafka", tls_min="1.2", logging=True, public_network_access=False),
             comp("score", "aks_cluster", secrets_store="key_vault", auth="managed_identity", tls_min="1.2", multi_az=True, instances=3, tier="tier1", region="westeurope", logging=True, provisioned_by="terraform"),
             comp("store", "cosmos_db", encryption_at_rest=True, public_network_access=False, backup=True, multi_az=True, tier="tier1", data_classification="confidential", retention_days=1095, region="westeurope", tls_min="1.2", logging=True, provisioned_by="terraform"),
         ]),
]
