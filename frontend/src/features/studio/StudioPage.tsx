import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Blocks, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AIThinking } from '@/components/ai/AIPanel';
import { Badge } from '@/components/ui/Badge';
import { Button, IconButton } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Overlay';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { EmptyState, Panel, SkeletonBlock } from '@/components/ui/Panel';
import { cn } from '@/lib/cn';
import { fmtDate } from '@/lib/format';
import { ArchitectureEditor, EditorProvider } from './ArchitectureEditor';
import { CustomiseStep } from './CustomiseStep';
import { ExportStep, GovernanceStep } from './DeliverySteps';
import { RecommendationStep, RequirementForm, RequirementsStep } from './RequirementSteps';
import { STATUS, STEPS, VERDICT, type StepId, type StepProps } from './shared';
import { GapsStep, ValidationStep } from './ValidationSteps';
import { createDesign, deleteDesign, useCatalog, useDesignActions, useDesignQuery, useDesigns } from './useStudio';
import type { Catalog, Design } from './types';

function DiagramStep({ design, catalog, actions, go }: StepProps) {
  return (
    <EditorProvider>
      <div className="space-y-4">
        {actions.error && <p role="alert" className="rounded border border-critical/30 bg-critical/10 px-3 py-2 text-sm text-fg">{actions.error}</p>}
        <ArchitectureEditor design={design} catalog={catalog} busy={actions.busy} onOps={actions.setOps} />
        <div className="flex justify-end"><Button variant="primary" onClick={() => go('validation')}>See the validation</Button></div>
      </div>
    </EditorProvider>
  );
}

