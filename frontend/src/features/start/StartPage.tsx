import { useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Check, CircleDashed, Cloud, Database, Download, FileText, GitBranch, ListTodo, Loader2, Minus, PackagePlus, Plug, RotateCcw, Rocket, X } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, extractFile } from '@/api/client';
import { useGet } from '@/api/hooks';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { FileDrop, type DroppedFile } from '@/components/ui/FileDrop';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Inputs';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { Panel, Skeleton } from '@/components/ui/Panel';
import { cn } from '@/lib/cn';
import { download } from '@/lib/format';
import { reportFileName, reportHtml, reportMarkdown } from './report';
import { useUI } from '@/store/ui';
import { useConnectionActions, useConnections, type Connection } from '@/features/connections/api';
import { ConnectionDrawer } from '@/features/connections/ConnectionDrawer';
import { useWorkspace, useWorkspaceActions, WORKSPACE_KEY, type WResult, type Workspace, type WorkspaceOptions, type WStep } from './useWorkspace';

const NEW_DOMAIN = '__new__';
/** The sample files that make a complete run: an inventory export, code, a design, a runbook, an HLD and an ADR. */
const SAMPLE_PACK = ['sample-cmdb-export-2026-11.csv', 'claims-copilot-main.tf', 'claims-notifications-design.md', 'Claims-Intake-Modernization-HLD-v1.2.docx', 'Policy-Admin-Operations-Runbook.pdf', 'ADR-0052-Event-Driven-Claims-Notifications.md'];

/** A design that passes review, to show the "Ready" outcome (it belongs to the Customer & Distribution domain). */
const READY_SAMPLE = 'agent-portal-sso-design.json';

interface Added { name: string; text: string; size: number }

const verdictTone = { go: 'healthy', conditional: 'medium', no_go: 'critical' } as const;
const verdictText = { go: 'Ready', conditional: 'Conditional', no_go: 'Not ready' } as const;

export default function StartPage() {
  const ws = useWorkspace();
  const [composing, setComposing] = useState(false);
  const w = ws.data;
  if (!w) return <Page><PageHeader title="New analysis" description="Say what you are looking for, add what you have, and see the whole flow run." /><Skeleton className="h-72 w-full" /></Page>;
  if (w.status === 'running' || (w.status === 'failed' && !composing)) return <RunView w={w} onAgain={() => setComposing(true)} />;
  if (w.status === 'ready' && !composing) return <ReadyView w={w} onNew={() => setComposing(true)} />;
  return <Wizard onStarted={() => setComposing(false)} />;
}

