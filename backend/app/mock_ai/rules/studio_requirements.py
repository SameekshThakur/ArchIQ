"""Blueprint Intelligence Studio, steps 1 and 2: read the requirements and rank the existing blueprints.

Everything here is deterministic. The text is searched with fixed patterns, every finding keeps the sentence it came from as evidence, and the ranking is
a weighted count of matched signals. A language model only writes the prose around these facts (see `services/studio.py`); it never sets a number.
"""

from __future__ import annotations

import re

from app.mock_ai.generators import blueprints as bp_gen
from app.mock_ai.generators import documents as docs
from app.mock_ai.generators import studio_catalog as cat
from app.repositories.store import get_store

# ------------------------------------------------------------------ helpers
_SENT = re.compile(r".+?(?:[.!?](?=\s|$)|\n|$)", re.S)
STOP = set("""about above after again against being below between could doing during each from further have having here into itself more most other over same should since some such than that their them then there these they this those through under until very were what when where which while will with within would your""".split())


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9+#.-]{2,}", text.lower())


def _snippet(text: str, pos: int) -> str:
    """The sentence that contains `pos`, cut to a readable length."""
    for m in _SENT.finditer(text):
        if m.start() <= pos < m.end() + 1:
            s = " ".join(m.group().split())
            return s if len(s) <= 180 else s[:177].rstrip() + "..."
    return " ".join(text[max(0, pos - 60): pos + 100].split())


def _find(rx: str, text: str, flags: int = re.I):
    m = re.search(rx, text, flags)
    return (m, _snippet(text, m.start())) if m else (None, "")


def _num(v: float) -> float | int:
    return int(v) if float(v).is_integer() else round(v, 2)


# ------------------------------------------------------------------ extraction
COMPLIANCE = [(r"\bgdpr\b", "GDPR"), (r"\bsoc ?2\b", "SOC2"), (r"\biso ?27001\b", "ISO27001"), (r"\bpci[- ]?dss\b|\bpci\b", "PCI-DSS"), (r"\bhipaa\b", "HIPAA"), (r"\bdora\b", "DORA"),
              (r"\bsolvency ?(?:ii|2)\b", "Solvency II"), (r"\bnis ?2\b", "NIS2"), (r"\bccpa\b", "CCPA"), (r"\bsox\b|sarbanes", "SOX")]
DOMAIN_WORDS = {
    "Claims": r"claims?|adjust\w+|fnol|loss|subrogation|settlement",
    "Policy Admin": r"polic(?:y|ies)|endorsement|renewal|quote|rating",
    "Underwriting": r"underwrit\w+|risk selection|referral",
    "Billing & Finance": r"billing|invoice|payment|premium collection|ledger|finance",
    "Customer & Distribution": r"customer|broker|agent|distribution|portal|onboarding",
    "Data & Analytics": r"analytics|reporting|data (?:lake|platform|warehouse)|lakehouse|bi\b",
    "Integration & Platform": r"integration|platform|gateway|middleware",
    "Corporate Services": r"\bhr\b|employee|procurement|facilities|legal",
}
REGION_WORDS = [("westeurope", r"west europe|netherlands"), ("northeurope", r"north europe|ireland"), ("uksouth", r"uk south|united kingdom|\buk\b"), ("eastus2", r"east us ?2?"),
                ("centralindia", r"central india|\bindia\b"), ("southeastasia", r"southeast asia|singapore"), ("brazilsouth", r"brazil")]
EU_REGIONS = {"westeurope", "northeurope", "uksouth"}


