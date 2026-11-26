import { AlertTriangle, ArrowRight, Wand2 } from 'lucide-react';
import { useMemo } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Field, Select, Switch, TextInput } from '@/components/ui/Inputs';
import { Panel } from '@/components/ui/Panel';
import { cn } from '@/lib/cn';
import { ArchitecturePreview, EditorProvider } from './ArchitectureEditor';
import { ErrorNote, type StepProps } from './shared';
import type { Notice, Opt, Selections } from './types';

const SOURCE: Record<string, string> = { you: 'set by you', 'recommendation accepted': 'from an accepted recommendation', 'changed with the cloud': 'changed with the cloud' };
const src = (s: string | undefined) => (s ? SOURCE[s] ?? s : null);

function NoticeLine({ n }: { n: Notice | null | undefined }) {
  if (!n) return null;
  return (
    <p className="mt-1 flex items-start gap-1.5 text-xs text-fg-2"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-medium" aria-hidden />
      {n.technology}: {n.status ?? n.lifecycle ?? 'flagged'}{n.standard_id ? ` (${n.standard_id})` : ''}{n.support_end ? `, support ends ${n.support_end}` : ''}{n.estate_apps ? `, used by ${n.estate_apps} existing application(s)` : ''}.</p>
  );
}

function Choice({ label, value, options, onChange, note, source, disabled }: { label: string; value: string | null; options: Opt[]; onChange: (v: string) => void; note?: React.ReactNode; source?: string; disabled?: boolean }) {
  const cur = options.find((o) => o.id === value);
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2"><span className="micro">{label}</span>{source && <span className="text-[10px] text-fg-3">{source}</span>}</div>
      <Select label={label} className="w-full [&>span:first-child]:truncate [&>span:first-child]:text-left" value={value ?? ''} onValueChange={onChange} options={options.map((o) => ({ value: o.id, label: o.label }))} placeholder="Choose" />
      {cur?.note && <p className="mt-1 text-xs text-fg-3">{cur.note}</p>}
      {note}
      {disabled && null}
    </div>
  );
}

