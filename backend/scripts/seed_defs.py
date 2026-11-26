"""Static definitions for the fictional enterprise "Northwind Assurance".

Everything here is hand-authored so the story facts are explicit and auditable:
  * Oracle 12c is used by exactly 9 applications, 4 of which support Claims.
  * Customer API v2 is consumed by exactly 14 applications.
  * SAP -> MuleSoft -> Salesforce -> Snowflake is a real integration chain.
The generator (generate_seed.py) layers deterministic, seeded data on top.
"""

from __future__ import annotations

DOMAINS = [
    "Claims",
    "Policy Admin",
    "Underwriting",
    "Billing & Finance",
    "Customer & Distribution",
    "Data & Analytics",
    "Integration & Platform",
    "Corporate Services",
]

# ---------------------------------------------------------------- owners
# (name, team, domain, role)
OWNERS = [
    ("Avadhi Jain", "Enterprise Architecture", "Corporate Services", "Chief Architect"),
    ("Rohan Kulkarni", "Claims Platform", "Claims", "Engineering Manager"),
    ("Ananya Rao", "Claims Digital", "Claims", "Product Owner"),
    ("Dev Patel", "Claims Integration", "Claims", "Tech Lead"),
    ("Sarah Whitfield", "Policy Platform", "Policy Admin", "Head of Platform"),
    ("Marcus Chen", "Policy Services", "Policy Admin", "Engineering Manager"),
    ("Lucia Fernandez", "Underwriting Technology", "Underwriting", "Head of Technology"),
    ("James O'Connor", "Pricing & Rating", "Underwriting", "Tech Lead"),
    ("Priya Venkataraman", "Finance Systems", "Billing & Finance", "Head of Finance Systems"),
    ("Thomas Becker", "Billing Operations", "Billing & Finance", "Product Owner"),
    ("Hannah Müller", "Treasury & Payments", "Billing & Finance", "Engineering Manager"),
    ("Aisha Khan", "Customer Experience", "Customer & Distribution", "Head of Digital"),
    ("Daniel Okafor", "Distribution Technology", "Customer & Distribution", "Engineering Manager"),
    ("Elena Petrova", "Customer Data (MDM)", "Customer & Distribution", "Data Product Owner"),
    ("Kenji Tanaka", "Data Platform", "Data & Analytics", "Head of Data Platform"),
    ("Olivia Brennan", "AI & Automation", "Data & Analytics", "Head of AI"),
    ("Rahul Mehta", "Integration Platform", "Integration & Platform", "Integration Architect"),
    ("Sofia Rossi", "Cloud Platform", "Integration & Platform", "Cloud Platform Lead"),
    ("Noah Williams", "Security Engineering", "Integration & Platform", "Security Architect"),
    ("Chloe Dubois", "Site Reliability", "Integration & Platform", "SRE Lead"),
    ("Arjun Nambiar", "Corporate Applications", "Corporate Services", "Engineering Manager"),
    ("Grace Liu", "HR Technology", "Corporate Services", "Product Owner"),
    ("Victor Alvarez", "Mainframe Services", "Claims", "Mainframe Lead"),
    ("Fatima Hassan", "Data Governance", "Data & Analytics", "Governance Lead"),
    ("Liam Gallagher", "Vendor Management", "Corporate Services", "Vendor Manager"),
]

