import type { ColumnDef } from '@tanstack/react-table';
import { useMemo, useState } from 'react';
import { useGet } from '@/api/hooks';
import type { AIMeta } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { useOpenRef } from '@/components/Ref';
import { Chart } from '@/components/viz/LazyChart';
import { useChartTheme } from '@/components/viz/useChartTheme';
import { Badge, severityTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import { Select } from '@/components/ui/Inputs';
import { Panel, ScoreRing, SkeletonBlock } from '@/components/ui/Panel';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { fmtMoneyK, titleCase } from '@/lib/format';

interface Heat { domains: string[]; dimensions: string[]; cells: { domain: string; dimension: string; score: number; apps: number }[]; domain_overall: Record<string, number>; weights: Record<string, number> }
interface Contributor { app_id: string; name: string; domain: string; criticality: string; scores: Record<string, number>; overall: number; drivers: string[]; effort_pd: number; remediation_cost_k: number }
interface Trends { months: string[]; series: Record<string, number[]>; overall: number[] }

export default function DebtPage() {
  const t = useChartTheme();
  const open = useOpenRef();
  const [sel, setSel] = useState<{ domain?: string; dimension?: string }>({});
  const [trendDomain, setTrendDomain] = useState('all');
  const heat = useGet<Heat>('/debt/heatmap');
  const summary = useGet<{ overall: number; ai: AIMeta }>('/debt/summary');
  const contrib = useGet<{ items: Contributor[] }>('/debt/contributors', { domain: sel.domain, dimension: sel.dimension, limit: 20 });
  const trends = useGet<Trends>('/debt/trends', { domain: trendDomain === 'all' ? undefined : trendDomain });

  const heatOption = heat.data && {
    grid: { left: 8, right: 16, top: 8, bottom: 40, containLabel: true },
    tooltip: { position: 'top', backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.fg, fontSize: 12 }, formatter: (p: { data: [number, number, number] }) => `${heat.data!.domains[p.data[1]]}<br/>${titleCase(heat.data!.dimensions[p.data[0]])}: <b>${p.data[2]}</b>` },
    xAxis: { type: 'category', data: heat.data.dimensions.map(titleCase), axisLabel: { color: t.fg2, fontSize: 11, interval: 0 }, axisLine: { show: false }, axisTick: { show: false }, splitArea: { show: false } },
    yAxis: { type: 'category', inverse: true, data: heat.data.domains, axisLabel: { color: t.fg2, fontSize: 11 }, axisLine: { show: false }, axisTick: { show: false } },
    visualMap: { min: 0, max: 60, calculable: false, orient: 'horizontal', left: 'center', bottom: 0, itemWidth: 10, itemHeight: 120, textStyle: { color: t.fg3, fontSize: 10 }, inRange: { color: [t.alpha('accent', 0.12), t.accent, t.high, t.critical] } },
    series: [{ type: 'heatmap', data: heat.data.cells.map((c) => [heat.data!.dimensions.indexOf(c.dimension), heat.data!.domains.indexOf(c.domain), c.score]), label: { show: true, color: t.fg, fontSize: 11 }, itemStyle: { borderColor: t.surface, borderWidth: 3, borderRadius: 4 }, emphasis: { itemStyle: { borderColor: t.fg } } }],
  };
  const trendOption = trends.data && {
    grid: { left: 8, right: 16, top: 28, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis', backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.fg, fontSize: 12 } },
    legend: { top: 0, textStyle: { color: t.fg2, fontSize: 11 }, icon: 'roundRect', itemWidth: 10, itemHeight: 3 },
    xAxis: { type: 'category', data: trends.data.months, axisLabel: { color: t.fg3, fontSize: 10 }, axisLine: { lineStyle: { color: t.line } } },
    yAxis: { type: 'value', axisLabel: { color: t.fg3, fontSize: 10 }, splitLine: { lineStyle: { color: t.lineSubtle } } },
    series: [{ name: 'Overall', type: 'line', data: trends.data.overall, smooth: true, symbol: 'none', lineStyle: { width: 2.5, color: t.accent }, areaStyle: { color: t.alpha('accent', 0.1) } },
      ...Object.entries(trends.data.series).slice(0, 3).map(([k, v], i) => ({ name: titleCase(k), type: 'line', data: v, smooth: true, symbol: 'none', lineStyle: { width: 1.3, color: t.series[i + 2], type: 'dashed' as const } }))],
  };

  const cols = useMemo<ColumnDef<Contributor>[]>(() => [
    { accessorKey: 'name', header: 'Application', cell: (c) => <span className="text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'domain', header: 'Domain', size: 160 },
    { accessorKey: 'criticality', header: 'Criticality', size: 100, cell: (c) => <Badge tone={severityTone(c.getValue<string>())}>{c.getValue<string>()}</Badge> },
    { accessorKey: 'overall', header: 'Debt', size: 70, cell: (c) => <span className="num font-mono text-sm font-semibold text-fg">{c.getValue<number>()}</span> },
    { id: 'drivers', header: 'Main drivers', accessorFn: (r) => r.drivers.join('; '), cell: (c) => <span className="text-xs text-fg-2">{c.getValue<string>()}</span> },
    { accessorKey: 'remediation_cost_k', header: 'Fix cost', size: 90, cell: (c) => <span className="num font-mono text-xs">{fmtMoneyK(c.getValue<number>())}</span> },
  ], []);

  return (
    <Page>
      <PageHeader title="Technical debt radar" description="Debt scored across five dimensions and weighted by business criticality. Select a heatmap cell to see which applications drive it." />
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
        <Panel title="Estate debt" className="items-center text-center">
          <div className="flex flex-col items-center gap-3">
            <ScoreRing score={summary.data?.overall ?? 0} size={120} invert />
            <p className="text-xs text-fg-3">out of 100</p>
            <div className="w-full space-y-1 text-left text-xs">{heat.data && Object.entries(heat.data.weights).map(([k, w]) => <div key={k} className="flex justify-between text-fg-2"><span>{titleCase(k)}</span><span className="num font-mono text-fg-3">{Math.round(w * 100)}%</span></div>)}</div>
          </div>
        </Panel>
        <AISummary ai={summary.data?.ai} loading={summary.isLoading} title="Where the debt is" thinking={['Scoring five dimensions', 'Weighting by criticality', 'Building the heatmap']} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="Domain × dimension heatmap" description="Click a cell to filter contributors" actions={(sel.domain || sel.dimension) ? <Button size="sm" variant="ghost" onClick={() => setSel({})}>Clear</Button> : undefined}>
          {heatOption ? <Chart option={heatOption} height={380} label="Technical debt heatmap by domain and dimension" onClick={(p) => { const d = p.data as [number, number, number]; if (heat.data) setSel({ dimension: heat.data.dimensions[d[0]], domain: heat.data.domains[d[1]] }); }} /> : <SkeletonBlock className="h-80" />}
        </Panel>
        <Panel title="12-month trend" actions={<Select label="Trend domain" value={trendDomain} onValueChange={setTrendDomain} className="w-48" options={[{ value: 'all', label: 'Whole estate' }, ...(heat.data?.domains.map((d) => ({ value: d, label: d })) ?? [])]} />}>
          {trendOption ? <Chart option={trendOption} height={380} label="Technical debt trend" /> : <SkeletonBlock className="h-80" />}
        </Panel>
      </div>
      <Panel className="mt-4" title="Top contributors" description={sel.domain ? `${sel.domain}${sel.dimension ? ` · ${titleCase(sel.dimension)}` : ''}` : 'Whole estate'} flush>
        <DataTable data={contrib.data?.items ?? []} columns={cols} loading={contrib.isLoading} getRowId={(r) => r.app_id} onRowClick={(r) => open({ type: 'application', id: r.app_id })} maxHeight={480} ariaLabel="Debt contributors" rowHeight={44} />
      </Panel>
    </Page>
  );
}
