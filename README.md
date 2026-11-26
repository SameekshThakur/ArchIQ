# ArchIQ: AI-powered Enterprise Architecture platform

ArchIQ discovers an enterprise's application estate, builds a living knowledge graph, assesses it, and then helps
architects design, govern, modernise and generate code for the target state. The demo enterprise is **Northwind
Assurance**, an insurer with 69 applications, 180 APIs, 45 databases and 229 integrations.

Everything runs **offline**. There is no database and no external LLM: the data is seeded JSON held in memory, and
every "AI" answer comes from a deterministic engine behind an `LLMProvider` interface (see
[Mock AI](#how-the-mock-ai-works) and [Using the Azure OpenAI model](#using-the-azure-openai-model)).

## Run it

Requirements: Python 3.11+, Node 22.9+ (`frontend/.nvmrc`).

```bash
make install     # backend venv + frontend deps
make dev         # API on :8000 and web app on :5173
```

**Windows (no `make`):**

1. Install Python 3.11+ (tick "Add python.exe to PATH") and Node.js 22.9+ (LTS).
2. Double-click `setup.bat` once. It creates the Python environment, installs both sets of packages and runs a checklist.
3. Double-click `dev.bat`. It starts the API and the web app in one window, waits until both are ready and opens the browser. Ctrl+C stops both.

If anything misbehaves, run `python scripts\doctor.py`. It checks the Python and Node versions, installed packages, free ports, and write access, and says how to fix each problem.
`dev.bat` and `setup.bat` were written without access to a Windows machine; `scripts/dev.py` and `scripts/doctor.py` (which do the real work) are tested on Linux, and use only cross-platform code.
The launcher forces UTF-8 for the API and binds to `127.0.0.1` rather than `localhost`, which avoids two common Windows problems (non-ASCII text in the console and IPv6 `localhost` resolving to `::1`).

By hand, in two terminals:

```bat
:: terminal 1: API
cd backend
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

:: terminal 2: web app
cd frontend
npm install
npm run dev
```

Tests on Windows: `cd backend && set AI_LATENCY=0 && python -m pytest`, and `cd frontend && npm run test`.

On macOS or Linux, `python3 scripts/dev.py` does the same as `make dev`.

Open <http://127.0.0.1:5173>. API docs are at <http://127.0.0.1:8000/docs>.

```bash
make test        # backend pytest + frontend vitest
make build       # tsc --noEmit + production build
make check       # test + build
make seed        # regenerate the seed JSON (faker seed 42, fully deterministic)
```

Useful environment variables for the backend (`backend/.env` is read if present):

| Variable | Default | Meaning |
|---|---|---|
| `PROVIDER` | `mock` | `mock` (built-in narrator) or `azure_openai`; see "Using the Azure OpenAI model". |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` | empty, empty, `gpt-5-mini` | Only used when `PROVIDER=azure_openai`. |
| `AI_LATENCY` | `1` | `1` simulates 0.6–2.5 s AI latency (so skeletons and "thinking" traces are visible); `0` is instant (used by tests). |
| `CORS_ORIGINS` | localhost:5173 | Comma separated list. |
| `ARCHIQ_DB` | `backend/data/archiq.db` | SQLite file for things you add (uploaded documents, ad-hoc reviews, inventory imports). `:memory:` turns saving off. The seeded estate is never written to it. Delete the file to start clean. |

## What is in the box

| Route | Module | What it does |
|---|---|---|
| `/` | Executive overview | KPIs, AI briefing, debt by domain, the finance→analytics chain, top risks, roadmap. |
| `/discovery` | Discovery | Nine mock connectors, reconciliation, shadow IT, a streamed scan. |
| `/graph` | Knowledge graph | Force graph grouped by domain: find-in-view with zoom, domain and criticality filters, saved views, PNG/SVG export, full screen, hubs, single points of failure, path finder. |
| `/documents` | Document intelligence | 60 documents: entities, relations, conflicts, gaps, coverage, reconstructed diagram, upload. |
| `/assessment` | Assessment | 50 findings: smells, SPOFs, obsolete tech, duplication, coupling. Re-runnable. |
| `/debt-radar` | Debt radar | Per-application debt scoring, heatmap, contributors, trend. |
| `/impact` | Change impact | Blast radius for any asset and change type. |
| `/target-architecture` | Target architecture | NFR form → three candidate architectures with diagrams, radar and sensitivity. |
| `/decisions` | Decision agent | Weighted matrix, sensitivity, ADR generator, decision log. |
| `/blueprints` | Blueprints | 12 reference patterns with diagrams, guidance and a downloadable starter bundle. |
| `/studio` | Blueprint Intelligence Studio | Requirements → recommended blueprint → customised, editable, validated architecture → documentation and starter ZIP → ARB submission. |
| `/standards` | Standards | 45-item catalogue and a design checker with remediation. |
| `/reviews`, `/reviews/:id` | Review agent | Pre-ARB review: readiness score, go / conditional / no-go, findings, conditions. |
| `/modernization` | Modernization | Three waves, three scenarios, Gantt, critical path, value curve, movable initiatives. |
| `/codegen` | Architecture to code | Terraform, Bicep, OpenAPI 3.1, FastAPI, Spring Boot, Dockerfile, CI, with a deployability checklist and zip download. |
| `/drift` | Drift detection | Approved IaC vs deployed state, mapped to the standard each deviation breaks. |
| `/copilot` and ⌘J | Copilot | Natural-language questions answered from the graph, streamed with reasoning, evidence and follow-ups. |

Keyboard: `⌘K` palette, `⌘J` Copilot, `/` focus search, `?` cheat-sheet, `g` then a letter to navigate (`g a` is
Assessment), `Esc` closes the inspector. Any entity link opens the same right-hand inspector drawer.

### The Northwind story

The seed data is built around a set of facts that the demo, the Copilot and the tests all agree on:

- Finance data flows **SAP S/4HANA → MuleSoft → Salesforce → Snowflake**.
- There are exactly **17 direct database integrations**.
- **Oracle 12c** (Policy Master DB) is used by **9 applications, 4 of which support Claims**. Ask the Copilot
  *"Show all applications dependent on Oracle 12c that support Claims."* and you get exactly those four, with paths.
- **Customer API v2** is consumed by **14 applications and 6 workflows**: *"Changing Customer API impacts 14
  applications and 6 workflows."*
- Drift: *"Approved design says private endpoint; deployed environment uses public endpoint."*
- Policy: *"Azure OpenAI is approved; direct public endpoint violates policy"* (STD-SEC-014).
- Modernization runs **Wave 1 APIs, Wave 2 Data decoupling, Wave 3 Agentification**.
- There are three customer-master systems, several single points of failure, and an undocumented
  Policy Admin Core → Oracle link that is the largest documentation gap.

`backend/tests/test_story_facts.py` asserts every one of these.

## Architecture

```
frontend (React 18, Vite)            backend (FastAPI)
┌────────────────────────┐   /api/v1 ┌───────────────────────────────────────────────┐
│ pages (lazy chunks)    │──────────▶│ routers (core, knowledge, design, delivery, files)    │
│ TanStack Query cache   │◀──SSE─────│   │                                           │
│ Zustand (UI, copilot,  │           │   ▼                                           │
│   design brief)        │           │ services/ai.narrate(task, facts, steps, ev)   │
│ inspector registry     │           │   │                      ▲                    │
└────────────────────────┘           │   ▼                      │ facts              │
                                     │ LLMProvider ──▶ narration│ engines            │
                                     │  (mock)                  │ graph · rules ·    │
                                     │                          │ scoring · generators│
                                     │ in-memory Store ◀── seeded JSON (faker 42)    │
                                     └───────────────────────────────────────────────┘
```

**Facts are computed, prose is generated.** Findings, SPOFs, debt scores, impact sets, standards results and
schedules come from real engines (networkx graph analysis, rule evaluation, scoring, a dependency-aware
scheduler). The provider only turns those structured facts into language. This is what makes the mock honest, and
what lets a real LLM replace it without touching any engine.

Every AI response carries the same envelope, which the UI renders as the summary, reasoning trace, evidence chips
and the *"AI-generated · confidence 0.91 · view evidence"* footer:

```json
{ "summary": "...", "confidence": 0.91, "evidence": [{"kind": "finding", "id": "F-001", "label": "..."}],
  "reasoning_steps": [{"label": "Traverse graph", "detail": "...", "duration_ms": 280}],
  "generated_at": "...", "provider": "mock", "task": "impact.summary" }
```

Errors use one envelope everywhere: `{"error": {"code", "message", "request_id", "details"}}`.

Frontend structure: `src/features/<module>` for pages, `src/components/ui` for the hand-built design system
(`/_design` is its living style guide), `src/components/viz` for lazily loaded ECharts, Mermaid, React Flow and
force-graph wrappers, `src/features/inspector` for the drawer registry, and `src/store` for UI, Copilot and
design-brief state. Charts read their colours from the CSS-variable tokens, so dark and light both work.

## How the mock AI works

- **`LLMProvider`** (`backend/app/mock_ai/provider.py`) has two methods: `generate(LLMRequest)` and `stream(LLMRequest)`.
  `LLMRequest` carries a `task` name and the structured `input` facts.
- **`MockLLMProvider`** looks up the task in `mock_ai/narration.py`, renders either a Jinja template or a Python
  handler from `mock_ai/handlers.py`, waits a deterministic 0.6–2.5 s derived from the request (so repeated calls
  feel consistent), and streams the text as word-sized tokens.
- **Copilot** (`mock_ai/copilot/`) has an entity lexicon, an intent router and one handler per intent. Each
  handler runs a real query over the graph and returns `{headline, cards, steps, evidence, followups}`. Thirty
  suggested questions are tested to return sensible answers. Unrecognised questions get "did you mean" help, not a
  fabricated answer.
- **Results are deterministic.** Seeds are fixed, betweenness is computed exactly rather than sampled, and a test
  confirms identical output across `PYTHONHASHSEED` values.

## Using the Azure OpenAI model

`AzureOpenAIProvider` (`backend/app/mock_ai/azure_openai.py`) is built in. The built-in narrator stays as the default and as the fallback.

1. Copy `.env.example` to `backend/.env` (git-ignored) and set:

```
PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://<resource>.cognitiveservices.azure.com
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_DEPLOYMENT=gpt-5-mini
AZURE_OPENAI_API_VERSION=2025-04-01-preview
```

2. `pip install -r backend/requirements.txt` (adds `openai`), then `cd backend && python scripts/check_llm.py`. It makes one small call and prints one real narration. Once the app runs, `GET /api/v1/ai/status` shows which model is active and `POST /api/v1/ai/test` repeats the small call.
3. Start the app as usual. AI summaries, the Copilot, review and design recommendations now go through the model. The footer of each AI panel shows the model name when the model wrote it.

How it stays trustworthy:

- **Facts are still computed, not generated.** The engines produce the facts; the model only writes them up. It receives the JSON facts plus the built-in narrator's text as a reference draft, and is told to use nothing else.
- **Invented figures are rejected.** If the answer contains a number that is in neither the facts nor the draft, it is discarded and the built-in text is used (`LLM_VERIFY_NUMBERS=false` turns this off).
- **It never breaks a page.** A wrong key, timeout, quota error, content filter or empty answer falls back to the built-in narrator and is counted in `/ai/status`. If `PROVIDER=azure_openai` but the key is missing, the app starts on the built-in narrator and `/ai/status` says why.
- **Repeat views are instant.** Answers are cached per task and facts for the life of the server.
- **Copilot streaming** releases the checked answer word by word. It is not token-by-token from the model, because an answer that fails the figures check could not be taken back once shown.
- **Fixed replies stay as templates** (the Copilot help and "did you mean" messages). Generated code and documents (Terraform, OpenAPI, ADR text) are still template output; only the prose summaries use the model.
- **Model settings.** `gpt-5-mini` is a reasoning model, so the call sends `max_completion_tokens` and `reasoning_effort` (default `low`) and no `temperature`. Tune with `LLM_REASONING_EFFORT`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT`, `LLM_CONCURRENCY`.
- **Secrets.** The key is read from the environment or `backend/.env` only, held as a secret value, and never returned by any endpoint. For production, use a private endpoint and managed identity instead of a key (standards STD-SEC-004 and STD-SEC-014).
- The backend tests use a fake client and never call the network (`tests/test_llm_provider.py`).

## Connections to other platforms

The **Connections** page (`/connections`, in the sidebar under Start) is where credentials are entered, tested and kept. It
works before any analysis exists. The platforms are **used from a new analysis**: step 3 of New analysis lists them, and
whatever is ticked is read when the run starts (see "Guided start"). Syncing on the Connections page only checks that a
connection works and shows what it would bring. Every connector is **read-only**: it never creates, changes or deletes
anything in the platform.

| Platform | What is read | API used | Where it shows up in ArchIQ |
| --- | --- | --- | --- |
| ServiceNow CMDB | Business applications: name, owner, criticality, lifecycle, support group, business unit | Table API (`/api/now/table/<table>`), basic auth or OAuth token | Reconciled against the estate and saved as a Discovery import |
| Jira | Issues from the chosen projects or JQL | `/rest/api/3/search/jql` (Cloud), falls back to `/rest/api/2/search` (Data Center) | Open and done work per application |
| Azure Resource Graph | Deployed resources and their properties across subscriptions | Resource Graph REST, service principal with the Reader role | Standards checks on deployed resources; deployed side of live drift |
| GitHub | Terraform and Bicep files; Markdown under `docs/`, `adr/`, `architecture/`, `decisions/`, and the README | REST (trees and contents), fine-grained token with Contents: read | Standards checks on infrastructure code; ADRs into Document intelligence; approved side of live drift |
| Confluence | Pages in the chosen spaces | `/rest/api/content/search` with CQL, Cloud API token or Data Center PAT | Document intelligence |
| SharePoint | Word, PDF, Excel, Markdown and text files in a library folder | Microsoft Graph, app registration with Sites.Selected or Sites.Read.All | Document intelligence |

**Live drift.** Once Azure and GitHub have both synced, resources are matched by name and every setting that differs
between the approved code and the deployed resource is listed on the Connections page.

**Demo mode.** Each connection can run in demo mode instead of live mode. Demo mode makes no network calls; a sync builds
the same kind of data from the sample estate and runs it through exactly the same steps, so the whole flow can be shown
without access to the real platforms.

**Credentials.** Secrets are stored in the local database on the server and are never returned by any endpoint. A secret
can also be entered as `env:VARIABLE_NAME`, so that it is read from the server environment and never stored. For
production, put secrets in a vault such as Azure Key Vault and use a managed identity where the platform supports it.
Saved connections survive "Start over"; the documents, imports and sync records an analysis read from them do not.

**API.** `GET /connections`, `GET|PUT|DELETE /connections/{id}`, `POST /connections/{id}/test`, `POST /connections/{id}/sync`. An analysis names the platforms to read in `POST /workspace/start` (`connections: ["servicenow", "jira", ...]`).

**Limits.** The live connectors are written to each platform's public API and are tested against recorded responses
(`backend/tests/test_connections.py`), not against real tenants. Expect to adjust field names on a first live run,
especially custom CMDB fields such as hosting. Syncs run on demand (no schedule yet) and read up to 5,000 records, 1,000
Jira issues, 40 infrastructure files and 20 documents per repository, 200 Confluence pages and 100 SharePoint files.
The server needs outbound HTTPS to each platform; it honours the standard `HTTPS_PROXY` settings.

## Design decisions

- **No pre-styled component library.** Radix primitives only, styled with Tailwind over a CSS-variable token layer.
  Dark is the default; the light theme is a full second palette rather than an inversion.
- **fg-3 contrast tweak.** In the dark theme the muted text token `--fg-3` is `123 133 153`, lifted slightly from the
  spec's `#667085` so small metadata text clears WCAG AA (about 5.2:1). Lighthouse accessibility is 94–96 on the
  pages checked.
- **Seed once, in memory.** `scripts/generate_seed.py` writes JSON with faker seed 42; the store builds a networkx
  MultiDiGraph at start-up. Uploaded documents and generated ADRs live in memory and reset on restart.
- **SPOFs** are articulation points, plus single-instance applications with no active-active deployment, plus
  assets with exact betweenness ≥ 0.08.
- **One shared design brief.** Target architecture and the Decision agent read the same requirements from a Zustand
  store, so a decision is always made on the requirements the options were generated for.
- **Code splitting.** Each module is its own route chunk. ECharts, Mermaid, React Flow and force-graph are loaded on
  demand. Initial JavaScript is about 190 kB gzipped.
- **`?noanim` QA hook.** Appending `?noanim` to any URL disables ECharts animation. Headless screenshot tools
  capture charts at frame zero otherwise, which looks like empty bars.
- **Copilot is one conversation.** The `/copilot` page and the ⌘J slide-over share a store, so a chat started in the
  drawer continues on the full page.

## Uploading your own files, and the sample files

Four places accept uploads. Each sends the file to `POST /api/v1/files/extract`, which returns plain text; that text then feeds the same engines as pasted input.

| Where | Accepts | What happens |
| --- | --- | --- |
| Documents > Upload documents | Word, PDF, Markdown, text, HTML (up to 10 files) | Entities and relations are extracted, conflicts and gaps are recomputed, coverage updates |
| Discovery > Import inventory | CSV, TSV, Excel | Reconciled against the estate (matches, fuzzy matches, drift in owner, criticality and hosting, unknown systems, systems missing from the export). Read-only: the estate is never changed |
| Standards > Check a design | Terraform, JSON, YAML, Markdown, Word, PDF | Checked against the policy catalogue; Terraform (`azurerm_*`) is parsed into components |
| Review agent > Review a design | Same as Standards | Reviewed as an ARB submission |

Limits: 8 MB per file; scanned (image-only) PDFs and encrypted PDFs are rejected with a clear message. Uploaded documents live in memory and disappear when the API restarts.

`sample-files/` holds realistic inputs built from the seeded Northwind estate (also served at `/samples/` for the one-click "Use this sample" buttons). `sample-files/README.txt` has the demo script.
Regenerate them with `cd backend && PYTHONPATH=. python3 -m scripts.build_samples`.

Suggested demo order: import the CMDB export (Discovery), upload the runbook PDF and the HLD (Documents, then open the Gaps and Conflicts tabs), check the Terraform before and after (Standards: 44 then 88), then review the notifications design (Review agent: no-go).

## Blueprint Intelligence Studio

`/studio` turns the blueprint catalogue into a workspace with eight steps: requirements, recommendation, customise, diagram, validation, gaps, export and governance. It extends what was already there: the 12 blueprint definitions, `standards.check_design`, `review.review`, the Terraform reader, the saved-items store and the ARB queue. It does not replace any of them.

**How the work is split.** Engines compute facts and the language model only writes prose about them (`services/ai.narrate`, the same provider abstraction as everything else; offline templates in `mock_ai/handlers.py`, Azure OpenAI when configured, which is checked to quote only numbers it was given).

1. **Requirements.** Free text, at least 20 characters. `mock_ai/rules/studio_requirements.py` extracts availability, RTO, RPO, latency, throughput, tier, exposure, data classification, residency and existing systems (matched by exact name against the estate). Each fact keeps the sentence it came from. A target the text does not state is shown as missing, never guessed.
2. **Recommendation.** Weighted keyword signals rank all 12 blueprints. The top one needs a score of at least 4 with a signal of weight 2 or more, otherwise the Studio says it needs more detail. Confidence is `0.2 + 0.5·min(1, top/12) + 0.3·margin`: a measure of keyword evidence, not a prediction. Alternatives say why they ranked lower and when to choose them. Overriding the recommendation needs a recorded reason.
3. **Customise.** Cloud, region, deployment, backend, LLM, data stores, messaging, IaC, tier, exposure, classification and 15 security and operational controls. A property exists in the design only if a choice, the blueprint's own label, an Azure platform default, a connection, or your edit set it; everything else is *not specified* and reported as such. Suggested NFR values from the tier are marked "suggested".
4. **Diagram.** The blueprint's Mermaid is parsed into a graph (`studio_catalog.parse_mermaid`) and built from your choices. Every edit (add, remove, rename, connect, move, set a property) is stored as an operation and replayed over the blueprint and choices, so changing the cloud later keeps your edits. Edits that no longer apply are listed as ignored.
5. **Validation.** The design is converted to the format `standards.check_design` and `review.review` already read, so the verdicts come from the existing engines. The Studio adds checks of its own (missing gateway, residency, linked-estate risk, lifecycle of chosen technology, NFR completeness) as separate gaps. Those gaps can only raise caution (a "go" becomes "conditional"); the review engine's formula is unchanged. A verdict cannot be "go" below 70% coverage. Non-Azure components and generic ones are listed as *not assessed*, not passed. Results are "as declared": nothing is verified against a deployed environment.
6. **Gaps.** Each gap has a severity, evidence (standard, component, finding), and where possible an automatic fix with alternatives. Accept applies the change to your choices or diagram and re-validates; Modify takes an alternative or a value; Accept risk needs a justification of at least 10 characters and the finding stays in the record.
7. **Export.** A Markdown target architecture document, SVG and Mermaid diagrams, and a starter ZIP (README, design config, NFR YAML, architecture JSON/SVG/Mermaid, OpenAPI 3.1, a service skeleton for the chosen backend, Dockerfile, and Terraform for Azure). **It is a starting point, not deployable infrastructure.** What was actually checked is listed with the ZIP: Python `ast`, YAML/JSON/XML parsing, OpenAPI structure and `$ref` resolution, Dockerfile non-root and HEALTHCHECK, and a Terraform round trip through the same HCL reader the standards use, compared with the design. `terraform init/validate/plan`, container builds, the service's own tests and any deployment are **not run**, and the ZIP says so. Bicep and non-Azure clouds get no infrastructure starter, with a note.
8. **Governance.** Submitting creates an entry in the existing review queue (`ARB-<year>-NNN`, stage "AI reviewed") that appears in `/reviews` and opens in the existing review page. Blocking checks: title and domain, requirements, no open critical gap. High gaps travel as conditions. A submitted design cannot be deleted; changing it and submitting again sends a new version to the same ARB id and keeps the earlier one.

Designs, versions, decisions and submissions are saved items (`studio_design`, `arb_submission`) in the same SQLite store as everything else.

**API** (all under `/api/v1/studio`): `GET /catalog`, `GET|POST /designs`, `GET|DELETE /designs/{n}`, `POST /designs/{n}/requirements`, `PUT /designs/{n}/blueprint`, `PATCH /designs/{n}`, `POST /designs/{n}/nfr/suggest`, `PUT /designs/{n}/ops`, `POST /designs/{n}/validate`, `POST /designs/{n}/decisions`, `POST /designs/{n}/versions`, `POST /designs/{n}/versions/{v}/restore`, `GET /designs/{n}/export/{document|document.md|starter.zip|diagram.svg|diagram.mmd}`, `POST /designs/{n}/submit`.

**Limits to know about.** Recommendation is keyword matching, not understanding. The standards library covers Azure resource types, so other clouds are mostly *not assessed*. Component properties are what the design declares. Generated code was never built or deployed. It has been run only on Linux with headless Chromium, not on Windows, and not with a screen reader (axe finds no serious violations on any step in either theme). The Azure OpenAI narration path has not been exercised live.

## Guided start

The app opens on **New analysis** (`/start`) and every other page stays empty until there is something to show. Four questions, then it runs:

1. **What are you looking for?** Pick one of five goals (understand the estate, get a design ready for review, check infrastructure code against standards, find risks and debt, plan modernisation), or describe it in your own words. Words are matched to a goal by keyword. The offline mock AI does not interpret free text any deeper than that.
2. **Supporting documents.** Drop or browse for designs, runbooks, HLDs, ADRs, Terraform or Bicep, and CMDB or inventory exports (up to 12 files), or use the Northwind sample files. Running with no files is allowed.
3. **Connect your tools (optional).** Tick the set-up platforms (ServiceNow, Jira, Azure, GitHub, Confluence, SharePoint) the run should read. A platform that is not set up can be connected in a side panel without leaving the page, and "Set up the rest as demo data" adds the others on sample data in one click. A run can start from tools alone, with no files.
4. **Business domain.** Choose one of the estate's domains or add a new one. A new domain has no estate behind it yet, so only your documents are filed under it, and the results say so.

The run (`POST /api/v1/workspace/start`, one background thread, progress saved after every step and polled by the page) chains the engines that already exist: read the chosen tools (each one the same way its Connections card does, so ServiceNow rows become an inventory import, Confluence, SharePoint and GitHub documents join Document intelligence, Azure and GitHub infrastructure code join the standards check, and Jira work is matched to applications), classify the files, add documents to Document intelligence, reconcile inventory exports, check designs and Terraform/Bicep against the standards, review them for readiness, then set the domain's slice of the estate (applications, findings) beside what was uploaded. It ends on a results page with a verdict, one panel per module and links into each. Pacing between steps follows the same `AI_LATENCY` setting as the rest of the mock AI.

- **Not ready vs Ready:** the verdict is the worst readiness review among the designs and infrastructure code you add. The Northwind sample pack deliberately contains breaches, so it reads *Not ready*. "Try a design that passes review" adds `agent-portal-sso-design.json` (domain Customer & Distribution), which reads *Ready*. A design needs its non-functional requirements filled in, no critical or high findings and a readiness of 80 or more to be Ready, so even the remediated Terraform and Bicep read *Conditional* (they carry no NFRs).
- **Download report** saves the results as a self-contained HTML page (prints cleanly to PDF) or as Markdown, built in the browser from the finished analysis.
- **Explore the Northwind demo** loads the full sample estate in one click, with no files needed.
- **A tool that cannot be read** is named in the "Reading connected tools" step and in the results, and the run goes on without it. The tools are read in full as configured (project keys, spaces, resource groups, folders); the business domain does not filter them yet, so narrow a connection in its own settings.
- **Start over** clears the analysis and removes the documents, imports, reviews and sync records it added. Saved connections stay.
- Only one analysis is active at a time. Each is stored as a saved item, so a list of past analyses is a small step later.
- The empty state is a gate in the shell: pages are not rewired, they simply do not render until the workspace is ready. The data endpoints themselves are unchanged.

## Graph tools

On `/graph` the toolbar above the canvas holds everything, and it all keeps working in full screen:

- **Find in view** jumps to a node already on the canvas (arrow keys and Enter work) and isolates its neighbourhood. Click the background to release it. The "Find and focus" panel on the left searches the whole estate instead and re-centres the graph on that asset.
- **Domains** and **Criticality** narrow the view. Owners, capabilities and cloud resources have neither, so they stay only while they still connect to something that does.
- **Relationships** keeps only the chosen kinds of link (calls, owns, stores data in, and so on, each with its count). Nodes left with no matching link drop out. Hovering any link shows a tooltip naming both ends and the relationship, and the relationship is written on the link itself while it is under the pointer, or on every link of the selected node once zoomed in.
- **Fold domains** collapses a business domain into one bubble (sized by how many nodes it holds, labelled with the count). Links inside the domain disappear and links to the outside are merged into one per neighbour, drawn thicker and tooltipped "calls ×12 · owns ×3". Fold from the menu, by clicking a domain name on the canvas (or `C` on a selected node), and open again by clicking the bubble. Find in view on a node inside a folded domain opens that domain first. With every layer on (635 nodes) the page offers a "Fold all domains" button.
- **Table view** (the Graph/Table switch) lists exactly the nodes the filters leave, sortable and filterable by name, in a virtualised table. Selecting a row lists its connections grouped by relationship, each of which can be followed; "Show in graph" jumps to the node. Export becomes a CSV in this view.
- **Keyboard and screen readers.** The canvas takes focus (Tab). Arrow keys move to the connected node in that direction, Home picks the first node, Enter opens details, `C` folds or opens the node's domain, `+`/`-` zoom, `0` fits the view and Escape clears the selection. Every move is announced through a polite live region (name, type, domain, number of connections), and the instructions are attached with `aria-describedby`. The table view covers everything the canvas shows without a mouse.
- **Views** saves layers, filters (including relationships), folded domains, colouring and focus under a name. Views are stored on the server (`GET/POST /api/v1/graph/views`, `DELETE /api/v1/graph/views/{id}`), so they survive a restart and are the same in every browser.
- **Export** writes a PNG of exactly what is on screen, with a title and legend, or an SVG of the whole graph that opens in Figma, Illustrator, Inkscape or PowerPoint.
- **Full screen** uses the browser's own full screen. In a browser that refuses it (some mobile browsers), the graph fills the window instead. In full screen a click shows a small details card with an "Open details" button.

## Testing and quality

- Backend: `cd backend && AI_LATENCY=0 python3 -m pytest` runs story-fact, API-contract, engine and upload tests.
- Frontend: `cd frontend && npm run test` (Vitest + Testing Library), `npm run lint` (zero warnings), `npm run typecheck`.
- **End to end:** `cd frontend && npx playwright install chromium` once, then `npm run e2e`. It builds the app, starts its own API (port 8100,
  throw-away database) and preview server (port 4273), and drives a real browser through:
  - the guided start: first-visit redirect, empty pages, the three questions, a full run with the sample files, new domains, start over and the demo shortcut, plus axe in both themes;
  - graph keyboard navigation and announcements, the table view (filters, CSV, connections), folding domains, the relationship filter and link tooltips;
  - graph interactions: find-in-view zoom, hovering without anything moving, clicking with a wobbly hand, dragging, filters, saved views, PNG and SVG
    export, and full screen;
  - uploads: runbook PDF, CMDB spreadsheet, design review, Bicep scoring, and the sample files served by the API;
  - the Blueprint Studio: requirements to a submitted review in a real browser (diagram edit, undo/redo, accepting a fix, the starter ZIP download, the link into the review page), axe on every step in both themes and a 390 px layout check;
  - accessibility with axe on six pages in **both themes**, including every graph toolbar menu open, the table view and the folded graph, plus checks that exports follow the theme.

  `E2E_PERF=1 npm run e2e -- e2e/perf` additionally measures the graph's frame rate with all 635 nodes, expanded and folded, and prints a table.
  On the development machine (headless Chromium, software rendering) the expanded graph held about 58 fps with a median draw cost of 3.4 ms
  (p95 11.7 ms), and the folded one about 59 fps at 0.7 ms (p95 4.1 ms). A real laptop with a GPU should do at least as well; a weak one may need the folding.

  Specs start from a known workspace (`resetServerState` loads the demo, or empties it for the first-visit tests).

  `npm run e2e:ui` opens Playwright's interactive runner. Set `PW_CHROMIUM_PATH` to use an existing Chrome instead of downloading one, and `E2E_REUSE=1`
  to reuse servers already running on those ports. It never touches the development API or its data.
- CI: `.github/workflows/ci.yml` runs all of the above on every push and pull request. Failed e2e runs upload the traces and screenshots.
- Lighthouse (production build, `vite preview`, desktop preset): accessibility 100 and best practices 100 on the overview, graph, standards,
  discovery, documents and review pages; performance 91–100. The mobile preset is noisier because the graph is canvas-heavy.

## Layout

```
backend/app/api/v1/routers/   HTTP surface (core, knowledge, design, delivery, files)
backend/app/mock_ai/          provider, narration, handlers, copilot, graph, rules, scoring, generators
backend/app/data/seed/        seeded JSON (regenerate with `make seed`)
backend/tests/                story facts, API, engines, uploads
backend/scripts/              build_samples.py (generates sample-files/)
sample-files/                 demo inputs: CMDB export, HLD, runbook, ADR, Terraform, design
frontend/src/features/        one folder per module
frontend/src/components/      ui (design system), viz (charts and graphs), ai (summary and thinking)
frontend/src/store/           ui, copilot, design
```
