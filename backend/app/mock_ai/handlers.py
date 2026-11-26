"""Narration templates for every AI task. # MOCK

Each template receives the structured facts computed by the real engines and writes the prose a model would.
To use a real LLM, implement `LLMProvider` (see README) and send the same `task` + `input`; this file is then unused.
"""

from __future__ import annotations

from app.mock_ai.narration import handler, template

# ================================================================ copilot
template("copilot.list_dependents", """
{% if count == 0 %}
I found no {{ filter }} applications that depend on {{ target }}.
{% else %}
{{ count }} {{ filter ~ ' ' if filter }}{{ 'application depends' if count == 1 else 'applications depend' }} on {{ target }}: {{ names[:6]|commas }}{{ ' and ' ~ (count - 6) ~ ' more' if count > 6 }}.
{{ critical }} {{ 'is' if critical == 1 else 'are' }} business-critical.{{ ' ' ~ note if note }}
{% if kind in ['technology', 'database'] %}
Each dependency was traced through the graph, for example {{ top_path }}. Direct database access like this couples consumers to the physical schema, so these applications are the first candidates to move behind APIs or events.
{% elif kind == 'api' %}
{{ workflows }} business {{ 'workflow calls' if workflows == 1 else 'workflows call' }} this API, so a breaking change would reach beyond the listed applications.
{% else %}
Review the dependency paths below before changing {{ target }}.
{% endif %}
{% endif %}
""", 0.94)

template("copilot.impact_of", """
{% if kind == 'api' %}Changing {{ name }} impacts {{ direct }} applications and {{ workflows }} workflows.{% else %}{{ name }} {{ 'going down' if change == 'outage' else ('being retired' if change == 'retirement' else 'changing') }} would reach {{ direct }} applications directly and {{ workflows }} workflows.{% endif %}
A further {{ indirect }} applications are affected indirectly, across {{ teams }} teams{{ ' (' ~ team_names|commas ~ ')' if team_names }}. {{ critical }} of the directly affected applications are business-critical, which gives a blast-radius score of {{ risk }}/100 ({{ rating }}).
Most exposed: {{ top[:4]|commas }}. Coordinate a versioned rollout with these owners before making the change.
""", 0.93)

template("copilot.find_assets", """
{{ count }} of {{ total }} applications match ({{ desc }}). {% if names %}The highest-debt matches are {{ names[:4]|commas }}.{% endif %}
{% if domains %}They are concentrated in {{ domains.items()|sort(attribute='1', reverse=True)|map(attribute='0')|list|first }}.{% endif %}
""", 0.9)

template("copilot.capabilities_of", """
{% if mode == 'app' %}{{ name }} supports {{ count }} business capabilities: {{ caps|commas }}. Any change to it carries risk for these capabilities.{% else %}{{ count }} applications support {{ name }}{{ ': ' ~ apps[:5]|commas if apps }}. Capability overlap between them is a candidate for consolidation.{% endif %}
""", 0.92)

template("copilot.compare", """
Comparing {{ names|commas }}: {{ highest }} carries the most technical debt ({{ debts|commas }} respectively). Hosting is {{ hosting|map('lower')|list|commas }}.{% if shared %} They share {{ shared|commas }}, which couples their release cycles.{% else %} They share no datastore.{% endif %}
""", 0.9)

@handler("copilot.explain")
def _explain(d):
    k = d["kind"]
    if k == "application":
        t = (f"{d['name']} is a {d['criticality']}-criticality application in {d['domain']}, {'hosted on-premises' if 'premises' in d['hosting'].lower() else 'hosted on ' + d['hosting']} and owned by {d['team']}. {d['description']} "
             f"Its technical debt score is {d['debt']}/100: {' '.join(d['why']) or 'no major drivers'}. "
             f"{d['dependents']} applications depend on it directly and it has {d['findings']} assessment finding(s) and {d['drift']} open drift item(s).")
    elif k == "api":
        t = (f"{d['name']} {d['version']} is a {d['protocol']} API ({d['lifecycle']}) exposed by {d['exposed_by']}{' through the API gateway' if d['gateway'] else ' directly (no gateway)'}. "
             f"It has {d['consumers']} consuming applications and is used in {d['workflows']} business workflows.")
    elif k == "database":
        t = (f"{d['name']} is a {d['engine']} datastore ({d['lifecycle']}), {d['size']:,} GB, classified {d['classification']}. "
             f"{d['users']} applications use it, {d['direct']} of them by direct database access.")
    elif k == "cloud":
        t = f"{d['name']} is a {d['type'].replace('_', ' ')} in {d['region']} ({d['env']}). " + (d["drift"] if d["drift"] else "It matches its approved infrastructure code.")
    else:
        t = f"{d['name']} is a {d['domain']} workflow with {d['steps']} steps handling about {d['volume']:,} items a day."
    return t, 0.91, {}


