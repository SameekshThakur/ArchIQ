"""Reference architectures and patterns. Blueprint content is authored; the bundle is rendered with Jinja2."""

from __future__ import annotations

import io
import zipfile

from app.mock_ai.narration import render_template
from app.repositories.store import get_store

C = lambda n, r, t: dict(name=n, role=r, technology=t)  # noqa: E731

BLUEPRINTS = {
    "PAT-005": dict(
        title="RAG blueprint: governed retrieval over enterprise content",
        when=["Answers must be grounded in policy wordings, claim files or standards", "Content changes frequently, so fine-tuning is impractical", "Every answer needs a citation back to a source"],
        diagram="""flowchart LR
  U["Adjuster / Customer"] --> GWY["AI Gateway (APIM)"]
  GWY --> ORCH["Orchestrator service (AKS)"]
  ORCH --> RET["Retriever"]
  RET --> IDX[("Azure AI Search: hybrid index")]
  ING["Ingestion pipeline"] --> IDX
  SRC["SharePoint / Confluence / Claims docs"] --> ING
  ORCH --> AOAI["Azure OpenAI (private endpoint)"]
  ORCH --> GRD["Guardrails: PII redaction, content filter"]
  ORCH --> AUD[("Audit log: prompts and citations")]""",
        components=[C("AI Gateway", "Authentication, quotas, prompt and response audit", "Azure API Management"), C("Orchestrator", "Builds prompts, calls retrieval and the model, enforces guardrails", "Python 3.11 on AKS"),
                    C("Hybrid index", "Vector plus keyword retrieval with document-level security trimming", "Azure AI Search"), C("LLM", "Grounded answer generation", "Azure OpenAI (private endpoint)"),
                    C("Ingestion pipeline", "Chunking, enrichment and incremental indexing", "Databricks / Azure Functions"), C("Audit store", "Immutable record of prompts, sources and outputs", "Cosmos DB")],
        nfr=["Latency: first token under 2.5 s at p95; budget 600 ms for retrieval", "Security: private endpoints only, managed identity, no API keys (STD-SEC-014, STD-SEC-004)", "Quality: track groundedness and citation precision on a golden set before each release", "Compliance: log prompts and completions with PII redaction (STD-AI-005)"],
        anti=["Sending raw customer data to an external public LLM endpoint (STD-AI-004)", "Indexing documents without preserving source permissions", "Returning answers without citations", "Using the model's memory instead of retrieval for policy facts"],
        standards=["STD-AI-002", "STD-AI-005", "STD-SEC-014", "STD-TECH-001"]),
    "PAT-006": dict(
        title="Agentic AI reference architecture: guard-railed agents over enterprise APIs",
        when=["A task needs several tool calls across systems (look up policy, check coverage, draft a letter)", "A human must approve any action that affects a customer", "Actions must be fully auditable and reversible"],
        diagram="""flowchart TB
  USER["Case handler"] --> AGT["Agent runtime (planner + executor)"]
  AGT --> POL["Policy and guardrail engine"]
  AGT --> TOOLS["Tool registry (OpenAPI-described)"]
  TOOLS --> GW["API Management"]
  GW --> SYS["Claims, Policy and Customer system APIs"]
  AGT --> MEM[("Short-term memory + case context")]
  AGT --> LLM["Azure OpenAI"]
  AGT --> HITL["Human approval queue"]
  HITL --> AGT
  AGT --> TRACE[("Trace store: plans, tool calls, decisions")]""",
        components=[C("Agent runtime", "Plans, calls tools, and checkpoints state", "Python on AKS"), C("Tool registry", "Typed, least-privilege tools generated from OpenAPI contracts", "APIM + OpenAPI 3.1"),
                    C("Guardrail engine", "Policy checks on inputs, plans and outputs", "Rules + content filter"), C("Approval queue", "Human decision before any customer-affecting action", "ServiceNow / Teams"),
                    C("Trace store", "End-to-end replay of every step", "Cosmos DB"), C("LLM", "Reasoning and language", "Azure OpenAI")],
        nfr=["Autonomy level declared per tool: read-only, draft, or execute-with-approval", "Human in the loop for any claim, underwriting or pricing outcome (STD-AI-003)", "Per-run budget caps for tokens, tool calls and wall-clock time", "Idempotent tools with compensating actions"],
        anti=["Giving an agent broad service-account credentials", "Letting the agent finalise decisions without approval", "Tools that accept free-form SQL or shell", "No trace of intermediate plans and tool results"],
        standards=["STD-AI-003", "STD-AI-005", "STD-SEC-004", "STD-INT-004"]),
    "PAT-001": dict(
        title="API-led connectivity reference pattern",
        when=["Several channels need the same capability from systems you cannot change quickly", "Cross-domain consumers currently read databases directly", "You want one place to apply security, throttling and analytics"],
        diagram="""flowchart LR
  subgraph EXP["Experience"]
    W["Web / Mobile BFF"]
    B["Broker API"]
  end
  subgraph PROC["Process"]
    Q["Quote to Bind"]
    CL["Claim Intake"]
  end
  subgraph SYS["System"]
    P["Policy API"]
    C["Customer API v2"]
    K["Claims API"]
  end
  W --> Q
  B --> Q
  W --> CL
  Q --> P
  Q --> C
  CL --> K
  CL --> C
  P --> DB1[("Policy Master DB")]
  C --> DB2[("Customer Master")]
  K --> DB3[("ClaimCenter")]""",
        components=[C("Experience APIs", "Channel-specific shaping (BFF)", "Azure API Management / Node.js"), C("Process APIs", "Cross-system orchestration", "MuleSoft Anypoint"), C("System APIs", "Stable contracts over systems of record", "MuleSoft / Spring Boot 3"), C("Contract registry", "OpenAPI source of truth and linting", "APIM + Spectral")],
        nfr=["p95 latency budget split across layers (experience 100 ms, process 200 ms, system 300 ms)", "Version every API and publish deprecation dates (STD-INT-002)", "Cache read-heavy system APIs to shield the system of record", "Contract tests in CI for every consumer"],
        anti=["Experience APIs calling databases directly", "Process APIs that embed business rules owned by a system of record", "One giant API per system that mirrors its tables", "Skipping the gateway for 'internal' consumers"],
        standards=["STD-PAT-001", "STD-INT-001", "STD-INT-002", "STD-INT-004"]),
    "PAT-002": dict(
        title="Event-driven architecture reference pattern",
        when=["Several consumers need to react to the same business fact", "Producers must not depend on consumer availability", "You need replay, audit or near-real-time analytics"],
        diagram="""flowchart LR
  PROD["Policy Admin Core"] --> OUT["Outbox + CDC"]
  OUT --> K[["Kafka: policy.events.v1"]]
  REG["Schema registry"] -.-> K
  K --> A["Billing"]
  K --> B["Customer 360"]
  K --> C["Fraud scoring"]
  K --> D["Snowflake sink"]
  K --> DLQ[["Dead-letter topic"]]""",
        components=[C("Kafka cluster", "Durable ordered log", "Confluent on AKS"), C("Outbox / CDC", "Atomic publish with the database change", "Debezium"), C("Schema registry", "Compatibility-checked Avro/JSON schemas", "Confluent Schema Registry"), C("Consumers", "Idempotent handlers with retry and DLQ", "Java 17 / Spring Boot 3")],
        nfr=["Partition by business key to preserve ordering where it matters", "At-least-once delivery with idempotent consumers", "Retention long enough to replay after an incident (7 to 30 days)", "Consumer lag alerts and DLQ review runbook"],
        anti=["Publishing database rows instead of business events", "Request/reply over Kafka", "No schema governance, so consumers break silently", "Using events where strong consistency is required"],
        standards=["STD-PAT-002", "STD-INT-003", "STD-TECH-002"]),
    "PAT-003": dict(
        title="Strangler-fig migration pattern",
        when=["A legacy system cannot be replaced in a single release", "Capabilities can be carved off one at a time", "You need to keep the business running during the migration"],
        diagram="""flowchart LR
  C["Channels"] --> F["Facade / routing layer"]
  F -->|"migrated routes"| N["New services"]
  F -->|"remaining routes"| L["Legacy (Claims Mainframe Core)"]
  N --> ND[("New data store")]
  L --> LD[("DB2 z/OS")]
  SYNC["Change data capture"] --> ND
  LD --> SYNC""",
        components=[C("Facade", "Routes each capability to old or new", "Azure API Management"), C("New services", "Re-implemented capabilities", "AKS"), C("Data sync", "Keeps old and new stores consistent during transition", "CDC + Kafka"), C("Feature flags", "Gradual cut-over and instant rollback", "LaunchDarkly")],
        nfr=["Every migrated route has a rollback switch", "Shadow traffic compared before cut-over", "Decommission criteria agreed up front"],
        anti=["Big-bang cut-over", "Permanent dual-running with no retirement date", "Letting the facade accumulate business logic"],
        standards=["STD-PAT-003", "STD-PAT-001"]),
    "PAT-004": dict(
        title="CQRS and read models",
        when=["Read and write workloads have very different shapes", "Consumers need query views the system of record cannot serve efficiently"],
        diagram="""flowchart LR
  CMD["Command API"] --> W[("Write model")]
  W --> EV[["Domain events"]]
  EV --> PRJ["Projection builders"]
  PRJ --> R[("Read models")]
  QRY["Query API"] --> R""",
        components=[C("Command side", "Validates and applies changes", "Spring Boot 3"), C("Event stream", "Source for projections", "Kafka"), C("Projection builders", "Maintain query-optimised views", "Kafka Streams"), C("Read store", "Fast queries", "Cosmos DB / Elasticsearch")],
        nfr=["Define staleness SLO for read models", "Rebuild projections from the event log"], anti=["Applying CQRS to simple CRUD services", "Reading from the write model 'just this once'"], standards=["STD-PAT-002"]),
    "PAT-007": dict(
        title="Saga orchestration", when=["A business transaction spans several services without a distributed lock"],
        diagram="""flowchart LR
  S["Saga orchestrator"] --> A["Reserve payment"]
  S --> B["Issue policy"]
  S --> C["Send documents"]
  A -. compensate .-> A2["Refund"]
  B -. compensate .-> B2["Cancel policy"]""",
        components=[C("Orchestrator", "Tracks saga state and drives compensation", "Temporal / Durable Functions"), C("Participants", "Idempotent local transactions", "Microservices")],
        nfr=["Every step has a compensating action", "Persist saga state durably"], anti=["Two-phase commit across services", "Compensations that are not idempotent"], standards=["STD-PAT-002"]),
    "PAT-008": dict(
        title="Transactional outbox", when=["A service must update its database and publish an event atomically"],
        diagram="""flowchart LR
  SVC["Service"] --> DB[("Table + outbox table")]
  DB --> CDC["CDC relay"]
  CDC --> K[["Kafka"]]""",
        components=[C("Outbox table", "Events written in the same transaction", "PostgreSQL 15"), C("Relay", "Reads and publishes outbox rows", "Debezium")],
        nfr=["Relay is at-least-once; consumers deduplicate"], anti=["Dual writes to the database and Kafka"], standards=["STD-PAT-002"]),
    "PAT-009": dict(
        title="Anti-corruption layer", when=["A clean domain model must integrate with a legacy model"],
        diagram="""flowchart LR
  N["New domain model"] --> ACL["Anti-corruption layer"]
  ACL --> L["Legacy API / COBOL copybooks"]""",
        components=[C("Translator", "Maps legacy structures to the domain model", "Java 17"), C("Adapter", "Protocol bridging (MQ, SOAP, copybooks)", "MuleSoft")],
        nfr=["Keep the ACL stateless and thin"], anti=["Letting legacy field names leak into new services"], standards=["STD-PAT-003"]),
    "PAT-010": dict(
        title="Backend-for-frontend", when=["Mobile and web channels need different payloads"],
        diagram="""flowchart LR
  M["Mobile app"] --> BM["Mobile BFF"]
  W["Web app"] --> BW["Web BFF"]
  BM --> API["Process APIs"]
  BW --> API""",
        components=[C("BFF per channel", "Aggregates and shapes API responses", "Node.js 20")], nfr=["One team owns the channel and its BFF"], anti=["A single shared BFF for every channel"], standards=["STD-PAT-001"]),
    "PAT-011": dict(
        title="Medallion lakehouse", when=["Governed analytics and ML on large, mixed-quality data"],
        diagram="""flowchart LR
  SRC["Sources"] --> BR[("Bronze: raw")]
  BR --> SI[("Silver: cleansed")]
  SI --> GO[("Gold: curated")]
  GO --> BI["Power BI"]
  GO --> ML["Feature store"]""",
        components=[C("Bronze/Silver/Gold zones", "Progressive quality", "ADLS Gen2 + Delta"), C("Pipelines", "Declarative transformations with expectations", "Databricks")],
        nfr=["Quality gates on promotion between layers", "Lineage registered in the catalog"], anti=["Business users querying bronze"], standards=["STD-DAT-003"]),
    "PAT-012": dict(
        title="Zero-trust private connectivity", when=["PaaS services hold enterprise data"],
        diagram="""flowchart LR
  APP["Workload (managed identity)"] --> PE["Private endpoint"]
  PE --> PAAS["Azure OpenAI / Storage / Key Vault"]
  DNS["Private DNS zone"] -.-> PE
  PUB["Public network access: Disabled"] -.x PAAS""",
        components=[C("Private endpoints", "Network path into PaaS", "Azure Private Link"), C("Private DNS", "Name resolution to private IPs", "Azure DNS"), C("Policy", "Deny public network access", "Azure Policy")],
        nfr=["Policy blocks creation of public PaaS endpoints (STD-SEC-014)"], anti=["Allow-listing public IPs instead of private endpoints"], standards=["STD-SEC-014", "STD-SEC-004"]),
}

