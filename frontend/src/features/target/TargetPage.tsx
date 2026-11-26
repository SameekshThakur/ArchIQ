import { useMutation } from '@tanstack/react-query';
import { ArrowRight, Sparkles, Wand2 } from 'lucide-react';
import { Suspense, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { post, useGet } from '@/api/hooks';
import { AISummary } from '@/components/ai/AIPanel';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Field, Select, SegmentedControl, Slider, TextArea } from '@/components/ui/Inputs';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { EmptyState, Panel, ProgressBar, Skeleton, SkeletonBlock } from '@/components/ui/Panel';
import { EvidenceChip } from '@/components/ui/Timeline';
import { Chart } from '@/components/viz/LazyChart';
import { LazyMermaid } from '@/components/viz/LazyChart';
import { useChartTheme } from '@/components/viz/useChartTheme';
import { cn } from '@/lib/cn';
import { fmtMoneyK } from '@/lib/format';
import { DEFAULT_NFR, useDesign, type Nfr } from '@/store/design';
import type { OptionsResult } from './types';

const COMPLIANCE = ['GDPR', 'SOX', 'Solvency II', 'PCI-DSS'];
const DOMAINS = ['Claims', 'Policy Admin', 'Underwriting', 'Customer & Distribution', 'Billing & Finance', 'Data & Analytics', 'Integration & Platform'];
const PRESET_LABEL: Record<string, string> = { 'claims-peak': 'Claims peak load', 'quick-win': 'Quick win', 'regulated-core': 'Regulated core' };