# ---------------------------------------------------------- capabilities
# (id, name, parent, level)
CAPABILITIES = [
    ("CAP-CLM", "Claims Management", None, 1),
    ("CAP-UW", "Underwriting", None, 1),
    ("CAP-POL", "Policy Administration", None, 1),
    ("CAP-BIL", "Billing & Collections", None, 1),
    ("CAP-CUS", "Customer & Distribution", None, 1),
    ("CAP-FIN", "Finance & Reporting", None, 1),
    ("CAP-DAT", "Data & Insight", None, 1),
    ("CAP-COR", "Corporate Services", None, 1),
    ("CAP-CLM-FNOL", "First Notice of Loss", "CAP-CLM", 2),
    ("CAP-CLM-ADJ", "Claims Adjudication", "CAP-CLM", 2),
    ("CAP-CLM-PAY", "Claims Payments", "CAP-CLM", 2),
    ("CAP-CLM-FRD", "Fraud Detection", "CAP-CLM", 2),
    ("CAP-UW-RSK", "Risk Assessment", "CAP-UW", 2),
    ("CAP-UW-PRC", "Pricing & Rating", "CAP-UW", 2),
    ("CAP-UW-REI", "Reinsurance", "CAP-UW", 2),
    ("CAP-POL-ISS", "Policy Issuance", "CAP-POL", 2),
    ("CAP-POL-END", "Endorsements & Renewals", "CAP-POL", 2),
    ("CAP-POL-DOC", "Policy Documents", "CAP-POL", 2),
    ("CAP-BIL-INV", "Invoicing", "CAP-BIL", 2),
    ("CAP-BIL-COL", "Collections", "CAP-BIL", 2),
    ("CAP-CUS-MDM", "Customer Master", "CAP-CUS", 2),
    ("CAP-CUS-ENG", "Customer Engagement", "CAP-CUS", 2),
    ("CAP-CUS-DST", "Distribution & Agents", "CAP-CUS", 2),
    ("CAP-FIN-GL", "General Ledger", "CAP-FIN", 2),
    ("CAP-FIN-REP", "Regulatory Reporting", "CAP-FIN", 2),
    ("CAP-DAT-ANL", "Analytics & BI", "CAP-DAT", 2),
    ("CAP-DAT-AI", "AI & Automation", "CAP-DAT", 2),
    ("CAP-COR-HR", "People & Payroll", "CAP-COR", 2),
    ("CAP-COR-ITSM", "IT Service Management", "CAP-COR", 2),
    ("CAP-CLM-FNOL-CHN", "Claim Intake Channels", "CAP-CLM-FNOL", 3),
    ("CAP-CLM-ADJ-COV", "Coverage Verification", "CAP-CLM-ADJ", 3),
    ("CAP-CLM-ADJ-SET", "Settlement Negotiation", "CAP-CLM-ADJ", 3),
    ("CAP-CLM-PAY-DSB", "Payment Disbursement", "CAP-CLM-PAY", 3),
    ("CAP-UW-PRC-RTE", "Rate Calculation", "CAP-UW-PRC", 3),
    ("CAP-CUS-MDM-IDR", "Identity Resolution", "CAP-CUS-MDM", 3),
    ("CAP-CUS-MDM-CON", "Consent & Privacy", "CAP-CUS-MDM", 3),
]

# ---------------------------------------------------------- technologies
# name -> (category, lifecycle, vendor_support_end)
TECHNOLOGIES = {
    "Java 8": ("runtime", "extended", "2030-12"),
    "Java 11": ("runtime", "supported", "2032-01"),
    "Java 17": ("runtime", "supported", "2029-09"),
    ".NET Framework 4.8": ("runtime", "supported", "2032-01"),
    ".NET 6": ("runtime", "eol", "2024-11"),
    ".NET 8": ("runtime", "supported", "2026-11"),
    "Python 3.11": ("runtime", "supported", "2027-10"),
    "Node.js 18": ("runtime", "eol", "2025-04"),
    "Node.js 20": ("runtime", "supported", "2026-04"),
    "React 18": ("framework", "supported", "2027-12"),
    "Spring Boot 2.7": ("framework", "eol", "2023-11"),
    "Spring Boot 3": ("framework", "supported", "2027-05"),
    "Oracle 12c": ("database", "eol", "2022-07"),
    "Oracle 19c": ("database", "supported", "2027-04"),
    "SQL Server 2014": ("database", "eol", "2024-07"),
    "SQL Server 2019": ("database", "supported", "2030-01"),
    "PostgreSQL 14": ("database", "supported", "2026-11"),
    "PostgreSQL 15": ("database", "supported", "2027-11"),
    "DB2 z/OS": ("database", "extended", "2029-04"),
    "Teradata 15": ("database", "extended", "2027-06"),
    "MongoDB 4.4": ("database", "eol", "2024-02"),
    "Elasticsearch 7": ("database", "eol", "2023-08"),
    "Redis 6": ("database", "supported", "2026-12"),
    "Snowflake": ("data-platform", "supported", "n/a"),
    "Databricks": ("data-platform", "supported", "n/a"),
    "Cosmos DB": ("database", "supported", "n/a"),
    "Windows Server 2012": ("os", "eol", "2023-10"),
    "Windows Server 2019": ("os", "supported", "2029-01"),
    "RHEL 8": ("os", "supported", "2029-05"),
    "z/OS": ("os", "supported", "2030-09"),
    "COBOL": ("language", "extended", "n/a"),
    "AS/400 RPG": ("language", "extended", "2028-04"),
    "WebSphere 8.5": ("middleware", "eol", "2022-04"),
    "IBM MQ 9.1": ("middleware", "extended", "2026-09"),
    "MuleSoft Anypoint": ("middleware", "supported", "2027-06"),
    "Apache Kafka": ("middleware", "supported", "n/a"),
    "Kubernetes 1.27": ("platform", "eol", "2024-06"),
    "AKS": ("platform", "supported", "n/a"),
    "Azure OpenAI": ("ai", "supported", "n/a"),
    "SharePoint Server 2016": ("platform", "extended", "2026-07"),
    "SAP S/4HANA": ("erp", "supported", "2030-12"),
    "SAP ECC 6.0": ("erp", "extended", "2027-12"),
    "Guidewire ClaimCenter 10": ("package", "extended", "2026-12"),
    "Duck Creek Policy": ("package", "supported", "n/a"),
    "Salesforce": ("saas", "supported", "n/a"),
    "Terraform": ("iac", "supported", "n/a"),
}