def extract(text: str, domain: str | None = None) -> dict:
    t = " ".join(text.split())
    low = t.lower()
    ev: list[dict] = []  # every fact found, with the sentence it came from

    def fact(key: str, label: str, value, snippet: str) -> None:
        ev.append(dict(key=key, label=label, value=value, evidence=snippet))

    # --- non-functional requirements
    nfr: dict = {}
    m, sn = _find(r"(\d{2}(?:\.\d{1,3})?)\s*%\s*(?:availability|uptime|available)|(?:availability|uptime)[^.\d%]{0,40}(\d{2}(?:\.\d{1,3})?)\s*%", t)
    if m:
        v = float(m.group(1) or m.group(2))
        if 90 <= v < 100:
            nfr["availability"] = f"{v:g}"
            fact("availability", "Availability", f"{v:g}%", sn)
    m, sn = _find(r"\brto\b[^.\d]{0,25}(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?|h)\b|(?:recover|restor\w+)[^.]{0,30}within\s+(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?)", t)
    if m:
        v, unit = (float(m.group(1)), m.group(2)) if m.group(1) else (float(m.group(3)), m.group(4))
        nfr["rto_hours"] = _num(round(v / 60 if unit.lower().startswith("m") else v, 3))
        fact("rto_hours", "Recovery time (RTO)", f"{nfr['rto_hours']} hours", sn)
    m, sn = _find(r"\brpo\b[^.\d]{0,25}(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b|(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?)\s+of\s+data\s+loss", t)
    if m:
        v, unit = (float(m.group(1)), m.group(2)) if m.group(1) else (float(m.group(3)), m.group(4))
        ul = unit.lower()
        mins = v / 60 if ul.startswith("s") else v * 60 if ul.startswith("h") else v
        nfr["rpo_minutes"] = _num(round(mins, 2))
        fact("rpo_minutes", "Data loss tolerance (RPO)", f"{nfr['rpo_minutes']} minutes", sn)
    m, sn = _find(r"(?:latency|response time|p9[059]|first token|respon\w+)[^.\d]{0,45}?(\d+(?:\.\d+)?)\s*(ms|milliseconds?|seconds?|secs?)\b", t)
    if m:
        v = float(m.group(1))
        nfr["latency_ms"] = _num(round(v * 1000 if m.group(2).lower().startswith("sec") else v))
        fact("latency_ms", "Latency", f"{nfr['latency_ms']} ms", sn)
    m, sn = _find(r"(\d[\d,]*)\s*(?:tps\b|transactions?\s*(?:per|/)\s*sec\w*|requests?\s*(?:per|/)\s*sec\w*|rps\b|req/s)|(\d[\d,]*)\s*(?:requests?|transactions?)\s*(?:per|/)\s*min\w*", t)
    if m:
        if m.group(1):
            nfr["throughput_tps"] = int(m.group(1).replace(",", ""))
        else:
            nfr["throughput_tps"] = max(1, round(int(m.group(2).replace(",", "")) / 60))
        fact("throughput_tps", "Throughput", f"{nfr['throughput_tps']} per second", sn)
    comp = []
    for rx, name in COMPLIANCE:
        m, sn = _find(rx, t)
        if m:
            comp.append(name)
            fact("compliance", "Regulation or standard", name, sn)
    if comp:
        nfr["compliance"] = comp

    # --- criticality tier
    tier, tier_basis = None, None
    m, sn = _find(r"\btier[- ]?1\b|mission[- ]critical|business[- ]critical|\bcritical (?:system|service|workload|application)", t)
    if m:
        tier, tier_basis = "tier1", sn
    else:
        m, sn = _find(r"\btier[- ]?3\b|best[- ]effort|non[- ]critical|low criticality", t)
        if m:
            tier, tier_basis = "tier3", sn
        else:
            m, sn = _find(r"\btier[- ]?2\b|business[- ]important|important (?:system|service|workload)", t)
            if m:
                tier, tier_basis = "tier2", sn
    if not tier and nfr.get("availability"):
        a = float(nfr["availability"])
        tier = "tier1" if a >= 99.95 else "tier2" if a >= 99.9 else "tier3"
        tier_basis = f"Derived from the stated availability target of {nfr['availability']}%: the Studio's tier minimums are 99.95% (tier 1), 99.9% (tier 2) and 99.5% (tier 3)."
    if tier:
        fact("tier", "Criticality tier", tier, tier_basis or "")

    # --- exposure
    exposure, exposure_basis = None, ""
    mi, si = _find(r"customer[- ]facing|internet|public[- ]facing|\bportal\b|mobile app|\bbrokers?\b|\bpartners?\b|\bb2c\b|self[- ]service|external users|policyholders?", t)
    mn, sn = _find(r"internal (?:users|staff|only|use)|employees|adjusters|underwriters|case handlers|back[- ]office|intranet", t)
    if mi:
        exposure, exposure_basis = "internet", si
    elif mn:
        exposure, exposure_basis = "internal", sn
    if exposure:
        fact("exposure", "Who uses it", "Internet-facing" if exposure == "internet" else "Internal users only", exposure_basis)

    # --- data sensitivity
    classification, class_basis = None, ""
    m, sn = _find(r"\bhealth\b|medical|special[- ]category|payment card|card data|bank account|\bssn\b|national id|\brestricted\b|sensitive (?:personal )?data", t)
    if m:
        classification, class_basis = "restricted", sn
    else:
        m, sn = _find(r"\bpii\b|personal data|personally identifiable|customer data|policyholder data|claimant|claim files?|\bgdpr\b", t)
        if m:
            classification, class_basis = "confidential", sn
    if classification:
        fact("classification", "Data classification", classification, class_basis)
    personal = bool(re.search(r"\bpii\b|personal data|personally identifiable|customer data|policyholder|claimant|\bgdpr\b|health|medical", low))

    # --- residency
    residency = None
    m, sn = _find(r"(?:eu|european|uk)\s+(?:data\s+)?residency|(?:data|workloads?)\s+(?:must|should)\s+(?:stay|remain|reside)\s+in\s+(?:the\s+)?(?:eu|europe|uk)|data sovereignty|keep (?:the )?data in (?:the )?(?:eu|europe)", t)
    if m:
        residency = dict(scope="europe", evidence=sn)
        fact("residency", "Data residency", "Europe", sn)

    # --- domain
    chosen = domain or None
    scores = {d: len(re.findall(rx, low)) for d, rx in DOMAIN_WORDS.items()}
    guess = max(scores, key=lambda k: scores[k]) if any(scores.values()) else None
    domain_out = dict(value=chosen or guess, basis="chosen" if chosen else "inferred" if guess else "unknown")
    if guess and not chosen:
        fact("domain", "Business domain", guess, f"Most frequent domain vocabulary ({scores[guess]} matching words).")

    # --- what the person already chose or named
    hints: dict[str, dict] = {}

    def hint(key: str, value, snippet: str, assumed: bool = False) -> None:
        hints[key] = dict(value=value, evidence=snippet, assumed=assumed)

    clouds = {c: bool(re.search(rx, low)) for c, rx in (("azure", r"\bazure\b"), ("aws", r"\baws\b|amazon web services"), ("gcp", r"\bgcp\b|google cloud"), ("hybrid", r"on[- ]prem\w*|hybrid cloud|\bhybrid\b"))}
    named = [c for c, v in clouds.items() if v]
    if len(named) == 1:
        m, sn = _find({"azure": r"\bazure\b", "aws": r"\baws\b|amazon web services", "gcp": r"\bgcp\b|google cloud", "hybrid": r"on[- ]prem\w*|hybrid"}[named[0]], t)
        hint("cloud", named[0], sn)
    elif len(named) > 1:
        hints["_cloud_conflict"] = dict(value=named, evidence="More than one cloud is named, so none was pre-selected.", assumed=False)
    for val, rx in (("azure_openai", r"azure openai|\baoai\b"), ("bedrock", r"bedrock"), ("vertex", r"vertex ai"), ("public_api", r"openai\.com|chatgpt|public llm|anthropic api|openai api|external llm"),
                    ("self_hosted", r"self[- ]hosted (?:llm|model)|llama|mistral|open[- ]source (?:llm|model)")):
        m, sn = _find(rx, t)
        if m:
            hint("llm", val, sn)
            break
    dbs = []
    for val, rx in (("postgres", r"postgres(?:ql)?"), ("cosmos_db", r"cosmos"), ("sql_server_2019", r"sql server"), ("oracle_19c", r"oracle 19"), ("oracle_12c", r"oracle 12"), ("data_lake", r"data ?lake|\badls\b|lakehouse"), ("redis", r"\bredis\b")):
        m, sn = _find(rx, t)
        if m:
            dbs.append(val)
            hints.setdefault("databases", dict(value=[], evidence=sn, assumed=False))
    if dbs:
        hints["databases"]["value"] = dbs
    for val, rx, assumed in (("python", r"\bpython\b|fastapi", False), ("java17", r"java 17|spring boot 3", False), ("java8", r"java 8\b", False), ("java17", r"\bjava\b|spring boot", True), ("dotnet8", r"\.net 8|dotnet 8", False),
                             ("dotnet8", r"\.net\b|c#|dotnet", True), ("node18", r"node(?:\.js)? ?18", False), ("node20", r"node(?:\.js)?\b", True)):
        m, sn = _find(rx, t)
        if m:
            hint("backend", val, sn, assumed)
            break
    for val, rx in (("aks", r"\baks\b|kubernetes"), ("app_service", r"app service"), ("functions", r"azure functions?|serverless|function app")):
        m, sn = _find(rx, t)
        if m:
            hint("deployment", val, sn)
            break
    for val, rx in (("kafka", r"kafka"), ("eventhubs", r"event hubs?")):
        m, sn = _find(rx, t)
        if m:
            hint("messaging", val, sn)
            break
    for val, rx in (("terraform", r"terraform"), ("bicep", r"bicep")):
        m, sn = _find(rx, t)
        if m:
            hint("iac", val, sn)
            break
    for val, rx in REGION_WORDS:
        m, sn = _find(rx, t)
        if m:
            hint("region", val, sn)
            break
    if exposure:
        hint("exposure", exposure, exposure_basis)
    if classification:
        hint("classification", classification, class_basis)
    if tier:
        hint("tier", tier, tier_basis or "")

    # --- estate systems named in the text
    ents = docs.extract_entities(t)
    s = get_store()
    apps = {a["id"]: a for a in s.apps}
    dbs_by_id = {d["id"]: d for d in s.dbs}
    mentioned_apps: dict[str, dict] = {}
    for e in ents:
        if e["kind"] == "application" and e["id"] in apps:
            a = apps[e["id"]]
            mentioned_apps.setdefault(a["id"], dict(id=a["id"], name=a["name"], kind="application", lifecycle=a["lifecycle"], criticality=a["criticality"], domain=a["domain"], via=a["name"]))
        elif e["kind"] == "database" and e["id"] in dbs_by_id:
            d = dbs_by_id[e["id"]]
            owner = apps.get(d["owner_app"])
            if owner:
                mentioned_apps.setdefault(owner["id"], dict(id=owner["id"], name=owner["name"], kind="application", lifecycle=owner["lifecycle"], criticality=owner["criticality"], domain=owner["domain"], via=d["name"]))
    techs = [e["text"] for e in ents if e["kind"] == "technology"]
    systems = [dict(m, evidence=_snippet(t, low.find(m["via"].lower()) if m["via"].lower() in low else 0)) for m in mentioned_apps.values()]

    words = len(_words(t))
    return dict(text=t, words=words, nfr=nfr, tier=tier, exposure=exposure, classification=classification, personal_data=personal, residency=residency, domain=domain_out,
                hints=hints, systems=systems, technologies=techs, facts=ev, nfr_present=sorted(nfr), nfr_missing=[k for k in ("availability", "rto_hours", "rpo_minutes", "latency_ms", "throughput_tps", "compliance") if k not in nfr])


