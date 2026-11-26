import { ArrowRight, FileSearch, Sparkles } from 'lucide-react';
import { useEffect, useState } from 'react';
import { AISummary, AIThinking } from '@/components/ai/AIPanel';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Field, Select, TextArea, TextInput } from '@/components/ui/Inputs';
import { EmptyState, Panel, ProgressBar } from '@/components/ui/Panel';
import { titleCase } from '@/lib/format';
import { ErrorNote, EXAMPLES, type StepProps } from './shared';
import type { Catalog } from './types';

const MIN = 20;

/** The same form starts a design and re-analyses one. */
export function RequirementForm({ catalog, initial, onSubmit, busy, error, submitLabel, showTitle }: {
  catalog: Catalog; initial?: { text: string; title: string; domain: string }; onSubmit: (v: { text: string; title: string; domain: string }) => void; busy: boolean; error: string | null; submitLabel: string; showTitle?: boolean;
}) {
  const [text, setText] = useState(initial?.text ?? '');
  const [title, setTitle] = useState(initial?.title ?? '');
  const [domain, setDomain] = useState(initial?.domain ?? '');
  const [touched, setTouched] = useState(false);
  useEffect(() => { if (initial) { setText(initial.text); setDomain(initial.domain); } }, [initial?.text]); // eslint-disable-line react-hooks/exhaustive-deps
  const short = text.trim().length < MIN;
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); setTouched(true); if (!short) onSubmit({ text: text.trim(), title: title.trim(), domain }); }} noValidate>
      <Field label="Business or technical requirements" hint={`Describe what the system must do and the constraints it lives under: availability, recovery, latency, data sensitivity, residency, integrations, users. ${text.trim().length.toLocaleString()} characters.`}>
        <TextArea rows={9} value={text} onChange={(e) => setText(e.target.value)} onBlur={() => setTouched(true)} maxLength={20000} aria-invalid={touched && short} aria-describedby={touched && short ? 'req-err' : undefined} placeholder="For example: a customer portal for claims intake with 99.9% availability, RTO 4 hours, personal data that must stay in the UK…" disabled={busy} />
      </Field>
      {touched && short && <ErrorNote id="req-err">Write at least a sentence or two ({MIN} characters or more) so there is something to analyse.</ErrorNote>}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="micro mr-1">Insert an example</span>
        {EXAMPLES.map((e) => <Button key={e.label} size="sm" variant="outline" disabled={busy} onClick={() => setText(e.text)}>{e.label}</Button>)}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {showTitle && <Field label="Title (optional)" hint="Leave blank to name it after the blueprint."><TextInput value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} disabled={busy} /></Field>}
        <div>
          <span className="micro mb-1.5 block">Business domain (optional)</span>
          <Select label="Business domain" className="w-full" value={domain || '_'} onValueChange={(v) => setDomain(v === '_' ? '' : v)} options={[{ value: '_', label: 'Infer from the text' }, ...catalog.domains.map((d) => ({ value: d, label: d }))]} />
        </div>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="flex items-center gap-3">
        <Button type="submit" variant="primary" loading={busy} leading={<Sparkles className="h-4 w-4" aria-hidden />}>{submitLabel}</Button>
        <p className="text-xs text-fg-3">Targets are read from your wording by rules; each one keeps the sentence it came from. Nothing is assumed.</p>
      </div>
    </form>
  );
}

