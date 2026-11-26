import type { ColumnDef } from '@tanstack/react-table';
import { useMemo, useState } from 'react';
import { useGet } from '@/api/hooks';
import type { AIMeta, Severity } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { useOpenRef } from '@/components/Ref';
import { Chart } from '@/components/viz/LazyChart';
import { useChartTheme } from '@/components/viz/useChartTheme';
import { Badge, SeverityBadge } from '@/components/ui/Badge';
import { DataTable } from '@/components/ui/DataTable';
import { FilterBar } from '@/components/ui/Inputs';
import { MetricTile, Panel, SkeletonBlock, SkeletonTile } from '@/components/ui/Panel';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { titleCase } from '@/lib/format';
import type { DriftItem } from '@/features/inspector/DriftInspector';

type Row = Omit<DriftItem, 'approved_iac' | 'deployed_config'>;
interface DriftData { items: Row[]; total: number; summary: { total: number; open: number; critical: number; by_domain: Record<string, number>; by_status: Record<string, number> }; trend: { labels: string[]; open: number[]; detected: number[] }; ai: AIMeta }

export default function DriftPage() {
  const t = useChartTheme();
  const open = useOpenRef();
  const [filters, setFilters] = useState<Record<string, string>>({ status: 'all', severity: 'all', domain: 'all' });
  const { data, isLoading } = useGet<DriftData>('/drift', { status: filters.status === 'all' ? undefined : filters.status, severity: filters.severity === 'all' ? undefined : filters.severity, domain: filters.domain === 'all' ? undefined : filters.domain });
  const all = useGet<DriftData>('/drift');

  const cols = useMemo<ColumnDef<Row>[]>(() => [
    { accessorKey: 'severity', header: 'Severity', size: 96, cell: (c) => <SeverityBadge severity={c.getValue<Severity>()} /> },
    { id: 'resource', header: 'Resource', accessorFn: (r) => r.resource.name, size: 200, cell: (c) => <span className="font-mono text-xs text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'summary', header: 'What drifted', cell: (c) => <span className="text-fg-2">{c.getValue<string>()}</span> },
    { accessorKey: 'standard_id', header: 'Standard', size: 120, cell: (c) => <Badge mono>{c.getValue<string>()}</Badge> },
    { accessorKey: 'domain', header: 'Domain', size: 150 },
    { accessorKey: 'status', header: 'Status', size: 130, cell: (c) => <Badge tone={c.getValue<string>() === 'open' ? 'critical' : 'accent'} dot>{titleCase(c.getValue<string>())}</Badge> },
  ], []);

  const trend = all.data?.trend;
  const trendOption = trend && {
    grid: { left: 8, right: 12, top: 24, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis', backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.fg, fontSize: 12 } },
    legend: { top: 0, textStyle: { color: t.fg2, fontSize: 11 }, icon: 'roundRect', itemWidth: 10, itemHeight: 3 },
    xAxis: { type: 'category', data: trend.labels, axisLabel: { color: t.fg3, fontSize: 10 }, axisLine: { lineStyle: { color: t.line } } },
    yAxis: { type: 'value', axisLabel: { color: t.fg3, fontSize: 10 }, splitLine: { lineStyle: { color: t.lineSubtle } } },
    series: [{ name: 'Open drift', type: 'line', data: trend.open, smooth: true, symbol: 'none', lineStyle: { width: 2.5, color: t.critical }, areaStyle: { color: t.alpha('critical', 0.1) } }, { name: 'Newly detected', type: 'bar', data: trend.detected, barWidth: 8, itemStyle: { color: t.alpha('accent', 0.6), borderRadius: 2 } }],
  };
  const domains = all.data ? Object.entries(all.data.summary.by_domain).sort((a, b) => b[1] - a[1]) : [];
  const domOption = domains.length ? {
    grid: { left: 8, right: 24, top: 4, bottom: 4, containLabel: true }, xAxis: { type: 'value', show: false },
    yAxis: { type: 'category', inverse: true, data: domains.map((d) => d[0]), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.fg2, fontSize: 11 } },
    series: [{ type: 'bar', barWidth: 9, data: domains.map((d) => d[1]), itemStyle: { color: t.accent, borderRadius: 3 }, label: { show: true, position: 'right', color: t.fg2, fontSize: 11 } }],
  } : null;
  const s = all.data?.summary;

  return (
    <Page>
      <PageHeader title="Drift detection" description="Compares the approved design (infrastructure code) with what is actually deployed, and tells you which standard each deviation breaks." />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {!s ? Array.from({ length: 4 }).map((_, i) => <SkeletonTile key={i} />) : (<>
          <MetricTile label="Drifted resources" value={s.total} />
          <MetricTile label="Open" value={s.open} sparkTone="critical" />
          <MetricTile label="Critical" value={s.critical} />
          <MetricTile label="Ticketed or excepted" value={s.total - s.open} />
        </>)}
      </div>
      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <AISummary ai={all.data?.ai} loading={all.isLoading} title="AI drift summary" thinking={['Diffing approved vs deployed', 'Mapping deviations to standards']} />
        <Panel title="Drift over 12 weeks">{trendOption ? <Chart option={trendOption} height={210} label="Drift trend" /> : <SkeletonBlock className="h-48" />}</Panel>
        <Panel title="By domain">{domOption ? <Chart option={domOption} height={210} label="Drift by domain" /> : <SkeletonBlock className="h-48" />}</Panel>
      </div>
      <Panel className="mt-4" title="Drift register" description={`${data?.total ?? 0} items`} flush>
        <div className="p-3">
          <FilterBar values={filters} onChange={(k, v) => setFilters((f) => ({ ...f, [k]: v }))}
            filters={[{ key: 'status', label: 'Status', options: ['open', 'ticket_raised', 'exception_granted', 'remediating'].map((v) => ({ value: v, label: titleCase(v) })) }, { key: 'severity', label: 'Severity', options: ['critical', 'high', 'medium', 'low'].map((v) => ({ value: v, label: titleCase(v) })) }, { key: 'domain', label: 'Domain', options: domains.map((d) => ({ value: d[0], label: d[0] })) }]} />
        </div>
        <DataTable data={data?.items ?? []} columns={cols} loading={isLoading} getRowId={(r) => r.id} onRowClick={(r) => open({ type: 'drift', id: r.id })} maxHeight={500} ariaLabel="Drift register" rowHeight={44} />
      </Panel>
    </Page>
  );
}
