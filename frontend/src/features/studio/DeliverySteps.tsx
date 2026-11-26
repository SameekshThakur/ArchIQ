import { useQuery } from '@tanstack/react-query';
import { ArrowRight, CheckCircle2, Download, FileArchive, FileText, History, Image as ImageIcon, Send, XCircle } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { get } from '@/api/client';
import { AISummary, AIThinking } from '@/components/ai/AIPanel';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { CodeBlock } from '@/components/ui/Code';
import { Field, Tabs, TextArea, TextInput } from '@/components/ui/Inputs';
import { Modal } from '@/components/ui/Overlay';
import { EmptyState, Panel, SkeletonBlock } from '@/components/ui/Panel';
import { Timeline } from '@/components/ui/Timeline';
import type { AIMeta } from '@/api/types';
import { fmtDate } from '@/lib/format';
import { ErrorNote, VERDICT, type StepProps } from './shared';

const base = (n: number) => `/api/v1/studio/designs/${n}/export`;
const link = 'inline-flex h-7 items-center gap-1.5 rounded border border-line bg-raised px-2.5 text-xs font-medium text-fg hover:bg-overlay focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

export function ExportStep({ design, actions, go }: StepProps) {
  const [tab, setTab] = useState('document');
  const [label, setLabel] = useState('');
  const [restore, setRestore] = useState<number | null>(null);
  const stamp = design.updated_at ?? design.created_at;
  const doc = useQuery<{ markdown: string; filename: string; ai: AIMeta }>({ queryKey: ['studio', 'doc', design.n, stamp], queryFn: () => get(`/studio/designs/${design.n}/export/document`), enabled: tab === 'document' && !!design.architecture, staleTime: 60_000 });
  const ex = design.export;
  if (!design.architecture || !ex) return <EmptyState icon={<FileText className="h-4 w-4" aria-hidden />} title="Nothing to export yet" description="Choose a blueprint first." />;

  return (
    <div className="space-y-4">
      <Panel title="Target architecture pack" description="The document, the diagram and a starter project, all generated from the design as it stands now."
        actions={<><a className={link} href={`${base(design.n)}/document.md`} download><Download className="h-3.5 w-3.5" aria-hidden />Document (.md)</a><a className={link} href={`${base(design.n)}/starter.zip`} download><FileArchive className="h-3.5 w-3.5" aria-hidden />Starter (.zip)</a></>}>
        <Tabs value={tab} onValueChange={setTab} items={[
          { value: 'document', label: <span className="inline-flex items-center gap-1.5"><FileText className="h-3.5 w-3.5" aria-hidden />Document</span>, content: (
            doc.isLoading ? <div><AIThinking steps={['Collecting the validation results', 'Writing the summary from the computed figures']} /><SkeletonBlock className="mt-3 h-64" /></div>
              : doc.isError ? <ErrorNote>{(doc.error as Error).message}</ErrorNote>
              : doc.data ? <div className="space-y-3"><AISummary ai={doc.data.ai} title="Document summary" /><CodeBlock code={doc.data.markdown} language="markdown" filename={doc.data.filename} maxHeight={520} /></div> : null) },
          { value: 'diagram', label: <span className="inline-flex items-center gap-1.5"><ImageIcon className="h-3.5 w-3.5" aria-hidden />Diagram</span>, content: (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2"><a className={link} href={`${base(design.n)}/diagram.svg`} download><Download className="h-3.5 w-3.5" aria-hidden />SVG</a><a className={link} href={`${base(design.n)}/diagram.mmd`} download><Download className="h-3.5 w-3.5" aria-hidden />Mermaid</a></div>
              <div className="overflow-auto rounded border border-line bg-white p-2" tabIndex={0} role="region" aria-label="Architecture diagram, scrollable"><img src={`${base(design.n)}/diagram.svg?v=${encodeURIComponent(stamp)}`} alt={`Architecture diagram of ${design.title}: ${design.architecture.nodes.map((n) => n.name).join(', ')}`} className="mx-auto max-w-none" /></div>
            </div>) },
          { value: 'starter', label: <span className="inline-flex items-center gap-1.5"><FileArchive className="h-3.5 w-3.5" aria-hidden />Starter ZIP</span>, count: ex.manifest.length, content: (
            <div className="space-y-4">
              <p className="rounded border border-medium/30 bg-medium/10 px-3 py-2 text-sm text-fg-2">This is a starting point, not deployable infrastructure. Only the checks listed below were run on it.</p>
              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <p className="micro mb-1.5">Checks run ({ex.passed} passed, {ex.failed} failed)</p>
                  <ul className="space-y-1.5 text-xs">{ex.checks.map((c) => <li key={c.label} className="flex gap-1.5">{c.status === 'pass' ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-healthy" aria-label="passed" /> : <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-critical" aria-label="failed" />}<span><span className="text-fg">{c.label}</span> <span className="text-fg-3">{c.detail}</span></span></li>)}</ul>
                </div>
                <div>
                  <p className="micro mb-1.5">Not run</p>
                  <ul className="list-disc space-y-1 pl-4 text-xs text-fg-2">{ex.not_run.map((t) => <li key={t}>{t}</li>)}</ul>
                  {ex.notes.length > 0 && <><p className="micro mb-1.5 mt-3">Notes</p><ul className="list-disc space-y-1 pl-4 text-xs text-fg-2">{ex.notes.map((t) => <li key={t}>{t}</li>)}</ul></>}
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm"><caption className="sr-only">Files in the starter ZIP</caption>
                  <thead><tr className="text-left"><th scope="col" className="micro pb-2 pr-3">File</th><th scope="col" className="micro pb-2 pr-3">What it is</th><th scope="col" className="micro pb-2 pr-3">Checked by</th><th scope="col" className="micro pb-2 text-right">Bytes</th></tr></thead>
                  <tbody>{ex.manifest.map((f) => <tr key={f.path} className="border-t border-line-subtle align-top"><td className="py-1.5 pr-3 font-mono text-xs text-fg">{f.path}</td><td className="py-1.5 pr-3 text-xs text-fg-2">{f.what}</td><td className="py-1.5 pr-3 text-xs text-fg-3">{f.checked_by}</td><td className="num py-1.5 text-right font-mono text-xs text-fg-3">{f.bytes.toLocaleString()}</td></tr>)}</tbody>
                </table>
              </div>
            </div>) },
        ]} />
      </Panel>

      <Panel title="Versions" description="Save the design at a point in time. Submissions also keep a copy of exactly what was reviewed." actions={<History className="h-4 w-4 text-fg-3" aria-hidden />}>
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); void actions.saveVersion(label.trim()).then((d) => d && setLabel('')); }}>
          <div className="min-w-[220px] flex-1"><Field label="Version label (optional)"><TextInput value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. After security review" /></Field></div>
          <Button type="submit" variant="primary" loading={actions.busy}>Save version</Button>
        </form>
        {design.versions.length === 0 ? <p className="mt-3 text-sm text-fg-3">No versions saved yet.</p> : (
          <ul className="mt-4 divide-y divide-line-subtle">{[...design.versions].reverse().map((v) => (
            <li key={v.n} className="flex flex-wrap items-start justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
              <div className="min-w-0"><p className="text-sm text-fg"><span className="num font-mono text-fg-3">v{v.n}</span> {v.label} <span className="text-xs text-fg-3">{fmtDate(v.at)}</span></p>
                <p className="mt-0.5 text-xs text-fg-3">Readiness {v.summary.readiness}, {v.summary.components} components, {v.summary.coverage}% assessed, {Object.values(v.summary.open).reduce((a, b) => a + b, 0)} open gaps.</p>
                {v.changes.length > 0 && <p className="mt-0.5 text-xs text-fg-3">Since the previous version: {v.changes.join('; ')}.</p>}</div>
              <Button size="sm" variant="outline" onClick={() => setRestore(v.n)}>Restore</Button>
            </li>))}</ul>
        )}
        {actions.error && <div className="mt-3"><ErrorNote>{actions.error}</ErrorNote></div>}
      </Panel>
      <Modal open={restore !== null} onOpenChange={(o) => !o && setRestore(null)} title={`Restore version ${restore}?`} description="The current choices, edits and decisions are replaced."
        footer={<><Button variant="ghost" onClick={() => setRestore(null)}>Cancel</Button><Button variant="primary" loading={actions.busy} onClick={() => void actions.restoreVersion(restore!).then(() => setRestore(null))}>Restore</Button></>}>
        <p className="text-sm text-fg-2">Anything you changed since your last saved version will be lost. Save a version first if you want to keep it.</p>
      </Modal>
      <div className="flex justify-end"><Button variant="primary" trailing={<ArrowRight className="h-4 w-4" aria-hidden />} onClick={() => go('governance')}>Continue to governance</Button></div>
    </div>
  );
}