export function RequirementsStep({ design, catalog, actions, go }: StepProps) {
  const e = design.extraction;
  const text = design.requirement.text;
  return (
    <div className="space-y-4">
      <Panel title="Requirements" description="Edit the text and analyse again to refresh the facts and the recommendation. Your choices and edits are kept where they still apply.">
        {actions.busy ? <AIThinking steps={['Reading the requirements', 'Extracting targets with their evidence', 'Ranking the 12 blueprints']} /> : (
          <RequirementForm catalog={catalog} initial={{ text, title: design.title, domain: design.domain }} busy={actions.busy} error={actions.error} submitLabel="Analyse again"
            onSubmit={(v) => void actions.reanalyse(v.text, v.domain)} />
        )}
      </Panel>
      {design.ai?.requirements && <AISummary ai={design.ai.requirements} title="What was found" />}
      <Panel title="What was found in the text" description="Every value below is quoted from your requirements. Anything not stated is shown as missing, not guessed.">
        {e.facts.length === 0 ? <EmptyState icon={<FileSearch className="h-4 w-4" aria-hidden />} title="No targets or constraints were recognised" description="Add numbers and constraints, such as an availability percentage, an RTO, or the sensitivity of the data, then analyse again." /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Facts found in the requirements</caption>
              <thead><tr className="text-left"><th scope="col" className="micro pb-2 pr-3">Fact</th><th scope="col" className="micro pb-2 pr-3">Value</th><th scope="col" className="micro pb-2">From your text</th></tr></thead>
              <tbody>{e.facts.map((f) => (
                <tr key={f.key} className="border-t border-line-subtle align-top"><td className="py-2 pr-3 text-fg-2">{f.label}</td><td className="py-2 pr-3 font-mono text-fg">{String(f.value)}</td><td className="py-2 text-xs italic text-fg-3">“{f.evidence}”</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <p className="micro mb-1.5">Non-functional targets stated ({e.nfr_present.length} of 6)</p>
            <ProgressBar value={(e.nfr_present.length / 6) * 100} tone={e.nfr_missing.length ? 'medium' : 'healthy'} label="Non-functional targets stated" />
            {e.nfr_missing.length > 0 && <p className="mt-2 text-xs text-fg-3">Not stated: {e.nfr_missing.map((k) => catalog.nfr_fields.find((f) => f.key === k)?.label ?? titleCase(k)).join(', ')}. You can set them in Customise, or take the tier defaults, which are marked as suggested.</p>}
          </div>
          {e.systems.length > 0 && (
            <div>
              <p className="micro mb-1.5">Existing systems named in the text</p>
              <ul className="space-y-1 text-xs text-fg-2">{e.systems.map((s) => <li key={s.id}><span className="text-fg">{s.name}</span> <span className="text-fg-3">({s.lifecycle.replace('_', ' ')}, {s.criticality})</span></li>)}</ul>
              <p className="mt-1 text-xs text-fg-3">Matched by exact name against the estate only.</p>
            </div>
          )}
        </div>
      </Panel>
      <div className="flex justify-end"><Button variant="primary" trailing={<ArrowRight className="h-4 w-4" aria-hidden />} onClick={() => go('recommendation')}>See the recommendation</Button></div>
    </div>
  );
}

export function RecommendationStep({ design, catalog, actions, go }: StepProps) {
  const rec = design.recommendation;
  const top = rec.recommended;
  const [pick, setPick] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const current = design.blueprint_id;
  const name = (id: string | null) => catalog.blueprints.find((b) => b.id === id)?.name ?? id ?? 'none';
  const using = current === top?.id;
  const choose = async (id: string) => { const d = await actions.chooseBlueprint(id, reason.trim()); if (d) { setPick(null); setReason(''); } };
  const needReason = (id: string) => !!top && id !== top.id;
  const reasonOk = reason.trim().length >= 5;

  return (
    <div className="space-y-4">
      {design.ai?.recommendation && !actions.busy && <AISummary ai={design.ai.recommendation} title="Recommendation summary" />}
      {actions.busy && <AIThinking steps={['Applying your choice', 'Rebuilding the architecture', 'Validating']} />}
      {rec.needs_more_detail && (
        <Panel title="More detail needed" className="border-medium/40"><p className="text-sm text-fg-2">{rec.message}</p><p className="mt-2 text-xs text-fg-3">No blueprint scored high enough to recommend honestly (the threshold is {rec.threshold}). Add detail in Requirements, or choose one yourself below.</p></Panel>
      )}
      {top && (
        <Panel title={<span className="flex items-center gap-2">Recommended: {top.title ?? top.name} {using && <Badge tone="healthy">In use</Badge>}</span>} description={`Confidence ${Math.round(top.confidence * 100)}%, from a score of ${top.score} and a margin of ${top.margin} over the runner-up. This is a ranking of keyword evidence, not a prediction.`}
          actions={!using ? <Button variant="primary" size="sm" loading={actions.busy} onClick={() => void choose(top.id)}>Use this blueprint</Button> : undefined}>
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <p className="micro mb-1.5">Why it was chosen</p>
              <ul className="space-y-2">{top.rationale.map((s) => (
                <li key={s.label + s.term} className="text-sm"><span className="font-medium text-fg">{s.label}</span> <span className="num font-mono text-xs text-fg-3">+{s.weight}</span><br /><span className="text-xs italic text-fg-3">“{s.evidence}”</span></li>
              ))}</ul>
            </div>
            <div className="space-y-3">
              {top.when_to_use?.length > 0 && <div><p className="micro mb-1.5">What the blueprint is for</p><ul className="list-disc space-y-1 pl-4 text-xs text-fg-2">{top.when_to_use.map((t) => <li key={t}>{t}</li>)}</ul></div>}
              {top.watch_outs?.length > 0 && <div><p className="micro mb-1.5">Watch out for</p><ul className="list-disc space-y-1 pl-4 text-xs text-fg-2">{top.watch_outs.map((t) => <li key={t}>{t}</li>)}</ul></div>}
              {top.when_overlap?.length > 0 && <p className="text-xs text-fg-3">Close to: {top.when_overlap.join(', ')}.</p>}
            </div>
          </div>
        </Panel>
      )}
      {rec.combine.length > 0 && (
        <Panel title="Could be combined" description="These cover a second need the text mentions. The Studio designs one blueprint at a time; the others are shown so nothing is lost.">
          <ul className="space-y-2 text-sm">{rec.combine.map((c) => <li key={c.id}><span className="font-medium text-fg">{c.name}</span> <span className="text-fg-2">— {c.reason}</span></li>)}</ul>
        </Panel>
      )}
      <Panel title="Alternatives" description="Why each was ranked lower, and when it would be the better choice.">
        <ul className="divide-y divide-line-subtle">
          {rec.alternatives.map((a) => (
            <li key={a.id} className="py-3 first:pt-0 last:pb-0" data-testid={`alt-${a.id}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium text-fg">{a.name} <span className="num font-mono text-xs font-normal text-fg-3">score {a.score}</span> {current === a.id && <Badge tone="accent">In use</Badge>}</p>
                {current !== a.id && <Button size="sm" variant="outline" onClick={() => setPick(pick === a.id ? null : a.id)} aria-expanded={pick === a.id}>Use this instead</Button>}
              </div>
              <p className="mt-1 text-xs text-fg-2">{a.why_not}</p>
              <p className="mt-0.5 text-xs text-fg-3">Choose it when: {a.choose_when}</p>
              {pick === a.id && (
                <div className="mt-3 space-y-2 rounded border border-line bg-raised/40 p-3">
                  <Field label="Why are you choosing this one?" hint="Recorded with the design and shown to the review board. At least 5 characters."><TextInput value={reason} onChange={(e) => setReason(e.target.value)} maxLength={400} /></Field>
                  <div className="flex items-center gap-2"><Button size="sm" variant="primary" loading={actions.busy} disabled={needReason(a.id) && !reasonOk} onClick={() => void choose(a.id)}>Switch to {a.name}</Button><span className="text-xs text-fg-3">Your customisations are re-applied where they still make sense; the rest are reset.</span></div>
                </div>
              )}
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="Choose any blueprint" description="If you already know which pattern you need, choose it directly.">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[260px] flex-1"><Select label="Blueprint" className="w-full" placeholder="Choose a blueprint" value={pick && !rec.alternatives.some((a) => a.id === pick) ? pick : ''} onValueChange={(v) => setPick(v)} options={catalog.blueprints.map((b) => ({ value: b.id, label: `${b.name} (${b.category})` }))} /></div>
        </div>
        {pick && !rec.alternatives.some((a) => a.id === pick) && (
          <div className="mt-3 space-y-2">
            <Field label="Reason (needed when it differs from the recommendation)"><TextInput value={reason} onChange={(e) => setReason(e.target.value)} maxLength={400} /></Field>
            <Button size="sm" variant="primary" loading={actions.busy} disabled={needReason(pick) && !reasonOk} onClick={() => void choose(pick)}>Use {name(pick)}</Button>
          </div>
        )}
      </Panel>
      {actions.error && <ErrorNote>{actions.error}</ErrorNote>}
      {design.blueprint_choice?.overridden && <p className="text-xs text-fg-3">You chose {name(current)} instead of the recommendation: “{design.blueprint_choice.reason}”.</p>}
      <div className="flex justify-end"><Button variant="primary" disabled={!current} trailing={<ArrowRight className="h-4 w-4" aria-hidden />} onClick={() => go('customise')}>{current ? 'Customise ' + name(current) : 'Choose a blueprint first'}</Button></div>
    </div>
  );
}