# ------------------------------------------------------------------ recommendation
# (pattern, weight, label, regex). The weights say how specific a phrase is: 5 names the pattern, 3 is a strong cue, 2 and 1 are supporting cues.
SIGNALS: dict[str, list[tuple[int, str, str]]] = {
    "PAT-001": [(5, "API-led or MuleSoft named", r"api[- ]led|mulesoft|anypoint"), (3, "Systems of record behind APIs", r"system[s]? of record|decouple|point[- ]to[- ]point|direct (?:db|database)|integration layer"),
                (2, "APIs for several consumers", r"\bapis?\b|rest(?:ful)?\b|openapi"), (2, "Several channels or consumers", r"multiple channels|several channels|\bchannels\b|consumers|\bpartners?\b|\bbrokers?\b"),
                (2, "Gateway controls", r"gateway|api management|apim|throttl\w+|rate limit")],
    "PAT-002": [(5, "Event-driven named", r"event[- ]driven|publish[/ ]subscribe|pub/sub"), (3, "Kafka or event streaming", r"kafka|event hubs?|event stream\w*|streaming"), (3, "Real-time propagation", r"real[- ]time|near real[- ]time|react to|as (?:it|they) happens?"),
                (2, "Events and notifications", r"\bevents?\b|notif\w+|asynchronous\w*|\basync\b"), (2, "Several consumers of the same change", r"fan[- ]out|multiple (?:downstream|consumers|systems)|downstream systems")],
    "PAT-003": [(5, "Strangler-fig named", r"strangl\w+"), (3, "Legacy replacement", r"legacy|mainframe|cobol|decommission|replace (?:the |our )?(?:old|existing)"), (3, "Gradual migration", r"migrat\w+|moderni[sz]\w+|re-?platform\w*|incremental(?:ly)?|phased"),
                (2, "Old and new running together", r"side by side|run(?:ning)? in parallel|coexist\w*|cut[- ]?over")],
    "PAT-004": [(5, "CQRS named", r"\bcqrs\b|read model|query model"), (3, "Reads far outnumber writes", r"read[- ]heavy|read[- ]intensive|reads? (?:far )?outnumber|read scal\w+|separate (?:the )?reads?"), (2, "Reporting or search views", r"reporting views?|search views?|denormali[sz]\w+|dashboards?"),
                (2, "Query performance on busy data", r"query performance|slow quer\w+|heavy quer\w+")],
    "PAT-005": [(5, "RAG named", r"\brag\b|retrieval[- ]augmented"), (3, "Answers grounded in documents", r"grounded|citation\w*|cite sources|knowledge base|policy wordings?|question[- ]answer\w*|answer questions"),
                (3, "Search over enterprise content", r"semantic search|vector (?:search|index|store)|embeddings?|hybrid search|ai search"), (2, "Generative AI assistant", r"\bllm\b|generative ai|genai|gpt|chatbot|copilot|assistant|summari[sz]\w+"),
                (2, "Content in documents", r"documents?|sharepoint|confluence|wiki|pdfs?|claim files?")],
    "PAT-006": [(5, "Agents named", r"\bagent(?:ic|s)?\b|agentic"), (3, "Multi-step tasks with tools", r"multi[- ]step|tool calls?|calls? (?:several|multiple) (?:systems|apis|tools)|plan and (?:act|execute)|autonomous\w*"), (3, "Human approval of actions", r"human (?:approval|in the loop)|approve\w*|sign[- ]off"),
                (2, "Actions in other systems", r"take actions?|update (?:the )?(?:claim|policy|record)|draft (?:a )?letters?|orchestrate tasks?")],
    "PAT-007": [(5, "Saga named", r"\bsaga\b"), (3, "Transaction across services", r"distributed transactions?|multi[- ]service transactions?|across (?:several |multiple )?services|two[- ]phase commit"), (3, "Compensation or rollback", r"compensat\w+|roll ?back|undo|reverse (?:a|the) (?:step|payment|booking)"),
                (2, "Long-running business process", r"long[- ]running|multi[- ]step (?:process|workflow)|workflow|orchestrat\w+")],
    "PAT-008": [(5, "Outbox named", r"\boutbox\b"), (4, "Database and event must agree", r"dual[- ]write|exactly[- ]once|lost events?|at[- ]least[- ]once|event and (?:the )?(?:database|data) (?:must|should)|consisten\w+ between (?:the )?(?:database|data)"),
                (3, "Publish after commit", r"publish\w* (?:an? )?events?\b[^.]{0,40}(?:commit|transaction|database)|reliabl\w+ (?:event|messag)\w+"), (2, "Events from a database change", r"change data capture|\bcdc\b|transaction(?:al)?")],
    "PAT-009": [(5, "Anti-corruption layer named", r"anti[- ]corruption|\bacl\b"), (3, "Protect the new model from a legacy or vendor model", r"legacy (?:model|data model|schema)|vendor (?:model|schema)|translate (?:between|the)|canonical (?:model|format)|isolate"),
                (2, "Third-party or package system", r"third[- ]party|package(?:d)? (?:system|application|software)|guidewire|duck creek|sap\b|salesforce"), (2, "Adapter or translator", r"adapter|translator|mapping layer")],
    "PAT-010": [(5, "BFF named", r"\bbff\b|backend[- ]for[- ]frontend"), (3, "Different clients need different APIs", r"web and mobile|mobile and web|per[- ]channel|channel[- ]specific|different (?:clients|channels|front ?ends)|client[- ]specific"),
                (2, "Front-end applications", r"mobile app|front ?ends?|\bportal\b|single[- ]page|\bspa\b|web app")],
    "PAT-011": [(5, "Lakehouse named", r"lakehouse|medallion|bronze|delta lake"), (3, "Analytics platform", r"data (?:lake|platform|warehouse)|analytics platform|databricks|snowflake|\betl\b|\belt\b"), (3, "Data science or reporting at scale", r"machine learning|feature store|\bbi\b|business intelligence|power bi|reporting"),
                (2, "Many data sources", r"ingest\w*|data sources?|historical data|batch")],
    "PAT-012": [(5, "Zero trust or private endpoints named", r"zero[- ]trust|private endpoints?|private link|no public (?:access|endpoint)|private connectivity"), (3, "Network isolation required", r"network isolation|isolat\w+ (?:network|workload)|data exfiltration|public internet"),
                (3, "Sensitive or regulated data", r"restricted data|confidential data|regulated|\bpii\b|personal data|special[- ]category|\bgdpr\b|health data|payment card"), (2, "Security-first requirement", r"secure by default|least privilege|managed identity|key vault|security review|penetration")],
}

