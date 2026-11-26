import { useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { RefreshCw } from 'lucide-react';
import { useMemo, useState } from 'react';
import { post } from '@/api/client';
import { useGet } from '@/api/hooks';
import type { AIMeta, Paged, Ref, Severity } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { useOpenRef } from '@/components/Ref';
import { Chart } from '@/components/viz/LazyChart';
import { useChartTheme } from '@/components/viz/useChartTheme';
import { Badge, SeverityBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import { FilterBar } from '@/components/ui/Inputs';
import { MetricTile, Panel, SkeletonTile } from '@/components/ui/Panel';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { titleCase } from '@/lib/format';
import { useUI } from '@/store/ui';

interface Finding { id: string; rule_id: string; category: string; severity: Severity; title: string; affected: Ref[]; affected_count: number; effort: { size: string; person_days: number }; domain: string; recommendation: string }
interface Summary { summary: { total: number; by_category: Record<string, number>; by_severity: Record<string, number>; by_domain: Record<string, number> }; ai: AIMeta }

export default function AssessmentPage() {
  const qc = useQueryClient();
  const open = useOpenRef();
  const toast = useUI((s) => s.toast);
  const t = useChartTheme();
  const [filters, setFilters] = useState<Record<string, string>>({ category: 'all', severity: 'all', domain: 'all' });
  const [q, setQ] = useState('');
  const [running, setRunning] = useState(false);
  const sum = useGet<Summary>('/assessment/summary');
  const list = useGet<Paged<Finding>>('/assessment/findings', { category: filters.category === 'all' ? undefined : filters.category, severity: filters.severity === 'all' ? undefined : filters.severity, domain: filters.domain === 'all' ? undefined : filters.domain, q: q || undefined, page_size: 200 });

  const rerun = async () => {
    setRunning(true);
    try {
      await post('/assessment/run');
      await Promise.all([qc.invalidateQueries({ queryKey: ['/assessment/summary'] }), qc.invalidateQueries({ queryKey: ['/assessment/findings'] })]);
      toast({ title: 'Assessment re-run', description: 'Findings refreshed from the latest graph', tone: 'success' });
    } finally { setRunning(false); }
  };

  const cols = useMemo<ColumnDef<Finding>[]>(() => [
    { accessorKey: 'severity', header: 'Severity', size: 96, sortingFn: (a, b) => ['critical', 'high', 'medium', 'low', 'info'].indexOf(a.original.severity) - ['critical', 'high', 'medium', 'low', 'info'].indexOf(b.original.severity), cell: (c) => <SeverityBadge severity={c.getValue<Severity>()} /> },
    { accessorKey: 'title', header: 'Finding', cell: (c) => <span className="text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'category', header: 'Category', size: 170, cell: (c) => <Badge>{titleCase(c.getValue<string>())}</Badge> },
    { accessorKey: 'domain', header: 'Domain', size: 170 },
    { accessorKey: 'affected_count', header: 'Affected', size: 90, cell: (c) => <span className="num font-mono text-xs">{c.getValue<number>()}</span> },
    { id: 'effort', accessorFn: (r) => r.effort.person_days, header: 'Effort', size: 110, cell: (c) => <span className="num font-mono text-xs">{c.row.original.effort.size} · {c.getValue<number>()}d</span> },
  ], []);

  const s = sum.data?.summary;
  const catOption = s && {
    grid: { left: 8, right: 30, top: 4, bottom: 4, containLabel: true },
    xAxis: { type: 'value', show: false },
    yAxis: { type: 'category', inverse: true, data: Object.keys(s.by_category).map(titleCase), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.fg2, fontSize: 11 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'none' }, backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.fg, fontSize: 12 } },
    series: [{ type: 'bar', barWidth: 9, data: Object.values(s.by_category), itemStyle: { color: t.accent, borderRadius: 3 }, label: { show: true, position: 'right', color: t.fg2, fontSize: 11 } }],
  };
  const facet = (k: string) => Object.keys(list.data?.facets?.[k] ?? {}).sort().map((v) => ({ value: v, label: titleCase(v) }));

  return (
    <Page>
      <PageHeader title="Architecture assessment" description="Rule-based and graph-based analysis of smells, single points of failure, obsolete technology, duplication, coupling and scalability risks." actions={<Button variant="primary" loading={running} onClick={rerun} leading={<RefreshCw className="h-4 w-4" />}>Re-run assessment</Button>} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {!s ? Array.from({ length: 5 }).map((_, i) => <SkeletonTile key={i} />) : (<>
          <MetricTile label="Findings" value={s.total} />
          <MetricTile label="Critical" value={s.by_severity.critical ?? 0} sparkTone="critical" />
          <MetricTile label="High" value={s.by_severity.high ?? 0} />
          <MetricTile label="Medium" value={s.by_severity.medium ?? 0} />
          <MetricTile label="Low" value={s.by_severity.low ?? 0} />
        </>)}
      </div>
      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <AISummary ai={running ? undefined : sum.data?.ai} loading={running || sum.isLoading} title="AI assessment" thinking={['Running rule categories', 'Scoring severity', 'Ranking by blast radius']} />
        <Panel title="Findings by category">{catOption ? <Chart option={catOption} height={200} label="Findings by category" /> : null}</Panel>
      </div>
      <Panel className="mt-4" title="Findings" description={`${list.data?.total ?? 0} shown`} flush>
        <div className="p-3">
          <FilterBar search={q} onSearch={setQ} searchPlaceholder="Search findings" values={filters} onChange={(k, v) => setFilters((f) => ({ ...f, [k]: v }))}
            filters={[{ key: 'category', label: 'Category', options: facet('category') }, { key: 'severity', label: 'Severity', options: facet('severity') }, { key: 'domain', label: 'Domain', options: facet('domain') }]} />
        </div>
        <DataTable data={list.data?.items ?? []} columns={cols} loading={list.isLoading} getRowId={(r) => r.id} onRowClick={(r) => open({ type: 'finding', id: r.id })} initialSort={[{ id: 'severity', desc: false }]} maxHeight={520} ariaLabel="Findings" empty={<p className="p-6 text-sm text-fg-3">No findings match these filters.</p>} />
      </Panel>
    </Page>
  );
}
