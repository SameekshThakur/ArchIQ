import { ArrowRight, CheckCircle2, ListChecks, ShieldAlert, ShieldCheck } from 'lucide-react';
import { useMemo, useState } from 'react';
import { AISummary } from '@/components/ai/AIPanel';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Field, Select, SegmentedControl, TextArea, TextInput } from '@/components/ui/Inputs';
import { EmptyState, Panel, ProgressBar, ScoreRing } from '@/components/ui/Panel';
import { EvidenceChip } from '@/components/ui/Timeline';
import { cn } from '@/lib/cn';
import { fmtDate, titleCase } from '@/lib/format';
import { ErrorNote, VERDICT, type StepProps } from './shared';
import type { Fix, Gap } from './types';

const SEV = ['critical', 'high', 'medium', 'low'] as const;
const STD_TONE = { pass: 'healthy', warn: 'medium', fail: 'critical' } as const;

export function ValidationStep({ design, catalog, actions, go }: StepProps) {
  const nfrLabel = (k: string) => catalog.nfr_fields.find((f) => f.key === k)?.label ?? titleCase(k);
  const v = design.validation;
  const [only, setOnly] = useState<'issues' | 'all'>('issues');
  if (!v) return <EmptyState icon={<ShieldCheck className="h-4 w-4" aria-hidden />} title="Nothing to validate yet" description="Choose a blueprint first." />;
  const verdict = VERDICT[v.verdict];
  const rec = design.recorded_validation;
  const stale = !rec || rec.readiness !== v.readiness || rec.verdict !== v.verdict;
  const results = v.standards.results.filter((r) => only === 'all' || r.status !== 'pass');
  const openTotal = SEV.reduce((a, s) => a + (v.open_counts[s] ?? 0), 0);
  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-center gap-6">
          <ScoreRing score={v.readiness} size={112} label="readiness" />
          <div className="min-w-[240px] flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2"><Badge tone={verdict.tone}>{verdict.label}</Badge><Badge tone="neutral">{v.coverage.percent}% of components assessed</Badge>{v.verdict !== v.engine_verdict && <Badge tone="medium">Studio gaps raised caution</Badge>}</div>
            <p className="text-sm text-fg-2">{v.basis}</p>
            <ul className="flex flex-wrap gap-3 text-xs" aria-label="Open gaps by severity">{SEV.map((s) => <li key={s} className="flex items-center gap-1.5"><Badge tone={s}>{s}</Badge><span className="num font-mono text-fg">{v.open_counts[s] ?? 0}</span></li>)}</ul>
          </div>
          <div className="flex flex-col items-start gap-2">
            <Button variant="primary" loading={actions.busy} leading={<ShieldCheck className="h-4 w-4" aria-hidden />} onClick={() => void actions.validate()}>{rec ? 'Record validation again' : 'Record this validation'}</Button>
            <p className="max-w-[220px] text-xs text-fg-3">{rec ? `Recorded ${fmtDate(rec.at)}: ${rec.readiness}/100.${stale ? ' The design has changed since.' : ''}` : 'The figures update live. Recording stores this result with the design and writes the summary.'}</p>
          </div>
        </div>
        {v.conditions.length > 0 && (
          <div className="mt-4 border-t border-line-subtle pt-3"><p className="micro mb-1.5">Conditions</p><ul className="list-disc space-y-1 pl-4 text-sm text-fg-2">{v.conditions.map((c) => <li key={c}>{c}</li>)}</ul></div>
        )}
        <p className="mt-3 text-xs text-fg-3">Validated as declared. Nothing here has been checked against a deployed environment. Scores come from the standards, NFR and review rules, not from the language model.</p>
      </Panel>
      {actions.error && <ErrorNote>{actions.error}</ErrorNote>}
      {design.narration && <AISummary ai={design.narration} title="Validation summary" />}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Standards" description={`${v.standards.passed} passed, ${v.standards.warned} warnings, ${v.standards.failed} failed. Score ${v.standards.score}.`}
          actions={<SegmentedControl size="sm" label="Show" value={only} onChange={setOnly} options={[{ value: 'issues', label: 'Issues' }, { value: 'all', label: 'All' }]} />}>
          {results.length === 0 ? <p className="text-sm text-fg-3">No standard failed or warned for the components that could be assessed ({v.coverage.percent}% of them). Components outside the standards library are listed under “Not assessed”; they have not been passed.</p> : (
            <ul className="divide-y divide-line-subtle">{results.map((r) => (
              <li key={r.standard_id} className="py-2.5 first:pt-0 last:pb-0"><div className="flex items-center gap-2"><Badge tone={STD_TONE[r.status]}>{r.status}</Badge><span className="font-mono text-[11px] text-fg-3">{r.standard_id}</span><span className="truncate text-sm text-fg">{r.title}</span></div>
                <p className="mt-1 text-xs text-fg-2">{r.rationale}</p>{r.status !== 'pass' && <p className="mt-0.5 text-xs text-fg-3">{r.remediation}</p>}</li>
            ))}</ul>
          )}
        </Panel>
        <div className="space-y-4">
          <Panel title="Non-functional targets" description={`${v.nfr_coverage.present.length} of 6 stated`}>
            <ProgressBar value={v.nfr_coverage.percent} tone={v.nfr_coverage.missing.length ? 'medium' : 'healthy'} label="NFR coverage" />
            <ul className="mt-3 grid grid-cols-2 gap-1.5 text-xs">{[...v.nfr_coverage.present, ...v.nfr_coverage.missing].map((k) => {
              const have = v.nfr_coverage.present.includes(k);
              return <li key={k} className="flex items-center gap-1.5">{have ? <CheckCircle2 className="h-3.5 w-3.5 text-healthy" aria-label="stated" /> : <ShieldAlert className="h-3.5 w-3.5 text-medium" aria-label="missing" />}<span className={have ? 'text-fg-2' : 'text-fg'}>{nfrLabel(k)}{have ? `: ${Array.isArray(v.nfr_coverage.values[k]) ? (v.nfr_coverage.values[k] as string[]).join(', ') : String(v.nfr_coverage.values[k])}` : ' (missing)'}</span></li>;
            })}</ul>
          </Panel>
          <Panel title="Checks that ran" description="Each is run by an existing engine against the design as declared.">
            <ul className="space-y-2 text-xs">{v.checks_run.map((c) => <li key={c.id}><span className="text-fg">{c.label}</span> <Badge mono>{c.engine}</Badge><br /><span className="text-fg-3">{c.detail}</span></li>)}</ul>
          </Panel>
          {v.patterns.length > 0 && <Panel title="Pattern alignment"><ul className="space-y-1 text-xs">{v.patterns.map((p) => <li key={p.pattern} className="flex items-center gap-2"><Badge tone={p.aligned ? 'healthy' : 'medium'}>{p.aligned ? 'aligned' : 'diverges'}</Badge><span className="text-fg-2">{p.pattern}</span></li>)}</ul></Panel>}
        </div>
      </div>

      {(v.coverage.not_assessed.length > 0 || v.estate_risks.length > 0 || v.notices.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          {v.coverage.not_assessed.length > 0 && <Panel title="Not assessed" description="These components have no standard that applies. They are listed, not passed."><ul className="space-y-1.5 text-xs">{v.coverage.not_assessed.map((n) => <li key={n.id}><span className="text-fg">{n.name}</span> <span className="text-fg-3">— {n.reason}</span></li>)}</ul></Panel>}
          {v.estate_risks.length > 0 && <Panel title="Risks in linked applications"><ul className="space-y-1.5 text-xs">{v.estate_risks.map((r) => <li key={r.finding_id} className="flex gap-1.5"><Badge tone={r.severity as 'high'}>{r.severity}</Badge><span className="text-fg-2">{r.title}</span></li>)}</ul></Panel>}
          {v.notices.length > 0 && <Panel title="Notices"><ul className="list-disc space-y-1 pl-4 text-xs text-fg-2">{v.notices.map((n) => <li key={n.id}>{n.text}</li>)}</ul></Panel>}
        </div>
      )}
      <div className="flex justify-end"><Button variant="primary" trailing={<ArrowRight className="h-4 w-4" aria-hidden />} onClick={() => go('gaps')}>{openTotal ? `Review ${openTotal} gap${openTotal === 1 ? '' : 's'}` : 'Continue to export'}</Button></div>
    </div>
  );
}