# authored pairs of blueprints that are normally used together
COMBINE = {frozenset(p): why for p, why in [(("PAT-005", "PAT-012"), "A RAG assistant over sensitive content is normally deployed on the zero-trust private network."), (("PAT-005", "PAT-006"), "An agent that answers from documents uses retrieval for its knowledge and tools for its actions."),
                                              (("PAT-003", "PAT-009"), "A strangler-fig migration normally uses an anti-corruption layer to keep the legacy model out of the new services."), (("PAT-002", "PAT-008"), "Event-driven services publish reliably by writing the event and the data change in one transaction."),
                                              (("PAT-007", "PAT-008"), "Each saga step needs its event and its data change to commit together."), (("PAT-004", "PAT-002"), "Read models are normally kept up to date from the event stream."),
                                              (("PAT-001", "PAT-010"), "Experience APIs are often built as one back-end-for-frontend per channel."), (("PAT-011", "PAT-012"), "A lakehouse that holds restricted data is deployed on private connectivity.")]}

ESTATE_BONUS = [  # (pattern, points, label, test over the systems named in the requirements)
    ("PAT-003", 2, "A named system is end-of-life or in extended support", lambda sy: any(x["lifecycle"] in ("eol", "extended") for x in sy)),
    ("PAT-009", 2, "A named system is a legacy or packaged application", lambda sy: any(x["lifecycle"] in ("eol", "extended") for x in sy)),
    ("PAT-001", 1, "Three or more existing systems are named", lambda sy: len(sy) >= 3),
]