template("copilot.risk_summary", """
The estate's technical debt score is {{ debt }}/100. The main risks are {{ critical }} critical assessment findings (led by "{{ top_finding }}"), {{ spofs }} single points of failure (most concentrated in {{ top_spof }}) and {{ drift }} critical configuration drift items.
Highest-debt application: {{ top_debt }}. Start with the critical findings; they also unlock most of the modernization plan.
""", 0.9)

template("copilot.spof", """
{{ count }} applications are single points of failure: {{ names[:6]|commas }}. The largest is {{ top }}: {{ top_reason }}.
Add redundancy or decouple consumers from these hubs before changing them.
""", 0.92)

@handler("copilot.stats")
def _stats(d):
    if d.get("label") == "direct database integrations":
        return f"There are {d['n']} direct database integrations. These should move behind APIs or events, since they bypass authorisation and couple consumers to schemas.", 0.97, {}
    if d.get("label"):
        return f"The catalog holds {d['n']} {d['label']}.", 0.97, {}
    return "Here is the current estate inventory.", 0.9, {}


template("copilot.direct_db", """
{{ count }} direct DB integrations should move behind APIs/events. They touch {{ dbs }} datastores; {{ top_db }} is the most exposed with {{ top_n }} direct consumers.
Replacing them with system APIs or Kafka events is the first step of Wave 1 in the modernization plan.
""", 0.95)

template("copilot.path", """
{% if found %}{{ a }} reaches {{ b }} in {{ hops }} hops{{ ' via ' ~ via|commas if via }}{{ ' using ' ~ styles|commas ~ ' integrations' if styles }}. {% if story %}This is the finance-to-analytics flow; a failure at any hop stops customer billing data reaching the warehouse.{% else %}This is the shortest dependency path in the coupling graph.{% endif %}{% else %}No dependency path connects {{ a }} and {{ b }}.{% endif %}
""", 0.93)

template("copilot.owner", """
{{ name }} is owned by {{ owner }} in the {{ team }} team. That team owns {{ n }} application{{ '' if n == 1 else 's' }} in total.
""", 0.95)

template("copilot.duplication", """
Three systems act as the customer master: {{ names|commas }}. Documents disagree about which one is the system of record; the most authoritative document names {{ recommended }}.
Consolidating onto one master would remove duplicate stewardship and the reconciliation integrations between them.
""", 0.93)

template("copilot.drift", """
{{ first_summary }} The resource is {{ first_resource }} and the deviation breaks {{ standard }}. In total {{ total }} resources have drifted from their approved design, {{ open }} still open.
Reconcile the Terraform state or raise a time-boxed exception.
""", 0.96)

@handler("copilot.standard")
def _standard(d):
    if d.get("id") is None:
        return f"There are {d['count']} architecture standards in the catalogue across {len(d['cats'])} categories.", 0.9, {}
    if d.get("openai"):
        t = (f"Azure OpenAI is approved; direct public endpoint violates policy. {d['id']} requires private endpoints for PaaS services holding enterprise data."
             + (f" {d['first']} currently breaks it." if d.get("first") else ""))
    else:
        t = f"{d['id']} ({d['severity']}): {d['statement']} {d['violations']} drift item(s) currently reference it."
    return t, 0.95, {}


template("copilot.cost", """
{{ top }} is the most expensive application at {{ top_cost|money }} a year. The top ten account for {{ share }}% of the {{ total|money }} annual run cost.
""", 0.9)

template("copilot.debt", """
Estate technical debt is {{ overall }}/100. {{ worst_domain }} is the most indebted domain at {{ worst_score }}{{ ' and ' ~ top ~ ' is the largest single contributor' if top }}.
""", 0.9)

template("copilot.modernization", """
The balanced plan runs {{ waves|commas }} across {{ items }} initiatives. Wave 1 starts with {{ wave1[:3]|commas }} because everything later depends on stable APIs.
""", 0.9)