/* ---------------------------------------------------------------- gaps */
function FixInput({ fix, value, onChange }: { fix: Fix; value: string; onChange: (v: string) => void }) {
  const inp = fix.input!;
  if (inp.kind === 'choice') return <Select label={inp.label} className="w-56" placeholder={inp.label} value={value} onValueChange={onChange} options={(inp.options ?? []).map((o) => ({ value: o, label: o }))} />;
  return <TextInput aria-label={inp.label} className="w-56" type={inp.kind === 'number' ? 'number' : 'text'} min={inp.min} max={inp.max} placeholder={inp.label} value={value} onChange={(e) => onChange(e.target.value)} />;
}

function GapCard({ gap, busy, onDecide, onGoTo }: { gap: Gap; busy: boolean; onDecide: (a: 'accept' | 'modify' | 'risk_accept' | 'reopen', x?: { value?: unknown; note?: string; alternative?: number }) => Promise<unknown>; onGoTo: (id: string) => void }) {
  const [mode, setMode] = useState<null | 'modify' | 'risk'>(null);
  const [value, setValue] = useState('');
  const [note, setNote] = useState('');
  const fix = gap.fix;
  const needsInput = !!fix?.input;
  const val = fix?.input?.kind === 'number' ? (value === '' ? '' : Number(value)) : value;
  const decided = gap.state !== 'open';
  return (
    <li className={cn('rounded-lg border bg-surface p-4', gap.severity === 'critical' ? 'border-critical/40' : 'border-line', decided && 'opacity-90')} data-testid={`gap-${gap.id}`}>
      <div className="flex flex-wrap items-center gap-2"><Badge tone={gap.severity}>{gap.severity}</Badge><Badge mono>{gap.category}</Badge>{decided && <Badge tone="accent">{gap.state.replace('_', ' ')}</Badge>}<h3 className="min-w-0 flex-1 text-sm font-semibold text-fg">{gap.title}</h3></div>
      <p className="mt-2 text-sm text-fg-2">{gap.detail}</p>
      {gap.evidence.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Evidence">{gap.evidence.map((e) => <EvidenceChip key={e.kind + e.id} kind={e.kind} label={e.label || e.id} />)}</div>}
      {gap.component_names.length > 0 && <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3">Affects: {gap.components.map((id, i) => <button key={id} type="button" className="rounded text-accent underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent" onClick={() => onGoTo(id)}>{gap.component_names[i] ?? id}</button>)}</p>}
      <p className="mt-2 text-sm text-fg"><span className="micro mr-1.5">Recommended</span>{gap.recommendation}</p>
      {decided && gap.decision && <p className="mt-2 rounded bg-raised/60 px-2.5 py-1.5 text-xs text-fg-2">{gap.state === 'risk_accepted' ? `Risk accepted: “${gap.decision.note}”. It stays in the findings and is sent to the board.` : gap.decision.fix_label}</p>}

      {!decided && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {fix && !needsInput && !fix.alternatives?.length && <Button size="sm" variant="primary" loading={busy} onClick={() => void onDecide('accept')}>Accept: {fix.label}</Button>}
            {fix && (needsInput || !!fix.alternatives?.length) && <Button size="sm" variant={mode === 'modify' ? 'secondary' : 'primary'} aria-expanded={mode === 'modify'} onClick={() => setMode(mode === 'modify' ? null : 'modify')}>{needsInput ? 'Provide a value' : 'Choose how to fix'}</Button>}
            {fix && !needsInput && !!fix.alternatives?.length && <Button size="sm" variant="outline" loading={busy} onClick={() => void onDecide('accept')}>Accept: {fix.label}</Button>}
            {!fix && <span className="text-xs text-fg-3">No automatic fix. Edit the diagram or the choices, or accept the risk.</span>}
            <Button size="sm" variant="ghost" aria-expanded={mode === 'risk'} onClick={() => setMode(mode === 'risk' ? null : 'risk')}>Accept the risk</Button>
          </div>
          {mode === 'modify' && fix && (
            <div className="space-y-2 rounded border border-line bg-raised/40 p-3">
              {needsInput && (
                <div className="flex flex-wrap items-end gap-2"><Field label={fix.input!.label}><FixInput fix={fix} value={value} onChange={setValue} /></Field>
                  <Button size="sm" variant="primary" loading={busy} disabled={value === ''} onClick={() => void onDecide('modify', { value: val })}>Apply</Button></div>
              )}
              {!!fix.alternatives?.length && (
                <div><p className="micro mb-1.5">Other ways to fix it</p><ul className="space-y-1.5">{fix.alternatives.map((a, i) => <li key={a.label} className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm text-fg-2">{a.label}</span><Button size="sm" variant="outline" loading={busy} onClick={() => void onDecide('modify', { alternative: i, value: a.input ? val : undefined })}>Use this</Button></li>)}</ul></div>
              )}
            </div>
          )}
          {mode === 'risk' && (
            <div className="space-y-2 rounded border border-line bg-raised/40 p-3">
              <Field label="Justification" hint="Recorded with the design and shown to the board. The finding stays open in the record. At least 10 characters."><TextArea rows={2} value={note} maxLength={600} onChange={(e) => setNote(e.target.value)} /></Field>
              <Button size="sm" variant="danger" loading={busy} disabled={note.trim().length < 10} onClick={() => void onDecide('risk_accept', { note: note.trim() })}>Record risk acceptance</Button>
            </div>
          )}
        </div>
      )}
      {gap.state !== 'open' && gap.state === 'risk_accepted' && <div className="mt-3"><Button size="sm" variant="ghost" loading={busy} onClick={() => void onDecide('reopen')}>Reopen</Button></div>}
    </li>
  );
}

export function GapsStep({ design, actions, go }: StepProps) {
  const v = design.validation;
  const [sev, setSev] = useState<string>('all');
  const [src, setSrc] = useState<string>('all');
  const [bulk, setBulk] = useState<string | null>(null);
  const gaps = useMemo(() => v?.gaps ?? [], [v]);
  const sources = useMemo(() => [...new Set(gaps.map((g) => g.source))], [gaps]);
  const shown = gaps.filter((g) => (sev === 'all' || g.severity === sev) && (src === 'all' || g.source === src));
  const open = gaps.filter((g) => g.state === 'open');
  const simple = open.filter((g) => g.fix && !g.fix.input && !g.fix.alternatives?.length);
  const resolved = Object.entries(design.decisions).filter(([id, d]) => d.status !== 'risk_accepted' && !gaps.some((g) => g.id === id));
  if (!v) return <EmptyState title="Nothing to review yet" description="Choose a blueprint first." />;

  const acceptAll = async () => {
    let cur: typeof design | null = design;
    for (const g of simple) {
      if (!cur?.validation?.gaps.some((x) => x.id === g.id && x.state === 'open')) continue; // an earlier fix already cleared it
      setBulk(g.title);
      cur = (await actions.decide(g.id, 'accept')) ?? null;
      if (!cur) break;
    }
    setBulk(null);
  };
  const goTo = (id: string) => { go('diagram'); sessionStorage.setItem('studio.select', id); };

  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><p className="text-sm font-medium text-fg">{open.length ? `${open.length} open gap${open.length === 1 ? '' : 's'}` : 'No open gaps'}</p><p className="text-xs text-fg-3">{gaps.length - open.length} decided, {resolved.length} resolved by an accepted recommendation. Accepting applies the change to your choices or diagram and re-validates immediately.</p></div>
          {simple.length > 1 && <Button variant="outline" size="sm" leading={<ListChecks className="h-4 w-4" aria-hidden />} loading={!!bulk} disabled={actions.busy && !bulk} onClick={() => void acceptAll()}>Accept the {simple.length} fixes that need no input</Button>}
        </div>
        {bulk && <p role="status" className="mt-2 text-xs text-fg-3">Applying: {bulk}…</p>}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <SegmentedControl size="sm" label="Severity" value={sev} onChange={setSev} options={[{ value: 'all', label: 'All' }, ...SEV.map((s) => ({ value: s, label: `${s} ${gaps.filter((g) => g.severity === s).length}` }))]} />
          {sources.length > 1 && <Select label="Source" className="w-44" value={src} onValueChange={setSrc} options={[{ value: 'all', label: 'All sources' }, ...sources.map((s) => ({ value: s, label: titleCase(s) }))]} />}
        </div>
      </Panel>
      {actions.error && <ErrorNote>{actions.error}</ErrorNote>}
      {shown.length === 0 ? <EmptyState icon={<ShieldCheck className="h-4 w-4" aria-hidden />} title={gaps.length ? 'No gaps match these filters' : 'No gaps found'} description={gaps.length ? undefined : 'The checks that ran found nothing to fix for this design as declared. That is not proof it is compliant; see the coverage and the components not assessed.'} /> : (
        <ul className="space-y-3">{shown.map((g) => <GapCard key={g.id} gap={g} busy={actions.busy} onGoTo={goTo} onDecide={(a, x) => actions.decide(g.id, a, x)} />)}</ul>
      )}
      {resolved.length > 0 && (
        <Panel title="Resolved by your decisions" description="These no longer appear because the change was applied.">
          <ul className="divide-y divide-line-subtle text-sm">{resolved.map(([id, d]) => <li key={id} className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0 last:pb-0"><span className="min-w-0 text-fg-2"><Badge tone="healthy">{d.status}</Badge> <span className="ml-1">{d.title ?? id}</span>{d.fix_label && <span className="block text-xs text-fg-3">{d.fix_label}</span>}</span><Button size="sm" variant="ghost" loading={actions.busy} onClick={() => void actions.decide(id, 'reopen')}>Reopen</Button></li>)}</ul>
          <p className="mt-2 text-xs text-fg-3">Reopening removes the record. It does not undo the change that was applied; edit the choices or diagram to change it back.</p>
        </Panel>
      )}
      <div className="flex justify-end"><Button variant="primary" trailing={<ArrowRight className="h-4 w-4" aria-hidden />} onClick={() => go('export')}>Continue to export</Button></div>
    </div>
  );
}