# --------------------------------------------------------------- applications
# kind: package | custom | microservice | platform | legacy | saas
# Keys are referenced by the generator when wiring story data.
D_CLM, D_POL, D_UW, D_FIN, D_CUS, D_DAT, D_INT, D_COR = DOMAINS

APPS = [
    # ---------------- Claims
    dict(key="GWCC", name="Guidewire ClaimCenter", domain=D_CLM, kind="package", tech=["Guidewire ClaimCenter 10", "Java 8", "WebSphere 8.5", "Oracle 12c"], lifecycle="extended", criticality="critical", host="on-prem", caps=["CAP-CLM-ADJ", "CAP-CLM-ADJ-COV", "CAP-CLM-FNOL"], owner="Rohan Kulkarni", vendor="Guidewire", users=1800, cost=2400, db="ORA12", dr="warm", internet=False),
    dict(key="CMF", name="Claims Mainframe Core", domain=D_CLM, kind="legacy", tech=["COBOL", "z/OS", "DB2 z/OS"], lifecycle="extended", criticality="critical", host="mainframe", caps=["CAP-CLM-ADJ-SET", "CAP-CLM-PAY"], owner="Victor Alvarez", vendor="In-house", users=900, cost=3100, db="DB2", dr="warm", single=True, age=31),
    dict(key="CIP", name="Claims Intake Portal", domain=D_CLM, kind="custom", tech=["React 18", "Node.js 20", "AKS"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-CLM-FNOL-CHN", "CAP-CLM-FNOL"], owner="Ananya Rao", users=420000, cost=640, db="PG", dr="hot", internet=True),
    dict(key="FSE", name="Fraud Scoring Engine", domain=D_CLM, kind="custom", tech=["Python 3.11", "Databricks", "AKS"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-CLM-FRD"], owner="Olivia Brennan", users=120, cost=520, db="SNOW_FRD", dr="warm"),
    dict(key="CPH", name="Claims Payments Hub", domain=D_CLM, kind="custom", tech=["Java 11", "Spring Boot 2.7", "AKS"], lifecycle="supported", criticality="critical", host="azure", caps=["CAP-CLM-PAY-DSB", "CAP-CLM-PAY"], owner="Dev Patel", users=300, cost=780, db="PG", dr="hot"),
    dict(key="CDV", name="Claims Document Vault", domain=D_CLM, kind="custom", tech=[".NET Framework 4.8", "SQL Server 2014", "Windows Server 2012"], lifecycle="eol", criticality="medium", host="on-prem", caps=["CAP-CLM-ADJ"], owner="Rohan Kulkarni", users=1500, cost=310, db="MSSQL14", dr="cold", single=True, age=13, vulns=(3, 11)),
    dict(key="ADJM", name="Adjuster Mobile App", domain=D_CLM, kind="custom", tech=["React 18", "Node.js 18"], lifecycle="supported", criticality="medium", host="azure", caps=["CAP-CLM-ADJ"], owner="Ananya Rao", users=2400, cost=260, db=None, dr="warm", internet=True),
    dict(key="CAM", name="Claims Analytics Mart", domain=D_CLM, kind="custom", tech=["Snowflake"], lifecycle="supported", criticality="medium", host="saas", caps=["CAP-DAT-ANL"], owner="Kenji Tanaka", users=380, cost=410, db=None, dr="hot"),
    dict(key="SUBRO", name="Subrogation Tracker", domain=D_CLM, kind="legacy", tech=[".NET Framework 4.8", "SQL Server 2014", "Windows Server 2012"], lifecycle="eol", criticality="medium", host="on-prem", caps=["CAP-CLM-ADJ-SET"], owner="Rohan Kulkarni", users=140, cost=120, db="MSSQL14_SUB", dr="none", single=True, age=11, vulns=(2, 9)),
    dict(key="CCOP", name="Claims Copilot", domain=D_CLM, kind="custom", tech=["Azure OpenAI", "Python 3.11", "AKS"], lifecycle="supported", criticality="medium", host="azure", caps=["CAP-CLM-ADJ-COV", "CAP-DAT-AI"], owner="Olivia Brennan", users=650, cost=380, db="COSMOS_CCOP", dr="warm", age=1),
    dict(key="SALV", name="Salvage & Recovery Service", domain=D_CLM, kind="microservice", tech=["Java 17", "Spring Boot 3", "AKS"], lifecycle="supported", criticality="low", host="azure", caps=["CAP-CLM-ADJ-SET"], owner="Dev Patel", users=60, cost=90, db="PG", dr="warm"),
    dict(key="CNS", name="Claims Notification Service", domain=D_CLM, kind="microservice", tech=["Java 17", "Apache Kafka", "AKS"], lifecycle="supported", criticality="medium", host="azure", caps=["CAP-CLM-FNOL"], owner="Dev Patel", users=0, cost=110, db=None, dr="warm", role="notification"),
    # ---------------- Policy Admin
    dict(key="PAC", name="Policy Admin Core", domain=D_POL, kind="package", tech=["Duck Creek Policy", ".NET Framework 4.8", "Windows Server 2019", "Oracle 12c"], lifecycle="extended", criticality="critical", host="on-prem", caps=["CAP-POL-ISS", "CAP-POL-END"], owner="Sarah Whitfield", vendor="Duck Creek", users=2200, cost=3600, db="ORA12", dr="warm", single=True),
    dict(key="PDG", name="Policy Document Generator", domain=D_POL, kind="custom", tech=["Java 8", "Oracle 12c", "RHEL 8"], lifecycle="extended", criticality="high", host="on-prem", caps=["CAP-POL-DOC"], owner="Marcus Chen", users=300, cost=280, db="ORA12", dr="cold", age=9),
    dict(key="END", name="Endorsement Engine", domain=D_POL, kind="microservice", tech=["Java 17", "Spring Boot 3", "PostgreSQL 15", "AKS"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-POL-END"], owner="Marcus Chen", users=0, cost=190, db="PG", dr="hot"),
    dict(key="REN", name="Renewal Orchestrator", domain=D_POL, kind="microservice", tech=["Java 17", "Apache Kafka", "AKS"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-POL-END"], owner="Marcus Chen", users=0, cost=170, db="PG", dr="hot"),
    dict(key="PSS", name="Policy Search Service", domain=D_POL, kind="microservice", tech=["Elasticsearch 7", "Java 17", "AKS"], lifecycle="supported", criticality="medium", host="azure", caps=["CAP-POL-ISS"], owner="Marcus Chen", users=0, cost=95, db="ES", dr="warm"),
    dict(key="PQP", name="Policy Quote Portal", domain=D_POL, kind="custom", tech=["React 18", "Node.js 20", "AKS"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-POL-ISS", "CAP-UW-PRC"], owner="Aisha Khan", users=310000, cost=450, db=None, dr="hot", internet=True),
    dict(key="PCS", name="Product Catalog Service", domain=D_POL, kind="microservice", tech=["Python 3.11", "PostgreSQL 15", "AKS"], lifecycle="supported", criticality="medium", host="azure", caps=["CAP-POL-ISS"], owner="Sarah Whitfield", users=0, cost=70, db="PG", dr="warm"),
    dict(key="LLP", name="Legacy Life Policy System", domain=D_POL, kind="legacy", tech=["AS/400 RPG"], lifecycle="eol", criticality="medium", host="on-prem", caps=["CAP-POL-ISS"], owner="Victor Alvarez", users=210, cost=1250, db="AS400", dr="none", single=True, age=29),
    # ---------------- Underwriting
    dict(key="UWB", name="Underwriting Workbench", domain=D_UW, kind="custom", tech=["Java 8", "Oracle 12c", "WebSphere 8.5"], lifecycle="extended", criticality="high", host="on-prem", caps=["CAP-UW-RSK"], owner="Lucia Fernandez", users=640, cost=930, db="ORA12", dr="warm", age=12),
    dict(key="RSS", name="Risk Scoring Service", domain=D_UW, kind="microservice", tech=["Python 3.11", "AKS", "PostgreSQL 15"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-UW-RSK"], owner="Lucia Fernandez", users=0, cost=180, db="PG", dr="hot"),
    dict(key="RTE", name="Rating Engine", domain=D_UW, kind="custom", tech=["Java 11", "Oracle 19c", "RHEL 8"], lifecycle="supported", criticality="critical", host="on-prem", caps=["CAP-UW-PRC-RTE", "CAP-UW-PRC"], owner="James O'Connor", users=0, cost=1100, db="ORA19", dr="hot", peak=(900, 1000)),
    dict(key="TPD", name="Third-Party Data Gateway", domain=D_UW, kind="microservice", tech=["Java 17", "AKS"], lifecycle="supported", criticality="medium", host="azure", caps=["CAP-UW-RSK"], owner="Lucia Fernandez", users=0, cost=120, db=None, dr="warm"),
    dict(key="REIP", name="Reinsurance Platform", domain=D_UW, kind="package", tech=["SQL Server 2019", "Windows Server 2019"], lifecycle="supported", criticality="medium", host="on-prem", caps=["CAP-UW-REI"], owner="Lucia Fernandez", vendor="Munich Re Tech", users=45, cost=680, db="MSSQL19", dr="warm"),
    dict(key="CATM", name="Catastrophe Modelling Suite", domain=D_UW, kind="package", tech=["Windows Server 2012", "SQL Server 2019"], lifecycle="eol", criticality="medium", host="on-prem", caps=["CAP-UW-RSK"], owner="Lucia Fernandez", vendor="Moody's RMS", users=25, cost=540, db="MSSQL19", dr="none", single=True, vulns=(1, 6)),
    # ---------------- Billing & Finance
    dict(key="SAP", name="SAP S/4HANA Finance", domain=D_FIN, kind="package", tech=["SAP S/4HANA", "RHEL 8"], lifecycle="supported", criticality="critical", host="on-prem", caps=["CAP-FIN-GL", "CAP-FIN-REP"], owner="Priya Venkataraman", vendor="SAP", users=1200, cost=4200, db="HANA", dr="hot"),
    dict(key="ECC", name="SAP ECC", domain=D_FIN, kind="package", tech=["SAP ECC 6.0", "Oracle 19c"], lifecycle="extended", criticality="high", host="on-prem", caps=["CAP-FIN-GL"], owner="Priya Venkataraman", vendor="SAP", users=380, cost=1900, db="ORA19_ECC", dr="warm", age=14),
    dict(key="DCB", name="Duck Creek Billing", domain=D_FIN, kind="package", tech=["Duck Creek Policy", "SQL Server 2019", "Windows Server 2019"], lifecycle="supported", criticality="high", host="on-prem", caps=["CAP-BIL-INV"], owner="Thomas Becker", vendor="Duck Creek", users=420, cost=1400, db="MSSQL19_DCB", dr="warm"),
    dict(key="COLM", name="Collections Manager", domain=D_FIN, kind="custom", tech=["Java 8", "Oracle 12c", "RHEL 8"], lifecycle="extended", criticality="medium", host="on-prem", caps=["CAP-BIL-COL"], owner="Thomas Becker", users=150, cost=260, db="ORA12", dr="cold", age=10),
    dict(key="PGS", name="Payment Gateway Service", domain=D_FIN, kind="microservice", tech=["Java 17", "Spring Boot 3", "AKS"], lifecycle="supported", criticality="critical", host="azure", caps=["CAP-BIL-INV"], owner="Hannah Müller", users=0, cost=340, db="PG", dr="hot", internet=True, peak=(700, 1200)),
    dict(key="GLR", name="General Ledger Reconciler", domain=D_FIN, kind="custom", tech=[".NET 6", "SQL Server 2019"], lifecycle="supported", criticality="medium", host="azure", caps=["CAP-FIN-GL"], owner="Priya Venkataraman", users=40, cost=85, db="MSSQL19_GLR", dr="warm"),
    dict(key="RRH", name="Regulatory Reporting Hub", domain=D_FIN, kind="custom", tech=["Python 3.11", "Snowflake"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-FIN-REP"], owner="Priya Venkataraman", users=55, cost=240, db=None, dr="warm"),
    dict(key="TAX", name="Tax Engine", domain=D_FIN, kind="saas", tech=["Salesforce"], lifecycle="supported", criticality="low", host="saas", caps=["CAP-FIN-GL"], owner="Priya Venkataraman", vendor="Vertex", users=30, cost=210, db=None, dr="hot"),
    dict(key="TRW", name="Treasury Workstation", domain=D_FIN, kind="package", tech=["SQL Server 2014", "Windows Server 2019"], lifecycle="extended", criticality="medium", host="on-prem", caps=["CAP-FIN-GL"], owner="Hannah Müller", vendor="Kyriba", users=35, cost=390, db="MSSQL14_TRW", dr="warm"),
    dict(key="CSS", name="Commission Statement Service", domain=D_FIN, kind="custom", tech=["Java 11", "Oracle 19c"], lifecycle="supported", criticality="low", host="on-prem", caps=["CAP-CUS-DST"], owner="Daniel Okafor", users=2600, cost=130, db="ORA19_CSS", dr="warm"),
    # ---------------- Customer & Distribution
    dict(key="SFC", name="Salesforce CRM", domain=D_CUS, kind="saas", tech=["Salesforce"], lifecycle="supported", criticality="high", host="saas", caps=["CAP-CUS-ENG", "CAP-CUS-MDM"], owner="Aisha Khan", vendor="Salesforce", users=3800, cost=2900, db=None, dr="hot", role="customer_master", internet=True),
    dict(key="CIS", name="Northwind Customer Hub", domain=D_CUS, kind="legacy", tech=["Java 8", "SQL Server 2014", "Windows Server 2012"], lifecycle="eol", criticality="high", host="on-prem", caps=["CAP-CUS-MDM"], owner="Elena Petrova", users=1100, cost=860, db="MSSQL14_CIS", dr="cold", role="customer_master", single=True, age=15, vulns=(4, 14)),
    dict(key="MDM", name="Customer Master (MDM)", domain=D_CUS, kind="package", tech=["Java 11", "PostgreSQL 14"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-CUS-MDM", "CAP-CUS-MDM-IDR"], owner="Elena Petrova", vendor="Informatica", users=200, cost=1300, db="PG", dr="warm", role="customer_master"),
    dict(key="ACE", name="Agent Commission Engine", domain=D_CUS, kind="custom", tech=["Java 8", "Oracle 12c", "RHEL 8"], lifecycle="extended", criticality="medium", host="on-prem", caps=["CAP-CUS-DST"], owner="Daniel Okafor", users=2600, cost=300, db="ORA12", dr="cold", age=11),
    dict(key="AGP", name="Agent Portal", domain=D_CUS, kind="custom", tech=["React 18", "Node.js 20", "AKS"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-CUS-DST"], owner="Daniel Okafor", users=8200, cost=380, db="PG", dr="hot", internet=True),
    dict(key="CSP", name="Customer Self-Service Portal", domain=D_CUS, kind="custom", tech=["React 18", "Node.js 20", "AKS"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-CUS-ENG"], owner="Aisha Khan", users=640000, cost=720, db="PG", dr="hot", internet=True),
    dict(key="CNH", name="Customer Notification Hub", domain=D_CUS, kind="microservice", tech=["Java 17", "Apache Kafka", "Cosmos DB", "AKS"], lifecycle="supported", criticality="medium", host="azure", caps=["CAP-CUS-ENG"], owner="Aisha Khan", users=0, cost=140, db="COSMOS_CNH", dr="warm", role="notification"),
    dict(key="CPM", name="Consent & Preference Manager", domain=D_CUS, kind="microservice", tech=["Java 17", "Spring Boot 3", "PostgreSQL 15", "AKS"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-CUS-MDM-CON"], owner="Elena Petrova", users=0, cost=100, db="PG", dr="hot"),
    dict(key="BRG", name="Broker Gateway", domain=D_CUS, kind="custom", tech=[".NET 8", "AKS"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-CUS-DST"], owner="Daniel Okafor", users=4100, cost=260, db="PG", dr="warm", internet=True),
    dict(key="MKT", name="Marketing Automation", domain=D_CUS, kind="saas", tech=["Salesforce"], lifecycle="supported", criticality="low", host="saas", caps=["CAP-CUS-ENG"], owner="Aisha Khan", vendor="Adobe", users=90, cost=330, db=None, dr="hot"),
    # ---------------- Data & Analytics
    dict(key="SNOW", name="Snowflake Data Cloud", domain=D_DAT, kind="platform", tech=["Snowflake"], lifecycle="supported", criticality="critical", host="saas", caps=["CAP-DAT-ANL"], owner="Kenji Tanaka", vendor="Snowflake", users=1900, cost=3300, db=None, dr="hot"),
    dict(key="DBX", name="Databricks Lakehouse", domain=D_DAT, kind="platform", tech=["Databricks", "Python 3.11"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-DAT-ANL", "CAP-DAT-AI"], owner="Kenji Tanaka", vendor="Databricks", users=320, cost=1800, db="ADLS", dr="warm"),
    dict(key="EDW", name="Enterprise Data Warehouse", domain=D_DAT, kind="legacy", tech=["Teradata 15"], lifecycle="extended", criticality="high", host="on-prem", caps=["CAP-DAT-ANL"], owner="Kenji Tanaka", vendor="Teradata", users=750, cost=2700, db="TERA", dr="warm", single=True, age=12),
    dict(key="PBI", name="Power BI Service", domain=D_DAT, kind="saas", tech=["Snowflake"], lifecycle="supported", criticality="medium", host="saas", caps=["CAP-DAT-ANL"], owner="Kenji Tanaka", vendor="Microsoft", users=4100, cost=310, db=None, dr="hot"),
    dict(key="COL", name="Data Catalog", domain=D_DAT, kind="saas", tech=["Salesforce"], lifecycle="supported", criticality="low", host="saas", caps=["CAP-DAT-ANL"], owner="Fatima Hassan", vendor="Collibra", users=210, cost=190, db=None, dr="warm"),
    dict(key="C360", name="Customer 360 Service", domain=D_DAT, kind="microservice", tech=["Java 17", "Apache Kafka", "Snowflake", "AKS"], lifecycle="supported", criticality="high", host="azure", caps=["CAP-CUS-MDM", "CAP-DAT-ANL"], owner="Elena Petrova", users=0, cost=260, db=None, dr="warm"),
    dict(key="AOAI", name="Azure OpenAI Platform", domain=D_DAT, kind="platform", tech=["Azure OpenAI"], lifecycle="supported", criticality="medium", host="azure", caps=["CAP-DAT-AI"], owner="Olivia Brennan", vendor="Microsoft", users=40, cost=520, db=None, dr="warm", age=1),
    dict(key="AIGW", name="AI Gateway", domain=D_DAT, kind="microservice", tech=["Python 3.11", "AKS"], lifecycle="supported", criticality="medium", host="azure", caps=["CAP-DAT-AI"], owner="Olivia Brennan", users=0, cost=90, db=None, dr="warm", age=1),
    dict(key="FST", name="Feature Store", domain=D_DAT, kind="custom", tech=["Databricks", "Redis 6"], lifecycle="supported", criticality="low", host="azure", caps=["CAP-DAT-AI"], owner="Olivia Brennan", users=0, cost=130, db="REDIS", dr="none"),
    # ---------------- Integration & Platform
    dict(key="MULE", name="MuleSoft Anypoint", domain=D_INT, kind="platform", tech=["MuleSoft Anypoint", "AKS"], lifecycle="supported", criticality="critical", host="azure", caps=["CAP-COR-ITSM"], owner="Rahul Mehta", vendor="Salesforce", users=0, cost=2100, db=None, dr="warm", single=False),
    dict(key="KAFKA", name="Kafka Event Platform", domain=D_INT, kind="platform", tech=["Apache Kafka", "AKS"], lifecycle="supported", criticality="critical", host="azure", caps=["CAP-COR-ITSM"], owner="Rahul Mehta", vendor="Confluent", users=0, cost=980, db=None, dr="hot"),
    dict(key="APIM", name="Azure API Management", domain=D_INT, kind="platform", tech=["AKS"], lifecycle="supported", criticality="critical", host="azure", caps=["CAP-COR-ITSM"], owner="Rahul Mehta", vendor="Microsoft", users=0, cost=420, db=None, dr="hot"),
    dict(key="SNOWITSM", name="ServiceNow", domain=D_INT, kind="saas", tech=["Salesforce"], lifecycle="supported", criticality="high", host="saas", caps=["CAP-COR-ITSM"], owner="Chloe Dubois", vendor="ServiceNow", users=6200, cost=1200, db=None, dr="hot"),
    dict(key="IDP", name="Identity Platform", domain=D_INT, kind="saas", tech=["Salesforce"], lifecycle="supported", criticality="critical", host="saas", caps=["CAP-COR-ITSM"], owner="Noah Williams", vendor="Microsoft Entra", users=9000, cost=640, db=None, dr="hot"),
    dict(key="IIB", name="Legacy Integration Bus", domain=D_INT, kind="legacy", tech=["IBM MQ 9.1", "WebSphere 8.5", "Java 8"], lifecycle="extended", criticality="high", host="on-prem", caps=["CAP-COR-ITSM"], owner="Rahul Mehta", vendor="IBM", users=0, cost=1500, db=None, dr="warm", single=True, age=14),
    dict(key="MFT", name="File Transfer Gateway", domain=D_INT, kind="package", tech=["Windows Server 2012", "SQL Server 2014"], lifecycle="eol", criticality="high", host="on-prem", caps=["CAP-COR-ITSM"], owner="Rahul Mehta", vendor="Axway", users=0, cost=290, db="MSSQL14_MFT", dr="none", single=True, age=11, vulns=(2, 7)),
    dict(key="OBS", name="Observability Stack", domain=D_INT, kind="saas", tech=["Salesforce"], lifecycle="supported", criticality="medium", host="saas", caps=["CAP-COR-ITSM"], owner="Chloe Dubois", vendor="Datadog", users=800, cost=620, db=None, dr="warm"),
    dict(key="SKM", name="Secrets & Key Management", domain=D_INT, kind="platform", tech=["AKS"], lifecycle="supported", criticality="critical", host="azure", caps=["CAP-COR-ITSM"], owner="Noah Williams", vendor="Microsoft", users=0, cost=60, db=None, dr="hot"),
    # ---------------- Corporate Services
    dict(key="WDAY", name="Workday HCM", domain=D_COR, kind="saas", tech=["Salesforce"], lifecycle="supported", criticality="high", host="saas", caps=["CAP-COR-HR"], owner="Grace Liu", vendor="Workday", users=11000, cost=2100, db=None, dr="hot"),
    dict(key="PAYI", name="Payroll Integration Service", domain=D_COR, kind="custom", tech=["Java 11", "SQL Server 2019"], lifecycle="supported", criticality="medium", host="on-prem", caps=["CAP-COR-HR"], owner="Grace Liu", users=20, cost=95, db="MSSQL19_PAY", dr="warm"),
    dict(key="INTRA", name="Corporate Intranet", domain=D_COR, kind="package", tech=["SharePoint Server 2016", "SQL Server 2014", "Windows Server 2012"], lifecycle="eol", criticality="low", host="on-prem", caps=["CAP-COR-ITSM"], owner="Arjun Nambiar", vendor="Microsoft", users=11000, cost=230, db="MSSQL14_INTRA", dr="none", age=10, vulns=(1, 8)),
    dict(key="LMM", name="Legal Matter Management", domain=D_COR, kind="saas", tech=["Salesforce"], lifecycle="supported", criticality="low", host="saas", caps=["CAP-COR-ITSM"], owner="Liam Gallagher", vendor="Onit", users=120, cost=160, db=None, dr="warm"),
    dict(key="FAC", name="Facilities & Travel", domain=D_COR, kind="saas", tech=["Salesforce"], lifecycle="supported", criticality="low", host="saas", caps=["CAP-COR-ITSM"], owner="Arjun Nambiar", vendor="SAP Concur", users=9000, cost=250, db=None, dr="warm"),
]

# ---------------------------------------------------------------- workflows
# Steps reference app keys; `api_cust2` marks the workflows that call Customer API v2.
WORKFLOWS = [
    ("First Notice of Loss to Claim Setup", D_CLM, ["CIP", "CNS", "GWCC", "FSE", "CMF"], True),
    ("Policy Quote to Bind", D_POL, ["PQP", "RTE", "RSS", "PAC", "DCB"], True),
    ("Customer Onboarding", D_CUS, ["CSP", "MDM", "CPM", "SFC", "CNH"], True),
    ("Policy Renewal", D_POL, ["REN", "RTE", "END", "PAC", "CNH"], True),
    ("Customer Address Change", D_CUS, ["CSP", "MDM", "PAC", "SFC", "END"], True),
    ("Consent Management Update", D_CUS, ["CSP", "CPM", "MDM", "MKT", "CNH"], True),
    ("Claim Payment Disbursement", D_CLM, ["CMF", "CPH", "PGS", "SAP"], False),
    ("Premium Billing & Collections", D_FIN, ["PAC", "DCB", "COLM", "PGS", "SAP"], False),
    ("Fraud Investigation", D_CLM, ["GWCC", "FSE", "DBX", "SNOWITSM"], False),
    ("Agent Commission Settlement", D_CUS, ["PAC", "ACE", "CSS", "SAP"], False),
    ("Regulatory Reporting Close", D_FIN, ["SAP", "SNOW", "RRH", "GLR"], False),
    ("Claims Settlement Approval", D_CLM, ["GWCC", "CMF", "CPH", "SAP"], False),
    ("Month-end Financial Close", D_FIN, ["ECC", "SAP", "GLR", "TRW"], False),
    ("Underwriting Referral", D_UW, ["UWB", "RSS", "TPD", "REIP"], False),
]

# Applications that consume Customer API v2 (exactly 14).
CUSTOMER_API_V2_CONSUMERS = [
    "CIP", "GWCC", "PAC", "PQP", "REN", "END", "SFC", "CSP", "AGP", "CNH", "CPM", "BRG", "C360", "FSE",
]
CUSTOMER_API_V1_CONSUMERS = ["CIS", "COLM", "ACE", "CSS", "MKT", "UWB"]

# Apps that reach into the shared Oracle 12c instance directly from another domain.
# Together with GWCC, PAC, PDG, UWB, COLM, ACE (which use it as their datastore) that makes 9
# dependents, 4 of which support Claims: GWCC, CIP, FSE, CPH.
ORACLE12_DIRECT = ["CIP", "FSE", "CPH"]  # cross-domain direct DB access (3)