template("copilot.documents", """
{% if app is defined %}{{ top_gap }}.{% else %}{{ documents }} documents were analysed: {{ conflicts }} conflicts and {{ gaps }} gaps were found, and the estate is {{ coverage }}% documented.{% endif %}
{% if top_gap and app is not defined %}The most serious gap: {{ top_gap }}.{% endif %}{% if hits %} Relevant documents: {{ hits[:3]|commas }}.{% endif %}
""", 0.9)

template("copilot.help", "I can answer questions about dependencies, change impact, risk, standards, configuration drift, ownership and the modernization plan. Pick an example below or ask in your own words.", 0.95)

template("copilot.unknown", """
I couldn't map "{{ query }}" to the architecture graph{{ ' (I recognised ' ~ entities|commas ~ ')' if entities }}. Try naming an application, API, database or technology, or pick one of these.
""", 0.35)

# ============================================================== modules
template("overview.briefing", """
The estate runs {{ apps }} applications and {{ apis }} APIs with an estate technical-debt score of {{ debt }}/100. {{ critical }} critical findings need attention, led by {{ direct_db }} direct DB integrations that should move behind APIs/events.
{{ spofs }} single points of failure and {{ drift_open }} open configuration-drift items add operational risk, and only {{ coverage }}% of the estate is documented. The modernization plan sequences the work as {{ waves|commas }}.
""", 0.9)

template("discovery.summary", """
The scan of {{ sources }} sources found {{ assets }} assets: {{ by_type|commas }}. {{ shadow }} appear to be shadow IT not in the CMDB, and {{ duplicates }} potential duplicates were merged by name and owner matching.
""", 0.88)

template("discovery.import", """
{{ filename }} contains {{ rows }} applications. {{ matched }} match the discovered estate cleanly{{ ', ' ~ conflicts ~ ' match but disagree with what discovery observed' if conflicts }}{{ ', and ' ~ probable ~ ' look like the same system under a different name' if probable }}.
{% if new %}{{ new }} {{ 'application is' if new == 1 else 'applications are' }} not in the estate at all and should be investigated as shadow IT or newly onboarded systems.{% endif %}
{% if missing %}In the other direction, {{ missing }} {{ 'application' if missing == 1 else 'applications' }} found by discovery {{ 'is' if missing == 1 else 'are' }} absent from this export{{ ', including ' ~ missing_top|commas if missing_top }}, so the CMDB is incomplete.{% endif %}
{% if fields %}The disagreements are mostly in {{ fields|commas }}; discovery should be treated as the more reliable source.{% endif %}
""", 0.9)

template("assessment.summary", """
The assessment raised {{ total }} findings: {{ critical }} critical and {{ high }} high. The most important is "{{ top[0] }}"{{ ', followed by "' ~ top[1] ~ '"' if top|length > 1 }}{{ ' and "' ~ top[2] ~ '"' if top|length > 2 }}.
Obsolete technology and single points of failure account for most of the remediation effort.
""", 0.9)

template("finding.explain", """
{{ title }}. {{ why }} Recommended action: {{ recommendation }} Estimated effort: {{ effort }}.
""", 0.9)

template("debt.summary", """
Estate debt is {{ overall }}/100, {{ 'up' if delta > 0 else 'down' }} {{ delta|abs }} points over the last 12 months. {{ worst_domain }} is the highest-debt domain at {{ worst_score }}; the largest application contributors are {{ top_apps[:3]|commas }}.
""", 0.9)

template("impact.summary", """
{% if kind == 'api' %}Changing {{ name }} impacts {{ direct }} applications and {{ workflows }} workflows.{% else %}{{ name }} {{ 'going down' if change == 'outage' else 'changing' }} affects {{ direct }} applications directly and {{ workflows }} workflows.{% endif %}
{{ indirect }} more are affected indirectly across {{ teams }} teams. Blast-radius risk is {{ risk }}/100 ({{ rating }}); {{ critical }} business-critical applications are directly exposed.
""", 0.93)

template("drift.summary", """
{{ total }} resources have drifted from their approved design, {{ open }} still open and {{ critical }} critical. The most serious: {{ top }}
""", 0.95)