export function GovernanceStep({ design, actions }: StepProps) {
  const [notes, setNotes] = useState('');
  const [who, setWho] = useState(design.owner ?? '');
  const sub = design.submission;
  const v = design.validation;
  const blocked = design.checks.filter((c) => c.blocking && !c.ok);
  const stage = design.status;
  const submit = async () => { await actions.submit(notes.trim(), who.trim()); };
  if (!v) return <EmptyState title="Nothing to submit yet" description="Choose a blueprint first." />;
  const verdict = VERDICT[v.verdict];
  return (
    <div className="space-y-4">
      {sub && (
        <Panel className="border-healthy/40" title={<span className="flex items-center gap-2">Submitted as <span className="font-mono">{sub.arb_id}</span> <Badge tone="healthy">version {sub.version}</Badge></span>} description={`Submitted ${fmtDate(sub.submitted_at)}. Readiness at submission ${sub.readiness}, ${sub.conditions} condition(s). Stage: ${sub.stage.replace('_', ' ')}.`}
          actions={<Link to={`/reviews/${sub.arb_id}`} className={link}>Open the review</Link>}>
          {stage === 'changed_after_submission' ? <p className="text-sm text-fg-2">The design has changed since it was submitted. Submitting again sends the new version to the same review as {sub.arb_id}, and the earlier version stays on record.</p> : <p className="text-sm text-fg-2">This version is with the review board. Change the design to submit a new version.</p>}
        </Panel>
      )}
      <Panel title="Before you submit" description="The review board sees the validation exactly as shown in the previous steps.">
        <div className="mb-3 flex flex-wrap items-center gap-2"><Badge tone={verdict.tone}>{verdict.label}</Badge><span className="text-sm text-fg-2">Readiness <span className="num font-mono text-fg">{v.readiness}</span>/100 · {v.coverage.percent}% assessed</span></div>
        <ul className="space-y-2" aria-label="Submission checks">{design.checks.map((c) => (
          <li key={c.id} className="flex items-start gap-2 text-sm">{c.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-healthy" aria-label="met" /> : <XCircle className={`mt-0.5 h-4 w-4 shrink-0 ${c.blocking ? 'text-critical' : 'text-medium'}`} aria-label={c.blocking ? 'blocking' : 'warning'} />}
            <span><span className="text-fg">{c.label}</span>{!c.ok && <Badge tone={c.blocking ? 'critical' : 'medium'} className="ml-2">{c.blocking ? 'blocks submission' : 'goes to the board'}</Badge>}{c.detail && <span className="block text-xs text-fg-3">{c.detail}</span>}</span></li>))}</ul>
      </Panel>
      <Panel title={sub ? 'Submit a new version' : 'Submit to the architecture review board'} description="Creates a review in the existing workflow. It enters at “AI reviewed” and the board schedules the rest.">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Submitted by"><TextInput value={who} onChange={(e) => setWho(e.target.value)} maxLength={80} /></Field>
        </div>
        <div className="mt-3"><Field label="Notes for the board (optional)" hint="Context, deadlines, or why a gap is acceptable."><TextArea rows={3} value={notes} maxLength={1000} onChange={(e) => setNotes(e.target.value)} /></Field></div>
        {actions.error && <div className="mt-3"><ErrorNote>{actions.error}</ErrorNote></div>}
        {blocked.length > 0 && <p role="status" className="mt-3 text-sm text-fg-2">Resolve {blocked.length} blocking item{blocked.length === 1 ? '' : 's'} above before submitting.</p>}
        <div className="mt-4 flex items-center gap-3"><Button variant="primary" leading={<Send className="h-4 w-4" aria-hidden />} loading={actions.busy} disabled={blocked.length > 0 || stage === 'submitted'} onClick={() => void submit()}>{sub ? 'Submit new version' : 'Submit for review'}</Button>
          {stage === 'submitted' && <span className="text-xs text-fg-3">Already submitted. Change the design to submit a new version.</span>}</div>
      </Panel>
      {design.narration && design.narration.task?.startsWith('studio.submission') && <AISummary ai={design.narration} title="Submission summary" />}
      <Panel title="Workflow history" description="Every change, decision and submission on this design.">
        <Timeline items={[...design.workflow].reverse().map((w, i) => ({ id: `${w.at}-${i}`, title: w.event, meta: new Date(w.at).toLocaleString('en-GB'), body: w.note || undefined }))} />
      </Panel>
    </div>
  );
}