def recommend(req: dict) -> dict:
    s = get_store()
    t = req["text"]
    pats = {p["id"]: p for p in s.patterns}
    req_words = {w for w in _words(t) if len(w) >= 5 and w not in STOP}
    ranked = []
    for pid, sigs in SIGNALS.items():
        meta = pats[pid]
        bp = bp_gen.BLUEPRINTS[pid]
        matched = []
        for weight, label, rx in sigs:
            m = re.search(rx, t, re.I)
            if m:
                matched.append(dict(label=label, weight=weight, term=m.group(0)[:40], evidence=_snippet(t, m.start())))
        tags = [tg for tg in meta["tags"] if re.search(r"(?<![\w-])" + re.escape(tg.replace("-", "[- ]")).replace(r"\[-\ \]", "[- ]") + r"(?![\w-])", t, re.I)]
        if tags:
            matched.append(dict(label=f"Blueprint tag named: {', '.join(tags)}", weight=3, term=tags[0], evidence=_snippet(t, re.search(re.escape(tags[0].replace("-", " ")), t, re.I).start()) if re.search(re.escape(tags[0].replace("-", " ")), t, re.I) else ""))
        when_words = {w for w in _words(" ".join(bp["when"])) if len(w) >= 5 and w not in STOP}
        shared = sorted(when_words & req_words)
        overlap = min(4, len(shared))
        estate = [dict(label=lbl, weight=pts) for p, pts, lbl, test in ESTATE_BONUS if p == pid and req["systems"] and test(req["systems"])]
        score = sum(x["weight"] for x in matched) + overlap + sum(x["weight"] for x in estate)
        ranked.append(dict(id=pid, name=meta["name"], category=meta["category"], summary=meta["summary"], score=score, matched=matched, when_overlap=shared[:6], when_points=overlap, estate=estate,
                           max_score=sum(w for w, _, _ in sigs) + 3 + 4))
    ranked.sort(key=lambda r: (-r["score"], r["id"]))
    top, second = ranked[0], ranked[1]
    enough = top["score"] >= 4 and any(m["weight"] >= 2 for m in top["matched"])
    if not enough:
        return dict(ranked=ranked, recommended=None, alternatives=[dict(id=r["id"], name=r["name"], score=r["score"], why_not="", choose_when=bp_gen.BLUEPRINTS[r["id"]]["when"][0]) for r in ranked[:3]],
                    combine=[], needs_more_detail=True, threshold=4,
                    message="The requirements do not point clearly to one blueprint. Describe what the system does, who uses it and what it connects to, or pick a blueprint yourself.")
    margin = (top["score"] - second["score"]) / top["score"]
    confidence = round(0.2 + 0.5 * min(1.0, top["score"] / 12) + 0.3 * margin, 2)
    bp = bp_gen.BLUEPRINTS[top["id"]]
    watch = []
    if re.search(r"openai\.com|chatgpt|public llm|anthropic api|openai api|external llm", t, re.I) and top["id"] in ("PAT-005", "PAT-006", "PAT-012"):
        watch.append("The requirements mention a public LLM API. Standard STD-AI-004 prohibits sending enterprise data to one, so the Studio will propose Azure OpenAI.")
    if req.get("classification") in ("confidential", "restricted") and top["id"] != "PAT-012":
        watch.append(f"The data is {req['classification']}. Review the zero-trust private connectivity blueprint alongside this one (the Customisation step turns on private endpoints).")
    for a in bp["anti"]:
        if "direct" in a.lower() and re.search(r"direct (?:db|database)", t, re.I):
            watch.append(f"Anti-pattern in this blueprint: {a}.")
    rec = dict(id=top["id"], name=top["name"], title=bp["title"], confidence=confidence, score=top["score"], margin=round(margin, 2), rationale=top["matched"] + [dict(label=e["label"], weight=e["weight"], term="", evidence="") for e in top["estate"]],
               when_overlap=top["when_overlap"], watch_outs=watch, when_to_use=bp["when"])
    alts = []
    for r in ranked[1:4]:
        mine = {m["label"] for m in r["matched"]}
        theirs = [m["label"] for m in top["matched"] if m["label"] not in mine][:3]
        if r["score"] == 0:
            why = "Nothing in the requirements matches the situations this blueprint is for."
        else:
            why = f"Matches {len(r['matched'])} cue(s) ({'; '.join(m['label'] for m in r['matched'][:3])}) for {r['score']} points, against {top['score']} for {top['name']}."
            if theirs:
                why += f" {top['name']} also matches: {'; '.join(theirs)}."
        alts.append(dict(id=r["id"], name=r["name"], category=r["category"], score=r["score"], matched=[m["label"] for m in r["matched"]], why_not=why, choose_when=bp_gen.BLUEPRINTS[r["id"]]["when"][0]))
    combine = []
    for r in ranked[1:]:
        if r["score"] >= 4 and frozenset((top["id"], r["id"])) in COMBINE:
            combine.append(dict(id=r["id"], name=r["name"], reason=COMBINE[frozenset((top["id"], r["id"]))]))
    return dict(ranked=ranked, recommended=rec, alternatives=alts, combine=combine, needs_more_detail=False, threshold=4, message="")