BUNDLE_MD = """# {{ title }}

> Generated by ArchIQ for Northwind Assurance. Pattern `{{ pattern_id }}`.

## When to use

{% for w in when %}
- {{ w }}
{% endfor %}

## Reference diagram

```mermaid
{{ diagram }}
```

## Components

| Component | Role | Technology |
|---|---|---|
{% for c in components %}
| {{ c.name }} | {{ c.role }} | {{ c.technology }} |
{% endfor %}

## Non-functional guidance

{% for n in nfr %}
- {{ n }}
{% endfor %}

## Anti-patterns

{% for a in anti %}
- {{ a }}
{% endfor %}

## Related standards

{% for s in standards %}
- `{{ s.id }}`: {{ s.title }}
{% endfor %}
"""


def generate(pattern_id: str) -> dict | None:
    s = get_store()
    meta = next((p for p in s.patterns if p["id"] == pattern_id), None)
    bp = BLUEPRINTS.get(pattern_id)
    if not meta or not bp:
        return None
    stds = [dict(id=x, title=s.standards_by_id[x]["title"]) for x in bp["standards"] if x in s.standards_by_id]
    md = render_template(BUNDLE_MD, title=bp["title"], pattern_id=pattern_id, when=bp["when"], diagram=bp["diagram"], components=bp["components"], nfr=bp["nfr"], anti=bp["anti"], standards=stds)
    return dict(pattern_id=pattern_id, name=meta["name"], category=meta["category"], title=bp["title"], when_to_use=bp["when"], diagram=bp["diagram"], components=bp["components"],
                nfr_guidance=bp["nfr"], anti_patterns=bp["anti"], standards=stds, markdown=md, mermaid=bp["diagram"], filename=f"{pattern_id.lower()}-{meta['name'].lower().replace(' ', '-')}")


def bundle_zip(pattern_id: str) -> bytes | None:
    bp = generate(pattern_id)
    if not bp:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{bp['filename']}/README.md", bp["markdown"])
        z.writestr(f"{bp['filename']}/diagram.mmd", bp["mermaid"] + "\n")
    return buf.getvalue()