function Workspace({ n, catalog, step, setStep }: { n: number; catalog: Catalog; step: StepId; setStep: (s: StepId) => void }) {
  const q = useDesignQuery(n);
  const actions = useDesignActions(n);
  if (q.isLoading) return <div className="space-y-3" aria-busy="true" aria-label="Loading the design"><SkeletonBlock className="h-16" /><SkeletonBlock className="h-96" /></div>;
  if (q.isError || !q.data) return <EmptyState title="This design could not be opened" description={(q.error as Error | null)?.message ?? 'It may have been deleted.'} action={<Link to="/studio" className="text-sm text-accent hover:underline">Back to your designs</Link>} />;
  const d: Design = q.data;
  const has = !!d.blueprint_id;
  const active: StepId = !has && step !== 'requirements' ? 'recommendation' : step;
  const props: StepProps = { design: d, catalog, actions, go: (s) => { setStep(s as StepId); window.scrollTo({ top: 0 }); } };
  const open = d.validation ? SEV_OPEN(d) : 0;
  const status = STATUS[d.status];
  const verdict = d.validation ? VERDICT[d.validation.verdict] : null;
  const Body = { requirements: RequirementsStep, recommendation: RecommendationStep, customise: CustomiseStep, diagram: DiagramStep, validation: ValidationStep, gaps: GapsStep, export: ExportStep, governance: GovernanceStep }[active];
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="min-w-0 truncate text-base font-semibold text-fg">{d.title}</h2>
        <Badge mono>{d.ref}</Badge>
        <Badge tone={status.tone}>{status.label}</Badge>
        {d.submission && <Link to={`/reviews/${d.submission.arb_id}`} className="font-mono text-xs text-accent hover:underline">{d.submission.arb_id}</Link>}
        {d.validation && verdict && <span className="ml-auto flex items-center gap-2 text-xs text-fg-2" aria-live="polite" data-testid="readiness-chip"><Badge tone={verdict.tone}>{verdict.label}</Badge>readiness <span className="num font-mono text-fg">{d.validation.readiness}</span>/100</span>}
      </div>
      <div className="space-y-5">
        <nav aria-label="Studio steps" className="-mx-1 overflow-x-auto px-1 pb-1">
          <ol className="flex min-w-max gap-1 border-b border-line">
            {STEPS.map((s, i) => {
              const locked = !has && i > 1;
              return (
                <li key={s.id}>
                  <button type="button" disabled={locked} aria-current={active === s.id ? 'step' : undefined} onClick={() => props.go(s.id)}
                    className={cn('-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-40',
                      active === s.id ? 'border-accent font-medium text-fg' : 'border-transparent text-fg-2 hover:text-fg')}>
                    <span className="num flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line font-mono text-[10px]">{i + 1}</span>
                    <span className="whitespace-nowrap">{s.label}</span>
                    {s.id === 'gaps' && open > 0 && <span className="num rounded bg-high/15 px-1.5 font-mono text-[10px] text-high" aria-label={`${open} open`}>{open}</span>}
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
        <div className="min-w-0" data-testid={`step-${active}`}><Body {...props} /></div>
      </div>
    </div>
  );
}
const SEV_OPEN = (d: Design) => d.validation?.gaps.filter((g) => g.state === 'open').length ?? 0;

function Start({ catalog }: { catalog: Catalog }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const list = useDesigns();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [del, setDel] = useState<{ n: number; title: string } | null>(null);
  const [delErr, setDelErr] = useState<string | null>(null);
  const create = async (v: { text: string; title: string; domain: string }) => {
    setBusy(true); setError(null);
    try { const d = await createDesign({ text: v.text, title: v.title || undefined, domain: v.domain || undefined }); qc.setQueryData(['studio', 'design', d.n], d); void qc.invalidateQueries({ queryKey: ['studio', 'designs'] }); nav(`/studio?design=${d.n}&step=recommendation`); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const rows = list.data?.items ?? [];
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <Panel title="Start with the requirements" description="Describe the system in your own words. The Studio finds the targets in your text, recommends the closest blueprint, and takes you through customising, validating and submitting it.">
        {busy ? <AIThinking steps={['Reading the requirements', 'Extracting targets with their evidence', 'Ranking the 12 blueprints', 'Building the first architecture']} /> : <RequirementForm catalog={catalog} onSubmit={(v) => void create(v)} busy={busy} error={error} submitLabel="Analyse and recommend" showTitle />}
      </Panel>
      <Panel title="Your designs" description={rows.length ? `${rows.length} saved` : undefined} bodyClassName="p-0">
        {list.isLoading ? <div className="space-y-2 p-4"><SkeletonBlock className="h-12" /><SkeletonBlock className="h-12" /></div>
          : list.isError ? <p role="alert" className="p-4 text-sm text-fg-2">Could not load your designs: {(list.error as Error).message}</p>
          : rows.length === 0 ? <div className="p-4"><EmptyState icon={<Blocks className="h-4 w-4" aria-hidden />} title="No designs yet" description="Designs you start here are saved automatically and listed here." /></div> : (
            <ul className="divide-y divide-line-subtle">{rows.map((r) => {
              const st = STATUS[r.status];
              return (
                <li key={r.n} className="flex items-center gap-2 px-4 py-3" data-testid={`design-${r.n}`}>
                  <Link to={`/studio?design=${r.n}&step=${r.blueprint_id ? 'customise' : 'recommendation'}`} className="min-w-0 flex-1 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
                    <p className="truncate text-sm font-medium text-fg">{r.title}</p>
                    <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-fg-3"><span className="font-mono">{r.ref}</span><Badge tone={st.tone}>{st.label}</Badge>{r.arb_id && <span className="font-mono">{r.arb_id}</span>}<span>{fmtDate(r.updated_at ?? r.created_at)}</span></p>
                  </Link>
                  {!r.arb_id && <IconButton label={`Delete ${r.title}`} size="sm" onClick={() => { setDelErr(null); setDel({ n: r.n, title: r.title }); }}><Trash2 className="h-4 w-4" /></IconButton>}
                </li>
              );
            })}</ul>
          )}
      </Panel>
      <Modal open={!!del} onOpenChange={(o) => !o && setDel(null)} title="Delete this design?" description={del?.title}
        footer={<><Button variant="ghost" onClick={() => setDel(null)}>Cancel</Button><Button variant="danger" onClick={() => void deleteDesign(del!.n).then(() => { setDel(null); void qc.invalidateQueries({ queryKey: ['studio', 'designs'] }); }).catch((e: Error) => setDelErr(e.message))}>Delete</Button></>}>
        <p className="text-sm text-fg-2">The design, its versions and decisions are removed. This cannot be undone.</p>
        {delErr && <p role="alert" className="mt-2 text-sm text-critical">{delErr}</p>}
      </Modal>
    </div>
  );
}

export default function StudioPage() {
  const [params, setParams] = useSearchParams();
  const cat = useCatalog();
  const n = Number(params.get('design')) || null;
  const stepParam = params.get('step') as StepId | null;
  const step: StepId = STEPS.some((s) => s.id === stepParam) ? (stepParam as StepId) : 'requirements';
  return (
    <Page>
      <PageHeader title="Blueprint Intelligence Studio" description="Go from business requirements to a customised, validated and governance-ready target architecture, built on the approved blueprints and checked by the same rules the review board uses."
        actions={n ? <Button variant="ghost" leading={<ArrowLeft className="h-4 w-4" aria-hidden />} onClick={() => setParams({})}>All designs</Button> : <Link to="/blueprints" className="inline-flex h-8 items-center gap-1.5 rounded px-3 text-sm text-fg-2 hover:bg-raised hover:text-fg"><Blocks className="h-4 w-4" aria-hidden />Blueprint catalogue</Link>} />
      {cat.isLoading ? <div className="space-y-3" aria-busy="true"><SkeletonBlock className="h-40" /><SkeletonBlock className="h-64" /></div>
        : cat.isError || !cat.data ? <EmptyState title="The Studio could not load its catalogue" description={(cat.error as Error | null)?.message ?? 'Check that the API is running, then try again.'} action={<Button leading={<Plus className="h-4 w-4" />} onClick={() => void cat.refetch()}>Try again</Button>} />
        : n ? <Workspace key={n} n={n} catalog={cat.data} step={step} setStep={(s) => setParams({ design: String(n), step: s })} /> : <Start catalog={cat.data} />}
    </Page>
  );
}