def suggest_selections(pattern_id: str, req: dict) -> dict:
    """Starting choices for the Customisation step: the blueprint's own technologies, then anything the requirements named. Each value says where it came from."""
    base = cat.default_selections(pattern_id)
    src = {k: "blueprint" for k in base}
    sel = dict(base)
    for key, h in req.get("hints", {}).items():
        if key.startswith("_"):
            continue
        if key == "llm" and "llm" not in cat.blueprint_roles(pattern_id) and "ai_llm" not in cat.blueprint_roles(pattern_id):
            continue
        sel[key] = h["value"]
        src[key] = "requirements"
    if sel.get("llm") == "public_api":
        sel["llm"] = "azure_openai"  # the standard prohibits it; the validation still explains why
        src["llm"] = "standards"
    sel["posture"] = suggest_posture(pattern_id, sel, req)
    src["posture"] = "blueprint standards and requirements"
    if not sel.get("classification") and req.get("classification"):
        sel["classification"] = req["classification"]
    return dict(selections=sel, sources=src)


def suggest_posture(pattern_id: str, sel: dict, req: dict) -> list[str]:
    """Security and operations controls to start with: those that serve the standards the blueprint itself cites, plus those the requirements call for."""
    bp = bp_gen.BLUEPRINTS[pattern_id]
    chosen: list[str] = []
    cited = set(bp["standards"])
    for p in cat.POSTURE:
        if cited & set(p["standards"]):
            chosen.append(p["id"])
    roles = set(cat.blueprint_roles(pattern_id))
    if req.get("classification") in ("confidential", "restricted") or req.get("personal_data"):
        chosen += ["private_endpoints", "tls12", "diagnostics", "pii_masking"]
    if req.get("classification") == "restricted":
        chosen += ["customer_managed_keys"]
    if (sel.get("exposure") or req.get("exposure")) == "internet":
        chosen += ["waf"]
    if req.get("tier") == "tier1":
        chosen += ["high_availability", "backups"]
    if "ai_llm" in roles or "ai_agent" in roles:
        chosen += ["content_filter", "audit_logging", "managed_identity"]
    if "ai_agent" in roles:
        chosen += ["human_in_loop"]
    if "api" in roles or "edge" in roles:
        chosen += ["api_governance"]
    chosen += ["key_vault_secrets", "mandatory_tags"]
    return [p for p in cat.POSTURE_IDS if p in set(chosen)]