/* ----------------------------------------------------------------- the three questions */
function Wizard({ onStarted }: { onStarted: () => void }) {
  const qc = useQueryClient();
  const toast = useUI((s) => s.toast);
  const navigate = useNavigate();
  const actions = useWorkspaceActions();
  const opts = useGet<WorkspaceOptions>('/workspace/options', undefined, { staleTime: 60_000 });
  const available = useGet<{ items: { name: string }[] }>('/files/samples', undefined, { staleTime: 60_000 });
  const [intent, setIntent] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [files, setFiles] = useState<Added[]>([]);
  const [domain, setDomain] = useState('');
  const [newDomain, setNewDomain] = useState('');
  const [sources, setSources] = useState<string[]>([]);
  const [busy, setBusy] = useState<'start' | 'samples' | 'demo' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const radio = useId();
  const max = opts.data?.max_files ?? 12;
  const domainName = domain === NEW_DOMAIN ? newDomain.trim() : domain;
  const haveSamples = SAMPLE_PACK.filter((n) => available.data?.items.some((i) => i.name === n));
  const haveReady = !!available.data?.items.some((i) => i.name === READY_SAMPLE);

  const add = (list: Added[]) => setFiles((cur) => {
    const next = [...cur];
    for (const f of list) if (!next.some((x) => x.name === f.name)) next.push(f);
    if (next.length > max) { setError(`Add at most ${max} files at a time`); return next.slice(0, max); }
    setError(null);
    return next;
  });
  const onFiles = (dropped: DroppedFile[]) => add(dropped.map((d) => ({ name: d.file.name, text: d.extracted.text, size: d.file.size })));
  const addSamples = async (names: string[], setup: { intent: string; domain: string }) => {
    setBusy('samples'); setError(null);
    try {
      const out: Added[] = [];
      for (const name of names) {
        const res = await fetch(`/api/v1/files/samples/${encodeURIComponent(name)}`);
        if (!res.ok) throw new Error(`Sample ${name} is not available`);
        const file = new File([await res.blob()], name);
        out.push({ name, text: (await extractFile(file)).text, size: file.size });
      }
      add(out);
      if (!domain) setDomain(setup.domain);
      if (!intent && !text) setIntent(setup.intent);
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const ready = domainName.length >= 2 && (intent !== null || text.trim().length > 0);
  const start = async () => {
    setBusy('start'); setError(null);
    try {
      const w = await api<Workspace>('/workspace/start', { method: 'POST', body: { intent_id: intent, intent_text: text, domain: domainName, files: files.map((f) => ({ filename: f.name, text: f.text })), connections: sources } });
      qc.setQueryData(WORKSPACE_KEY, w);
      onStarted();
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const demo = async () => {
    setBusy('demo');
    try { await actions.loadDemo(); toast({ title: 'Baseline estate loaded' }); navigate('/'); } catch (e) { setError((e as Error).message); setBusy(null); }
  };
  // the question that still needs an answer, so the disabled button explains itself
  const missing = intent === null && !text.trim() ? 'Say what you are looking for' : !domainName ? 'Choose a business domain' : domainName.length < 2 ? 'Give the domain a name' : null;

  return (
    <Page>
      <PageHeader
        title="New analysis"
        description="Tell ArchIQ what you are looking for, add whatever supporting documents you have, connect the tools that hold your data, and pick the business domain. It then runs the whole flow, from reading your sources to a readiness verdict, and fills in the rest of the app."
        actions={<Button variant="outline" size="sm" disabled={busy !== null} onClick={() => void demo()} leading={busy === 'demo' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : undefined}>Load baseline estate instead</Button>}
      />
      <div className="mx-auto grid max-w-3xl gap-4">
        <Panel title={<Heading n={1}>What are you looking for?</Heading>} description="Pick the closest match, or describe it in your own words.">
          <div role="radiogroup" aria-label="What you are looking for" className="grid gap-2 sm:grid-cols-2">
            {(opts.data?.intents ?? []).map((i) => (
              <label key={i.id} className={cn('relative flex cursor-pointer flex-col gap-0.5 rounded-lg border border-line bg-bg p-3 transition-colors hover:border-fg-3/50 has-[:checked]:border-accent has-[:checked]:bg-accent/5 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/50')}>
                <input type="radio" name={radio} value={i.id} checked={intent === i.id} onChange={() => setIntent(i.id)} className="sr-only" />
                <span className="text-sm font-medium text-fg">{i.label}</span>
                <span className="text-xs text-fg-3">{i.hint}</span>
                {intent === i.id && <Check className="absolute right-2.5 top-2.5 h-4 w-4 text-accent" aria-hidden />}
              </label>
            ))}
            {opts.isLoading && Array.from({ length: 4 }).map((_, k) => <Skeleton key={k} className="h-[58px]" />)}
          </div>
          <Field label="In your own words (optional)" className="mt-3">
            <TextArea rows={2} maxLength={500} value={text} onChange={(e) => setText(e.target.value)} placeholder="For example: we are moving claims intake to events and need the design ready for architecture review" />
          </Field>
        </Panel>

        <Panel title={<Heading n={2}>Add your supporting documents</Heading>} description="Designs, runbooks, HLDs, ADRs, Terraform or Bicep, and CMDB or inventory exports. Nothing leaves this machine. You can run without any."
          actions={(haveSamples.length > 0 || haveReady) ? (
            <div className="flex flex-wrap justify-end gap-2">
              {haveSamples.length > 0 && <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void addSamples(haveSamples, { intent: 'understand', domain: 'Claims' })} leading={busy === 'samples' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <PackagePlus className="h-3.5 w-3.5" aria-hidden />}>Load reference files</Button>}
              {haveReady && <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void addSamples([READY_SAMPLE], { intent: 'review', domain: 'Customer & Distribution' })} leading={<PackagePlus className="h-3.5 w-3.5" aria-hidden />}>Try a design that passes review</Button>}
            </div>) : undefined}>
          <FileDrop multiple onFiles={onFiles} label="Drop files here or browse" />
          {files.length > 0 && (
            <ul aria-label="Files to analyse" className="mt-3 divide-y divide-line-subtle rounded-lg border border-line">
              {files.map((f) => (
                <li key={f.name} className="flex items-center gap-2.5 px-3 py-1.5 text-sm">
                  <FileText className="h-4 w-4 shrink-0 text-fg-3" aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  <span className="num text-xs text-fg-3">{(f.size / 1024).toFixed(f.size < 10240 ? 1 : 0)} KB</span>
                  <button type="button" aria-label={`Remove ${f.name}`} onClick={() => setFiles((c) => c.filter((x) => x.name !== f.name))} className="rounded p-1 text-fg-3 hover:bg-raised hover:text-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"><X className="h-3.5 w-3.5" aria-hidden /></button>
                </li>))}
            </ul>)}
        </Panel>

        <Panel title={<Heading n={3}>Connect your tools</Heading>} description="Optional. Tick the platforms ArchIQ should read as part of this analysis. It only reads; nothing in your tools is changed.">
          <ToolPicker selected={sources} onChange={setSources} />
        </Panel>

        <Panel title={<Heading n={4}>Which business domain?</Heading>} description="Everything is filed under it and the estate is read through it. Choose one that exists, or add your own.">
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Business domain">
              <Select className="min-w-[240px]" label="Business domain" placeholder="Choose a domain" value={domain} onValueChange={setDomain}
                options={[...(opts.data?.domains ?? []).map((d) => ({ value: d.name, label: `${d.name} · ${d.assets} applications` })), { value: NEW_DOMAIN, label: 'Add a new domain…' }]} />
            </Field>
            {domain === NEW_DOMAIN && (
              <Field label="New domain name" hint="Nothing in the estate is tagged to it yet, so only your documents will be filed under it.">
                <TextInput autoFocus maxLength={80} value={newDomain} onChange={(e) => setNewDomain(e.target.value)} placeholder="For example: Treasury" className="w-64" />
              </Field>)}
          </div>
        </Panel>

        {error && <p role="alert" className="text-sm text-critical">{error}</p>}
        <div className="flex flex-wrap items-center gap-3">
          <Button size="lg" disabled={!ready || busy !== null} onClick={() => void start()} leading={busy === 'start' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Rocket className="h-4 w-4" aria-hidden />}>Start the analysis</Button>
          <span className="text-xs text-fg-3">{missing ?? [files.length ? `${files.length} file${files.length === 1 ? '' : 's'}` : 'No files', sources.length ? `${sources.length} tool${sources.length === 1 ? '' : 's'}` : null, domainName].filter(Boolean).join(' · ')}</span>
        </div>
      </div>
    </Page>
  );
}

/* ----------------------------------------------------------------- connected tools */
const TOOL_ICON = { cmdb: Database, work: ListTodo, cloud: Cloud, code: GitBranch, docs: FileText } as const;

/** The platforms ArchIQ can read. A set-up platform can be ticked; one that is not yet set up can be connected here, without leaving the page. */
function ToolPicker({ selected, onChange }: { selected: string[]; onChange: (ids: string[]) => void }) {
  const { data, isLoading, isError } = useConnections();
  const { save } = useConnectionActions();
  const toast = useUI((s) => s.toast);
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const items: Connection[] = data?.items ?? [];
  const ready = items.filter((c) => c.configured);
  const toggle = (id: string, on: boolean) => onChange(on ? [...selected.filter((x) => x !== id), id] : selected.filter((x) => x !== id));
  // a platform that was removed elsewhere can no longer be read, so it drops out of the selection
  useEffect(() => {
    if (data && selected.some((id) => !data.items.find((c) => c.id === id)?.configured)) onChange(selected.filter((id) => data.items.find((c) => c.id === id)?.configured));
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps
  const addAllAsDemo = async () => {
    setAdding(true);
    try {
      const ids: string[] = [];
      for (const c of items) {
        if (!c.configured) await save(c.id, { mode: 'demo', config: {}, secrets: {} });
        ids.push(c.id);
      }
      onChange(ids);
      toast({ title: 'The remaining tools are set to Not live', description: 'They use the local estate snapshot, so no credentials are needed.' });
    } catch (e) { toast({ title: 'Could not add the tools', description: (e as Error).message, tone: 'error' }); } finally { setAdding(false); }
  };
  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (isError) return <p className="text-sm text-fg-3">The list of tools could not be loaded. You can still run the analysis with files only.</p>;
  return (
    <div>
      <ul aria-label="Tools to read" className="divide-y divide-line-subtle rounded-lg border border-line">
        {items.map((c) => {
          const Icon = TOOL_ICON[c.category];
          const on = selected.includes(c.id);
          return (
            <li key={c.id} className="flex items-center gap-3 px-3 py-2">
              <Icon className="h-4 w-4 shrink-0 text-fg-3" aria-hidden />
              <div className="min-w-0 flex-1">
                {c.configured ? (
                  <label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-fg">
                    <input type="checkbox" checked={on} onChange={(e) => toggle(c.id, e.target.checked)} className="h-4 w-4 accent-[var(--accent)]" />
                    {c.name}
                  </label>
                ) : <p className="text-sm font-medium text-fg">{c.name}</p>}
                <p className="mt-0.5 truncate text-xs text-fg-3" title={c.description}>{c.description}</p>
              </div>
              {c.configured && <Badge tone={c.mode === 'demo' ? 'accent' : 'healthy'} dot>{c.mode === 'demo' ? 'Not live' : 'Live'}</Badge>}
              <Button size="sm" variant={c.configured ? 'ghost' : 'secondary'} leading={<Plug className="h-3.5 w-3.5" aria-hidden />} onClick={() => setOpen(c.id)} aria-label={`${c.configured ? 'Settings for' : 'Connect'} ${c.name}`}>{c.configured ? 'Settings' : 'Connect'}</Button>
            </li>
          );
        })}
      </ul>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        {items.some((c) => !c.configured) && <Button size="sm" variant="outline" disabled={adding} onClick={() => void addAllAsDemo()} leading={adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <PackagePlus className="h-3.5 w-3.5" aria-hidden />}>Set remaining tools to Not live</Button>}
        <span className="text-xs text-fg-3">{selected.length ? `${selected.length} of ${ready.length} set-up tool${ready.length === 1 ? '' : 's'} will be read` : ready.length ? 'None ticked: the analysis will use your files only.' : 'Nothing is connected yet. You can also run with files only.'}</span>
        <Link to="/connections" className="ml-auto text-xs text-accent hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Manage connections</Link>
      </div>
      <ConnectionDrawer id={open} onClose={() => setOpen(null)} onSaved={(id) => toggle(id, true)} />
    </div>
  );
}

function Heading({ n, children }: { n: number; children: string }) {
  return <span className="flex items-center gap-2"><span aria-hidden className="flex h-5 w-5 items-center justify-center rounded-full bg-accent/15 font-mono text-[11px] text-accent">{n}</span>{children}</span>;
}

/* ----------------------------------------------------------------- running */
function StepIcon({ s }: { s: WStep['status'] }) {
  if (s === 'running') return <Loader2 className="h-4 w-4 animate-spin text-accent" aria-hidden />;
  if (s === 'done') return <Check className="h-4 w-4 text-healthy" aria-hidden />;
  if (s === 'skipped') return <Minus className="h-4 w-4 text-fg-3" aria-hidden />;
  if (s === 'failed') return <X className="h-4 w-4 text-critical" aria-hidden />;
  return <CircleDashed className="h-4 w-4 text-fg-3" aria-hidden />;
}
const stepWord: Record<WStep['status'], string> = { pending: 'waiting', running: 'in progress', done: 'done', skipped: 'skipped', failed: 'failed' };

function Steps({ steps }: { steps: WStep[] }) {
  return (
    <ol aria-label="Analysis steps" className="divide-y divide-line-subtle">
      {steps.map((s) => (
        <li key={s.id} className="flex items-start gap-3 px-4 py-2.5" data-status={s.status}>
          <span className="mt-0.5"><StepIcon s={s.status} /></span>
          <div className="min-w-0 flex-1">
            <p className={cn('text-sm', s.status === 'pending' ? 'text-fg-3' : 'text-fg')}>{s.label}<span className="sr-only"> — {stepWord[s.status]}</span></p>
            {s.detail && <p className="mt-0.5 text-xs text-fg-3">{s.detail}</p>}
          </div>
          {s.link && s.status === 'done' && <Link to={s.link} className="shrink-0 text-xs text-accent hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Open</Link>}
        </li>))}
    </ol>
  );
}

function RunView({ w, onAgain }: { w: Workspace; onAgain: () => void }) {
  const actions = useWorkspaceActions();
  const failed = w.status === 'failed';
  return (
    <Page>
      <PageHeader title={failed ? 'The analysis did not finish' : 'Running your analysis'} description={`${w.intent?.label ?? 'Analysis'} · ${w.domain?.name ?? ''} · ${w.documents.length} file${w.documents.length === 1 ? '' : 's'}${w.sources?.length ? ` · ${w.sources.length} tool${w.sources.length === 1 ? '' : 's'}` : ''}`} />
      <div className="mx-auto max-w-3xl">
        <Panel flush title="Progress" bodyClassName="p-0">
          <div role="status" aria-live="polite" className="sr-only">{failed ? 'The analysis failed' : `${w.steps.filter((s) => s.status === 'done' || s.status === 'skipped').length} of ${w.steps.length} steps finished`}</div>
          <Steps steps={w.steps} />
        </Panel>
        {failed && (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <p role="alert" className="text-sm text-critical">{w.error}</p>
            <Button variant="outline" onClick={() => void actions.reset().then(onAgain)}>Start again</Button>
          </div>)}
      </div>
    </Page>
  );
}

/* ----------------------------------------------------------------- results */
function ReadyView({ w, onNew }: { w: Workspace; onNew: () => void }) {
  const actions = useWorkspaceActions();
  const qc = useQueryClient();
  const ranRefresh = useRef(false);
  // the data pages cached "nothing here" while the run was under way
  useEffect(() => { if (!ranRefresh.current) { ranRefresh.current = true; void qc.invalidateQueries(); } }, [qc]);
  const newAnalysis = async () => { await actions.reset(); onNew(); };
  if (w.mode === 'demo' || !w.result) {
    return (
      <Page>
        <PageHeader title="Baseline estate is loaded" description="Every page is showing the baseline architecture estate. Start a new analysis to run against your own documents and domain." />
        <div className="flex flex-wrap gap-2">
          <Link to="/" className="inline-flex h-8 items-center gap-1.5 rounded-md accent-bg px-3 text-sm font-medium text-accent-fg hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">Open the overview <ArrowRight className="h-3.5 w-3.5" aria-hidden /></Link>
          <Button variant="outline" onClick={() => void newAnalysis()} leading={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}>Start a new analysis</Button>
        </div>
      </Page>
    );
  }
  const r: WResult = w.result;
  return (
    <Page>
      <PageHeader title="Your analysis is ready" description={`${w.intent?.label ?? ''} · ${w.domain?.name ?? ''} · ${w.documents.length} file${w.documents.length === 1 ? '' : 's'}`}
        actions={<><Button variant="outline" onClick={() => download(reportFileName(w, 'html'), reportHtml(w), 'text/html;charset=utf-8')} leading={<Download className="h-3.5 w-3.5" aria-hidden />}>Download report</Button><Button variant="outline" onClick={() => download(reportFileName(w, 'md'), reportMarkdown(w), 'text/markdown;charset=utf-8')} leading={<Download className="h-3.5 w-3.5" aria-hidden />}>Markdown</Button><Button variant="outline" onClick={() => void newAnalysis()} leading={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}>Start over</Button><Link to={r.primary.to} className="inline-flex h-8 items-center gap-1.5 rounded-md accent-bg px-3 text-sm font-medium text-accent-fg hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">{r.primary.label} <ArrowRight className="h-3.5 w-3.5" aria-hidden /></Link></>} />
      <div className="grid gap-4">
        <Panel>
          <div className="flex flex-wrap items-center gap-3">
            {r.verdict && <Badge tone={verdictTone[r.verdict]} dot>{verdictText[r.verdict]}</Badge>}
            <p className="min-w-0 flex-1 text-sm text-fg" data-testid="result-headline">{r.headline}</p>
          </div>
          {r.notes.map((n) => <p key={n} className="mt-2 text-xs text-fg-3">{n}</p>)}
        </Panel>
        <Panel flush title="What happened" bodyClassName="p-0"><Steps steps={w.steps} /></Panel>
        <div className="grid gap-4 md:grid-cols-2">
          {r.sections.map((s) => (
            <Panel key={s.id} title={s.title} data-testid={`result-${s.id}`} actions={<Link to={s.to} className="text-xs text-accent hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Open<span className="sr-only"> {s.title}</span></Link>}>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                {s.metrics.map((m) => (<div key={m.label}><dt className="text-[11px] text-fg-3">{m.label}</dt><dd className="num text-lg font-semibold text-fg">{m.value}</dd></div>))}
              </dl>
              {s.bullets.length > 0 && <ul className="mt-3 space-y-1 border-t border-line-subtle pt-3 text-xs text-fg-2">{s.bullets.map((b) => <li key={b} className="truncate" title={b}>{b}</li>)}</ul>}
            </Panel>))}
        </div>
      </div>
    </Page>
  );
}