export default function TargetPage() {
  const t = useChartTheme();
  const { goals, domain, nfr, set } = useDesign();
  const presets = useGet<{ presets: Record<string, Nfr> }>('/target-architecture/presets');
  const [active, setActive] = useState('A');
  const gen = useMutation<OptionsResult, Error, void>({ mutationFn: () => post<OptionsResult>('/target-architecture/options', { goals, domain, nfr }) });
  const { mutate } = gen;
  useEffect(() => { mutate(); }, [mutate]);
  const recommended = gen.data?.evaluation.recommendation.option;
  useEffect(() => { if (recommended) setActive(recommended); }, [recommended]);

  const res = gen.data;
  const rec = res?.evaluation.recommendation.option;
  const patch = (p: Partial<Nfr>) => set({ nfr: { ...nfr, ...p } });
  const option = res?.options.find((o) => o.id === active) ?? res?.options[0];

  const radar = res && {
    legend: { bottom: 0, textStyle: { color: t.fg2, fontSize: 11 }, icon: 'roundRect', itemWidth: 10, itemHeight: 3 },
    tooltip: { backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.fg, fontSize: 12 } },
    radar: { radius: '56%', center: ['50%', '46%'], indicator: res.evaluation.criteria.map((c) => ({ name: c.label.replace(' efficiency', ''), max: 10 })), axisName: { color: t.fg2, fontSize: 11 }, splitLine: { lineStyle: { color: t.line } }, splitArea: { show: false }, axisLine: { lineStyle: { color: t.line } } },
    series: [{ type: 'radar', data: res.evaluation.radar.map((r, i) => ({ name: r.name, value: r.values, lineStyle: { width: r.option === rec ? 2.5 : 1.5, color: t.series[i % t.series.length] }, itemStyle: { color: t.series[i % t.series.length] }, areaStyle: { color: t.alpha('accent', r.option === rec ? 0.14 : 0) }, symbol: 'none' })) }],
  };

  return (
    <Page>
      <PageHeader
        title="Target architecture"
        description="Describe the outcome and the non-functional requirements; the AI proposes candidate architectures, scores them against your criteria and explains the trade-offs."
        actions={<Link to="/decisions" className="inline-flex h-8 items-center gap-2 rounded border border-line bg-raised px-3 text-sm font-medium text-fg hover:bg-overlay">Weigh the options <ArrowRight className="h-3.5 w-3.5" aria-hidden /></Link>}
      />
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Panel title="Requirements" description="Changes here feed the Decision agent too" className="lg:sticky lg:top-4">
          <div className="space-y-4">
            <Field label="Goal">
              <TextArea rows={3} value={goals} onChange={(e) => set({ goals: e.target.value })} aria-label="Architecture goal" />
            </Field>
            <Field label="Domain">
              <Select value={domain} onValueChange={(v) => set({ domain: v })} options={DOMAINS.map((d) => ({ value: d, label: d }))} label="Domain" />
            </Field>
            <Field label="Start from a preset">
              <SegmentedControl size="sm" label="Preset" value={'' as string} onChange={(v) => presets.data && set({ nfr: presets.data.presets[v] })} options={Object.keys(presets.data?.presets ?? PRESET_LABEL).map((k) => ({ value: k, label: PRESET_LABEL[k] ?? k }))} />
            </Field>
            <Field label="Availability">
              <SegmentedControl size="sm" label="Availability" value={String(nfr.availability)} onChange={(v) => patch({ availability: Number(v) })} options={['99.5', '99.9', '99.95', '99.99'].map((v) => ({ value: v, label: `${v}%` }))} />
            </Field>
            <Slider label="Throughput" min={50} max={2000} step={50} value={nfr.throughput_tps} onChange={(v) => patch({ throughput_tps: v })} format={(v) => `${v} tps`} />
            <Slider label="p95 latency" min={100} max={3000} step={100} value={nfr.latency_ms} onChange={(v) => patch({ latency_ms: v })} format={(v) => `${v} ms`} />
            <Slider label="RTO" min={1} max={24} step={1} value={nfr.rto_hours} onChange={(v) => patch({ rto_hours: v })} format={(v) => `${v} h`} />
            <Slider label="RPO" min={1} max={120} step={1} value={nfr.rpo_minutes} onChange={(v) => patch({ rpo_minutes: v })} format={(v) => `${v} min`} />
            <Slider label="Budget" min={200} max={6000} step={100} value={nfr.budget_k} onChange={(v) => patch({ budget_k: v })} format={fmtMoneyK} />
            <Slider label="Timeline" min={3} max={24} step={1} value={nfr.timeline_months} onChange={(v) => patch({ timeline_months: v })} format={(v) => `${v} months`} />
            <Field label="Compliance">
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Compliance regimes">
                {COMPLIANCE.map((c) => {
                  const on = nfr.compliance.includes(c);
                  return (
                    <button key={c} type="button" aria-pressed={on} onClick={() => patch({ compliance: on ? nfr.compliance.filter((x) => x !== c) : [...nfr.compliance, c] })}
                      className={cn('rounded-full border px-2.5 py-1 text-xs transition-colors', on ? 'border-accent/50 bg-accent/15 text-fg' : 'border-line text-fg-3 hover:text-fg')}>{c}</button>
                  );
                })}
              </div>
            </Field>
            <div className="flex gap-2 pt-1">
              <Button variant="primary" className="flex-1" loading={gen.isPending} leading={<Wand2 className="h-4 w-4" />} onClick={() => mutate()}>Generate options</Button>
              <Button variant="ghost" onClick={() => set({ nfr: DEFAULT_NFR })}>Reset</Button>
            </div>
          </div>
        </Panel>

        <div className="min-w-0 space-y-4">
          {gen.isError && <EmptyState icon={<Sparkles className="h-4 w-4" />} title="Could not generate options" description={gen.error.message} action={<Button onClick={() => mutate()}>Try again</Button>} />}
          <AISummary ai={res?.ai} loading={gen.isPending} title="AI recommendation" thinking={['Generating candidate architectures', 'Scoring against requirements', 'Running sensitivity analysis']}>
            {res && (
              <div className="mt-2 space-y-1.5">
                {res.evaluation.recommendation.reasons.map((r, i) => <p key={i} className="flex gap-2 text-sm text-fg-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" aria-hidden />{r}</p>)}
              </div>
            )}
          </AISummary>

          {res ? (
            <>
              <div className="grid gap-3 md:grid-cols-3" role="tablist" aria-label="Candidate architectures">
                {res.options.map((o) => (
                  <button key={o.id} role="tab" aria-selected={o.id === option?.id} onClick={() => setActive(o.id)}
                    className={cn('hairline rounded-lg border bg-surface p-4 text-left transition-colors', o.id === option?.id ? 'border-accent/60 ring-1 ring-accent/30' : 'border-line hover:border-fg-3/40')}>
                    <div className="flex items-start justify-between gap-2">
                      <span className="flex h-6 w-6 items-center justify-center rounded bg-raised font-mono text-xs text-fg-2">{o.id}</span>
                      {o.id === rec && <Badge tone="healthy" dot>Recommended</Badge>}
                    </div>
                    <p className="mt-2 text-sm font-semibold text-fg">{o.name}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-fg-3">{o.summary}</p>
                    <div className="mt-3 flex items-end justify-between gap-3">
                      <div className="min-w-0 flex-1"><p className="micro mb-1">Fit {o.fit_score}</p><ProgressBar value={o.fit_score} tone={o.fit_score >= 70 ? 'healthy' : 'accent'} label={`${o.name} fit score`} /></div>
                      <div className="text-right text-[11px] text-fg-3"><span className="num font-mono text-fg-2">{fmtMoneyK(o.estimated_cost_k)}</span><br />{o.estimated_months} months</div>
                    </div>
                  </button>
                ))}
              </div>

              {option && (
                <Panel title={`${option.id} · ${option.name}`} description="Generated reference diagram" bodyClassName="space-y-4">
                  <div className="overflow-x-auto rounded-md border border-line bg-bg p-3">
                    <Suspense fallback={<SkeletonBlock className="h-64" />}><LazyMermaid code={option.diagram} label={`${option.name} diagram`} className="mx-auto min-w-[560px] max-w-[900px]" /></Suspense>
                  </div>
                  <div className="grid gap-4 md:grid-cols-3">
                    <div><p className="micro mb-1.5">Strengths</p><ul className="space-y-1.5 text-xs text-fg-2">{option.pros.map((p) => <li key={p} className="flex gap-2"><span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-healthy" aria-hidden />{p}</li>)}</ul></div>
                    <div><p className="micro mb-1.5">Trade-offs</p><ul className="space-y-1.5 text-xs text-fg-2">{option.cons.map((p) => <li key={p} className="flex gap-2"><span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-high" aria-hidden />{p}</li>)}</ul></div>
                    <div>
                      <p className="micro mb-1.5">Components</p>
                      <ul className="divide-y divide-line-subtle rounded border border-line text-xs">
                        {option.components.map((c) => <li key={c.name} className="px-3 py-1.5"><span className="block font-medium text-fg">{c.name}</span><span className="block text-fg-3">{c.role}</span></li>)}
                      </ul>
                    </div>
                  </div>
                </Panel>
              )}
              <div className="grid items-start gap-4 lg:grid-cols-2">
                <Panel title="Scored against your criteria" description="Higher is better on every axis">{radar ? <Chart option={radar} height={300} label="Option comparison radar chart" /> : <Skeleton className="h-72" />}</Panel>
                <Panel title="Existing systems in scope" description="Applications this change touches">
                  <div className="flex flex-wrap gap-1.5">{res.systems.map((s) => <Badge key={s}>{s}</Badge>)}</div>
                  {res.evaluation.evidence.length > 0 && (<><p className="micro mb-1.5 mt-4">Grounded in</p><div className="flex flex-wrap gap-1.5">{res.evaluation.evidence.map((e) => <EvidenceChip key={e.id} label={e.label} kind={e.kind} />)}</div></>)}
                </Panel>
              </div>
            </>
          ) : gen.isPending ? <SkeletonBlock className="h-80" /> : null}
        </div>
      </div>
    </Page>
  );
}