template("design.recommendation", """
Option {{ winner }} ({{ winner_name }}) scores highest at {{ score }}/10, ahead of {{ runner_name }} at {{ runner_score }}. It wins mainly on {{ top_criterion }}. {% if sensitive %}The ranking is sensitive to the weight of {{ sensitive_criterion }}: raising it by 50% would change the winner.{% else %}The ranking is stable when any single criterion weight changes by 50%.{% endif %}
""", 0.87)

template("review.summary", """
Verdict: {{ verdict }}. The submission "{{ title }}" is {{ readiness }}% ready for the Architecture Review Board with {{ blockers }} blocking issue{{ '' if blockers == 1 else 's' }} and {{ warnings }} warning{{ '' if warnings == 1 else 's' }}. NFR coverage is {{ nfr }}%.
{% if blockers %}Resolve the blocking items before the meeting.{% else %}No blocking standards violations were found.{% endif %}
""", 0.9)

template("standards.summary", """
{{ passed }} checks passed, {{ warned }} produced warnings and {{ failed }} failed across {{ components }} components.{% if headlines %} Key violations: {{ headlines[:3]|commas }}{% endif %}
""", 0.93)

template("blueprint.summary", """
{{ name }} fits when {{ when|map('lower')|join('; ') }}. The blueprint contains {{ components }} components with ready-to-use Terraform and OpenAPI starters.
""", 0.9)

template("modernization.summary", """
The {{ scenario }} scenario delivers {{ waves|commas }} in about {{ weeks }} weeks for {{ cost|money }}, returning {{ value|money }} in annual value. The critical path runs through {{ critical_path[:3]|commas }}.
""", 0.88)

template("codegen.summary", """
Generated {{ files }} files for {{ name }}. {{ passed }} of {{ total }} deployability checks passed.
""", 0.9)

template("documents.summary", """
{{ documents }} documents were analysed: {{ conflicts }} conflicts and {{ gaps }} gaps were found, and the estate is {{ coverage }}% documented.
""", 0.9)


# ================================================================ blueprint intelligence studio
template("studio.requirements", """
The text has {{ words }} words. {{ found }} of the 6 non-functional targets the review requires {{ 'is' if found == 1 else 'are' }} stated{% if present %} ({{ present|commas }}){% endif %}{% if missing %}; not stated: {{ missing|commas }}{% endif %}.
{% if tier %}It reads as {{ tier }} criticality. {% endif %}{% if exposure %}{{ 'It is used from the internet.' if exposure == 'internet' else 'It is used by internal staff only.' }} {% endif %}{% if classification %}The data looks {{ classification }}. {% endif %}{% if systems %}It names {{ systems|commas }} from the estate.{% endif %}
""", 0.86)

template("studio.recommendation", """
{% if not name %}The requirements do not point clearly to one blueprint. {{ closest|commas }} came closest, but none reached the {{ threshold }}-point threshold. Add what the system does, who uses it and what it connects to, or choose a blueprint yourself.
{% else %}{{ name }} is the closest fit, with {{ score }} points{% if reasons %} from {{ reasons|commas }}{% endif %}. {% if alt %}The next closest is {{ alt }} with {{ alt_score }} points. {% endif %}{% if combine %}{{ combine }} {% endif %}{% if watch %}{{ watch }}{% endif %}
{% endif %}
""", 0.88)

template("studio.validation", """
"{{ title }}" is {{ readiness }}% ready and the verdict is {{ verdict }}. {{ critical }} critical, {{ high }} high, {{ medium }} medium and {{ low }} low {{ 'gap is' if (critical + high + medium + low) == 1 else 'gaps are' }} open. {{ assessed }} of {{ total }} components could be assessed by the standards library.
{% if top %}Resolve first: {{ top|commas }}.{% else %}No critical or high gaps are open.{% endif %}
""", 0.9)

template("studio.summary", """
{{ title }} is built on the {{ blueprint }} blueprint, deployed on {{ cloud }} in {{ region }}{% if llm %} with {{ llm }}{% endif %}. The review engine rates it {{ readiness }}% ready with a verdict of {{ verdict }}. {{ open_count }} {{ 'gap remains' if open_count == 1 else 'gaps remain' }} open{% if top %}, led by {{ top|commas }}{% endif %}.
""", 0.88)

template("studio.submission", """
"{{ title }}" was submitted as {{ arb_id }}. It enters the review queue at the {{ stage }} stage with a readiness of {{ readiness }}% and {{ conditions }} {{ 'condition' if conditions == 1 else 'conditions' }} attached for the board.
""", 0.9)
