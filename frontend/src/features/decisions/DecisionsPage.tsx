import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { Download, FileText, RotateCcw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { post, useGet } from '@/api/hooks';
import { AISummary } from '@/components/ai/AIPanel';
import { Badge, type Tone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { CodeBlock } from '@/components/ui/Code';
import { DataTable } from '@/components/ui/DataTable';
import { Field, Select, Slider, TextInput } from '@/components/ui/Inputs';
import { Modal } from '@/components/ui/Overlay';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { Panel, SkeletonBlock } from '@/components/ui/Panel';
import { EvidenceChip } from '@/components/ui/Timeline';
import { Chart } from '@/components/viz/LazyChart';
import { useChartTheme } from '@/components/viz/useChartTheme';
import { cn } from '@/lib/cn';
import { download, fmtDate, titleCase } from '@/lib/format';
import { DEFAULT_WEIGHTS, useDesign, type Nfr } from '@/store/design';
import type { AdrResult, Evaluation } from '../target/types';

interface Decision { number: string; title: string; status: string; domain: string; date: string; decision: string; source: string; document_id?: string }
const STATUS_TONE: Record<string, Tone> = { accepted: 'healthy', proposed: 'accent', superseded: 'neutral', rejected: 'critical' };

function heat(score: number): string {
  // 1..10 → low scores warm, high scores cool/green, drawn from theme tokens so it works in both themes
  const a = Math.max(0.06, Math.min(0.5, Math.abs(score - 5.5) / 9));
  return score >= 6.5 ? `rgb(var(--healthy) / ${a})` : score <= 4.5 ? `rgb(var(--high) / ${a})` : 'transparent';
}

export default function DecisionsPage() {
  const t = useChartTheme();
  const { nfr, weights, domain, set } = useDesign();
  const evalQ = useEvaluation(nfr, weights);
  const data = evalQ.data;
  const log = useGet<{ items: Decision[]; total: number; by_status: Record<string, number> }>('/decisions');
  const [title, setTitle] = useState('Target architecture for claims intake');
  const [chosen, setChosen] = useState('recommended');
  const [adr, setAdr] = useState<AdrResult | null>(null);
  const [view, setView] = useState<string | null>(null);
  const viewDoc = useGet<{ decision: Decision; markdown: string | null }>(`/decisions/${view}`, undefined, { enabled: !!view });

  const qc = useQueryClient();
  const gen = useMutation<AdrResult, Error, void>({
    mutationFn: () => post<AdrResult>('/decisions/adr', { title, domain, nfr, weights, chosen_option: chosen === 'recommended' ? undefined : chosen }),
    onSuccess: (r) => { setAdr(r); void qc.invalidateQueries({ queryKey: ['/decisions'] }); },
  });

  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  const cols = useMemo<ColumnDef<Decision>[]>(() => [
    { accessorKey: 'number', header: 'ADR', size: 90, cell: (c) => <span className="font-mono text-xs text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'title', header: 'Decision', cell: (c) => <span className="text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'domain', header: 'Domain', size: 170 },
    { accessorKey: 'status', header: 'Status', size: 110, cell: (c) => <Badge tone={STATUS_TONE[c.getValue<string>()] ?? 'neutral'} dot>{titleCase(c.getValue<string>())}</Badge> },
    { accessorKey: 'date', header: 'Date', size: 110, cell: (c) => <span className="num text-fg-2">{fmtDate(c.getValue<string>())}</span> },
  ], []);

  const contrib = data && {
    grid: { left: 8, right: 16, top: 24, bottom: 4, containLabel: true },
    legend: { top: 0, textStyle: { color: t.fg2, fontSize: 11 }, icon: 'roundRect', itemWidth: 10, itemHeight: 3 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.fg, fontSize: 12 } },
    xAxis: { type: 'value', axisLabel: { color: t.fg3, fontSize: 10 }, splitLine: { lineStyle: { color: t.lineSubtle } } },
    yAxis: { type: 'category', inverse: true, data: data.matrix.map((m) => m.name), axisLabel: { color: t.fg2, fontSize: 11 }, axisLine: { show: false }, axisTick: { show: false } },
    series: data.criteria.map((c, i) => ({ name: c.label, type: 'bar', stack: 'w', barWidth: 22, data: data.matrix.map((m) => m.contribution[c.key]), itemStyle: { color: t.series[i % t.series.length] } })),
  };

  return (
    <Page>
      <PageHeader title="Decision agent" description="Weigh the candidate architectures with a transparent decision matrix, test how robust the answer is, then record it as an Architecture Decision Record." />
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Panel title="What matters most" description={`Weights sum to ${total}. They are normalised for scoring.`} actions={<Button size="sm" variant="ghost" leading={<RotateCcw className="h-3 w-3" />} onClick={() => set({ weights: DEFAULT_WEIGHTS })}>Reset</Button>}>
          <div className="space-y-4">
            {(data?.criteria ?? Object.keys(DEFAULT_WEIGHTS).map((k) => ({ key: k, label: titleCase(k) }))).map((c) => (
              <Slider key={c.key} label={c.label} value={weights[c.key] ?? 0} min={0} max={50} step={5} onChange={(v) => set({ weights: { ...weights, [c.key]: v } })} format={(v) => `${v}`} />
            ))}
          </div>
          <p className="mt-4 text-xs text-fg-3">Requirements come from <Link to="/target-architecture" className="text-accent hover:underline">Target architecture</Link>: {nfr.availability}% availability, {nfr.throughput_tps} tps, {nfr.compliance.join(' + ') || 'no compliance regime'}.</p>
        </Panel>

        <div className="min-w-0 space-y-4">
          <AISummary ai={data?.ai} loading={evalQ.isLoading} title="Recommendation" thinking={['Scoring options', 'Applying weights', 'Testing sensitivity']} />
          <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <Panel title="Decision matrix" description="Scores out of 10; the cell shading shows strength">
              {data ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead><tr className="border-b border-line"><th scope="col" className="micro py-2 pr-3 font-medium">Criterion (weight)</th>{data.matrix.map((m) => <th key={m.option} scope="col" className="px-2 py-2 text-center font-semibold text-fg">{m.option} <span className="block text-[10px] font-normal text-fg-3">{m.name}</span></th>)}</tr></thead>
                    <tbody>
                      {data.criteria.map((c) => (
                        <tr key={c.key} className="border-b border-line-subtle">
                          <th scope="row" className="py-2 pr-3 font-medium text-fg-2">{c.label} <span className="num font-mono text-fg-3">({Math.round(((weights[c.key] ?? 0) / (total || 1)) * 100)}%)</span></th>
                          {data.matrix.map((m) => <td key={m.option} className="num px-2 py-2 text-center font-mono" style={{ background: heat(m.scores[c.key]) }}>{m.scores[c.key].toFixed(1)}</td>)}
                        </tr>
                      ))}
                      <tr><th scope="row" className="py-2.5 pr-3 font-semibold text-fg">Weighted score</th>{data.matrix.map((m) => <td key={m.option} className="px-2 py-2.5 text-center"><span className={cn('num font-mono text-sm font-semibold', m.rank === 1 ? 'text-healthy' : 'text-fg')}>{m.weighted.toFixed(2)}</span>{m.rank === 1 && <Badge tone="healthy" className="ml-1.5">Best</Badge>}</td>)}</tr>
                    </tbody>
                  </table>
                </div>
              ) : <SkeletonBlock className="h-56" />}
            </Panel>
            <Panel title="Where the score comes from">{contrib ? <Chart option={contrib} height={230} label="Weighted score contribution by criterion" /> : <SkeletonBlock className="h-56" />}</Panel>
          </div>

          <Panel title="Sensitivity" description="Does the winner change if a weight moves by ±50%?">
            {data ? (
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                {data.sensitivity.map((s) => (
                  <div key={s.criterion} className="rounded-md border border-line bg-bg p-3">
                    <p className="text-xs font-medium text-fg">{s.label}</p>
                    <p className="mt-1.5">{s.robust ? <Badge tone="healthy" dot>Robust</Badge> : <Badge tone="high" dot>Flips winner</Badge>}</p>
                    <p className="mt-1.5 text-[11px] text-fg-3">{s.flips.map((f) => `×${f.factor} → ${f.winner}`).join(' · ')}</p>
                  </div>
                ))}
              </div>
            ) : <SkeletonBlock className="h-20" />}
          </Panel>

          <Panel title="Record the decision" description="Generates a markdown ADR from the matrix, ready to commit to the architecture repository">
            <div className="grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-[minmax(0,1fr)_220px_auto] md:items-end">
              <Field label="Title"><TextInput value={title} onChange={(e) => setTitle(e.target.value)} aria-label="ADR title" /></Field>
              <Field label="Chosen option"><Select value={chosen} onValueChange={setChosen} label="Chosen option" options={[{ value: 'recommended', label: 'AI recommendation' }, ...(data?.matrix ?? []).map((m) => ({ value: m.option, label: `${m.option} · ${m.name}` }))]} /></Field>
              <Button variant="primary" loading={gen.isPending} leading={<FileText className="h-4 w-4" />} onClick={() => gen.mutate()} disabled={title.trim().length < 3}>Draft ADR</Button>
            </div>
            {gen.isError && <p role="alert" className="mt-3 text-xs text-critical">{gen.error.message}</p>}
            {adr && (
              <div className="mt-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm text-fg"><span className="font-mono">{adr.number}</span> · {adr.recommendation.name}</p>
                  <Button size="sm" leading={<Download className="h-3.5 w-3.5" />} onClick={() => download(adr.filename, adr.markdown, 'text/markdown')}>Download .md</Button>
                </div>
                <CodeBlock code={adr.markdown} language="markdown" filename={adr.filename} maxHeight={360} />
                <div className="flex flex-wrap gap-1.5">{adr.evidence.map((e) => <EvidenceChip key={e.id} label={e.label} kind={e.kind} />)}</div>
              </div>
            )}
          </Panel>

          <Panel title="Decision log" description={`${log.data?.total ?? 0} recorded decisions`} flush>
            <DataTable data={log.data?.items ?? []} columns={cols} loading={log.isLoading} getRowId={(r) => r.number} onRowClick={(r) => setView(r.number)} maxHeight={420} rowHeight={44} ariaLabel="Architecture decision log" />
          </Panel>
        </div>
      </div>

      <Modal open={!!view} onOpenChange={(o) => !o && setView(null)} title={viewDoc.data?.decision.title ?? view ?? ''} description={view ?? undefined} width={720}>
        {viewDoc.data?.markdown ? <CodeBlock code={viewDoc.data.markdown} language="markdown" maxHeight={460} /> : viewDoc.data ? <p className="text-sm text-fg-2">{viewDoc.data.decision.decision}</p> : <SkeletonBlock className="h-40" />}
      </Modal>
    </Page>
  );
}

/** Re-scores the options whenever the weights move (debounced so dragging a slider is one request, not twenty). */
function useEvaluation(nfr: Nfr, weights: Record<string, number>) {
  const [debounced, setDebounced] = useState(weights);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(weights), 250);
    return () => clearTimeout(id);
  }, [weights]);
  return useQuery<Evaluation>({
    queryKey: ['evaluate', nfr, debounced],
    queryFn: () => post<Evaluation>('/target-architecture/evaluate', { nfr, weights: debounced }),
    placeholderData: keepPreviousData,
  });
}