export function CustomiseStep({ design, catalog, actions, go }: StepProps) {
  const s = design.selections;
  const so = design.selection_sources ?? {};
  const set = (p: Partial<Selections>) => void actions.patch({ selections: p });
  const cloud = catalog.clouds.find((c) => c.id === s.cloud);
  const deployments = catalog.deployments[s.cloud] ?? [];
  const llm = catalog.llms.find((l) => l.id === s.llm);
  const backend = catalog.backends.find((b) => b.id === s.backend);
  const posture = useMemo(() => new Set(s.posture), [s.posture]);
  const togglePosture = (id: string, on: boolean) => set({ posture: catalog.posture.map((p) => p.id).filter((x) => (x === id ? on : posture.has(x))) });
  const nfr = design.nfr;
  const missing = catalog.nfr_fields.filter((f) => ['availability', 'rto_hours', 'rpo_minutes', 'latency_ms', 'throughput_tps', 'compliance'].includes(f.key) && (nfr[f.key] === undefined || nfr[f.key] === null)).length;

  return (
    <EditorProvider>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0 space-y-4">
          {actions.error && <ErrorNote>{actions.error}</ErrorNote>}
          <Panel title="Platform" description="Each choice changes the components in the diagram and the properties the standards check.">
            <div className="grid gap-4 sm:grid-cols-2">
              <Choice label="Cloud provider" value={s.cloud} options={catalog.clouds} source={src(so.cloud) ?? undefined} onChange={(v) => set({ cloud: v })}
                note={cloud && !cloud.covered ? <p className="mt-1 text-xs text-fg-2"><AlertTriangle className="mr-1 inline h-3 w-3 text-medium" aria-hidden />{catalog.coverage_note}</p> : null} />
              <Choice label="Region" value={s.region} options={catalog.regions} source={src(so.region) ?? undefined} onChange={(v) => set({ region: v })}
                note={!catalog.approved_regions.includes(s.region) ? <p className="mt-1 text-xs text-fg-2"><AlertTriangle className="mr-1 inline h-3 w-3 text-medium" aria-hidden />Not an approved region; this will be reported as a gap.</p> : null} />
              <Choice label="Deployment" value={s.deployment} options={deployments} source={src(so.deployment) ?? undefined} onChange={(v) => set({ deployment: v })} />
              <Choice label="Infrastructure as code" value={s.iac} options={catalog.iac} source={src(so.iac) ?? undefined} onChange={(v) => set({ iac: v })} />
              <Choice label="Backend technology" value={s.backend} options={catalog.backends} source={src(so.backend) ?? undefined} onChange={(v) => set({ backend: v })} note={<NoticeLine n={backend?.notice} />} />
              <Choice label="Language model" value={s.llm} options={catalog.llms} source={src(so.llm) ?? undefined} onChange={(v) => set({ llm: v })} note={<NoticeLine n={llm?.notice} />} />
              <Choice label="Messaging" value={s.messaging} options={catalog.messaging} source={src(so.messaging) ?? undefined} onChange={(v) => set({ messaging: v })} />
            </div>
            <fieldset className="mt-4">
              <legend className="micro mb-1.5 flex w-full items-baseline justify-between"><span>Data stores</span>{so.databases && <span className="text-[10px] normal-case text-fg-3">{src(so.databases)}</span>}</legend>
              <div className="grid gap-1.5 sm:grid-cols-2">
                {catalog.databases.map((d) => (
                  <label key={d.id} className="flex cursor-pointer items-start gap-2 rounded border border-line px-2.5 py-2 text-sm hover:bg-raised/50">
                    <input type="checkbox" className="mt-0.5 h-3.5 w-3.5 accent-[rgb(var(--accent))]" checked={s.databases.includes(d.id)} onChange={(e) => set({ databases: e.target.checked ? [...s.databases, d.id] : s.databases.filter((x) => x !== d.id) })} />
                    <span className="min-w-0"><span className="block text-fg">{d.label}</span>{d.note && <span className="block text-xs text-fg-3">{d.note}</span>}<NoticeLine n={d.notice} /></span>
                  </label>
                ))}
              </div>
            </fieldset>
          </Panel>

          <Panel title="Workload" description="These shape the availability, exposure and data controls that are checked.">
            <div className="grid gap-4 sm:grid-cols-2">
              <Choice label="Service tier" value={s.tier} options={catalog.tiers} source={src(so.tier) ?? undefined} onChange={(v) => set({ tier: v })} />
              <Choice label="Exposure" value={s.exposure} options={catalog.exposure} source={src(so.exposure) ?? undefined} onChange={(v) => set({ exposure: v })} />
              <div>
                <span className="micro mb-1.5 block">Data classification</span>
                <Select label="Data classification" className="w-full" value={s.classification ?? '_'} onValueChange={(v) => set({ classification: v === '_' ? null : v })} options={[{ value: '_', label: 'Not specified' }, ...catalog.classifications.map((c) => ({ value: c.id, label: c.label }))]} />
              </div>
              <div className="flex items-center justify-between gap-3 rounded border border-line px-3 py-2 sm:col-span-2">
                <div><p className="text-sm text-fg">Handles personal data</p><p className="text-xs text-fg-3">Adds the residency and privacy checks.</p></div>
                <Switch label="Handles personal data" checked={!!s.personal_data} onCheckedChange={(c) => set({ personal_data: c })} />
              </div>
              <Field label="Instances (optional)" hint="Leave blank if not decided. It is not assumed."><NumberBox label="Instances" value={s.instances} onCommit={(v) => set({ instances: v })} /></Field>
              <Field label="Data retention in days (optional)"><NumberBox label="Data retention in days" value={s.retention_days} onCommit={(v) => set({ retention_days: v })} /></Field>
            </div>
          </Panel>

          <Panel title="Security and operational controls" description="Each switch sets specific properties on specific components. A control you leave off stays unset and the standards report it.">
            <div className="mb-3 flex gap-2"><Button size="sm" variant="outline" onClick={() => set({ posture: catalog.posture.map((p) => p.id) })}>Select all</Button><Button size="sm" variant="outline" onClick={() => set({ posture: [] })}>Clear all</Button></div>
            <ul className="grid gap-2 2xl:grid-cols-2">
              {catalog.posture.map((p) => (
                <li key={p.id} className={cn('flex items-start justify-between gap-3 rounded border px-3 py-2', posture.has(p.id) ? 'border-accent/40 bg-accent/5' : 'border-line')}>
                  <div className="min-w-0"><p className="text-sm text-fg">{p.label}</p><p className="text-xs text-fg-3">{p.description}</p>{p.standards.length > 0 && <p className="mt-1 font-mono text-[10.5px] text-fg-3">{p.standards.join(' · ')}</p>}</div>
                  <Switch label={p.label} checked={posture.has(p.id)} onCheckedChange={(c) => togglePosture(p.id, c)} />
                </li>
              ))}
            </ul>
            {so.posture && <p className="mt-2 text-xs text-fg-3">Controls: {src(so.posture)}.</p>}
          </Panel>

          <Panel title="Non-functional targets" description={missing ? `${missing} of the required targets are not stated. Enter them, or take the defaults for the tier, which are marked as suggested.` : 'All required targets are stated.'}>
            <div className="mb-3"><Button size="sm" variant="outline" leading={<Wand2 className="h-3.5 w-3.5" aria-hidden />} loading={actions.busy} onClick={() => void actions.suggestNfr()}>Suggest from the tier</Button></div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {catalog.nfr_fields.map((f) => {
                const v = nfr[f.key];
                const origin = design.nfr_origin?.[f.key];
                const text = Array.isArray(v) ? v.join(', ') : v === undefined || v === null ? '' : String(v);
                return (
                  <div key={f.key}>
                    <div className="mb-1.5 flex items-baseline justify-between gap-2"><label htmlFor={`nfr-${f.key}`} className="micro">{f.label}</label>{origin ? <span className={cn('text-[10px]', origin.includes('suggested') ? 'text-medium' : 'text-fg-3')}>{origin}</span> : <span className="text-[10px] text-fg-3">not stated</span>}</div>
                    <TextInput id={`nfr-${f.key}`} key={`${f.key}-${text}`} defaultValue={text} inputMode={f.kind === 'number' ? 'decimal' : 'text'} placeholder={f.kind === 'text' ? 'comma separated' : 'not stated'} disabled={actions.busy}
                      onBlur={(e) => { const nv = e.target.value.trim(); if (nv !== text) void actions.patch({ nfr: { [f.key]: nv === '' ? null : f.key === 'compliance' ? nv.split(',').map((x) => x.trim()).filter(Boolean) : nv } }); }} />
                  </div>
                );
              })}
            </div>
          </Panel>

          <Panel title="About this design">
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Title"><TextInput defaultValue={design.title} key={design.title} maxLength={120} onBlur={(e) => { const v = e.target.value.trim(); if (v.length >= 3 && v !== design.title) void actions.patch({ title: v }); }} /></Field>
              <div><span className="micro mb-1.5 block">Business domain</span><Select label="Business domain" className="w-full" value={design.domain || '_'} onValueChange={(v) => void actions.patch({ domain: v === '_' ? '' : v })} options={[{ value: '_', label: 'Not set' }, ...catalog.domains.map((d) => ({ value: d, label: d }))]} /></div>
              <Field label="Owner"><TextInput defaultValue={design.owner} key={design.owner} maxLength={80} onBlur={(e) => { const v = e.target.value.trim(); if (v !== design.owner) void actions.patch({ owner: v }); }} /></Field>
            </div>
            {catalog.apps.length > 0 && (
              <fieldset className="mt-4">
                <legend className="micro mb-1.5">Existing applications this design touches</legend>
                <p className="mb-2 text-xs text-fg-3">Linked applications bring their known risks and lifecycle into the validation.</p>
                <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
                  {catalog.apps.map((a) => {
                    const on = design.linked_apps.includes(a.id);
                    return <label key={a.id} className={cn('inline-flex cursor-pointer items-center gap-1.5 rounded border px-2 py-1 text-xs', on ? 'border-accent/40 bg-accent/10 text-fg' : 'border-line text-fg-2 hover:bg-raised/50')}><input type="checkbox" className="h-3 w-3 accent-[rgb(var(--accent))]" checked={on} onChange={(e) => void actions.patch({ linked_apps: e.target.checked ? [...design.linked_apps, a.id] : design.linked_apps.filter((x) => x !== a.id) })} />{a.name}</label>;
                  })}
                </div>
              </fieldset>
            )}
          </Panel>
          <div className="flex justify-end"><Button variant="primary" trailing={<ArrowRight className="h-4 w-4" aria-hidden />} onClick={() => go('diagram')}>Edit the diagram</Button></div>
        </div>

        <div className="xl:sticky xl:top-4 xl:self-start">
          <Panel title="Live diagram" description={`${design.architecture?.nodes.length ?? 0} components, ${design.architecture?.edges.length ?? 0} connections. Updates as you choose.`} actions={design.validation ? <Badge tone={design.validation.verdict === 'go' ? 'healthy' : design.validation.verdict === 'conditional' ? 'medium' : 'critical'}>{design.validation.readiness}/100</Badge> : undefined}>
            <ArchitecturePreview design={design} height={420} />
            <Button size="sm" variant="outline" className="mt-3" onClick={() => go('diagram')}>Open in the editor</Button>
            {actions.busy && <p role="status" className="mt-2 text-xs text-fg-3">Rebuilding the architecture…</p>}
          </Panel>
        </div>
      </div>
    </EditorProvider>
  );
}

function NumberBox({ label, value, onCommit }: { label: string; value: number | null; onCommit: (v: number | null) => void }) {
  return <TextInput type="number" min={1} aria-label={label} inputMode="numeric" key={String(value)} defaultValue={value ?? ''} placeholder="not decided"
    onBlur={(e) => { const t = e.target.value.trim(); const v = t === '' ? null : Math.floor(Number(t)); if (v !== value && (v === null || v >= 1)) onCommit(v); }} />;
}
