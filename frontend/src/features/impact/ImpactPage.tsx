import type { ColumnDef } from '@tanstack/react-table';
import { Suspense, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import type { AIMeta, Asset, Paged } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { useOpenRef } from '@/components/Ref';
import { LazyFlow } from '@/components/viz/LazyChart';
import type { FlowEdgeIn, FlowNodeIn } from '@/components/viz/FlowGraph';
import { Badge, severityTone } from '@/components/ui/Badge';
import { DataTable } from '@/components/ui/DataTable';
import { SearchInput, SegmentedControl, Slider, Tabs } from '@/components/ui/Inputs';
import { MetricTile, Panel, ScoreRing, Skeleton, SkeletonTile } from '@/components/ui/Panel';
import { Page, PageHeader } from '@/components/ui/PageHeader';

interface ImpactData {
  asset: Asset;
  headline: string;
  summary: { direct: number; indirect: number; workflows: number; databases: number; teams: number; critical_apps: number; risk_score: number; risk_rating: string };
  nodes: { id: string; name: string; type: string; hop: number; criticality?: string; domain?: string }[];
  edges: { source: string; target: string }[];
  applications: (Asset & { hop: number })[];
  workflows: { id: string; name: string; domain: string; volume_per_day: number }[];
  teams: { team: string; owner: string; direct: number; indirect: number }[];
  capabilities: { id: string; name: string }[];
  ai: AIMeta;
}

const QUICK = [
  { id: 'API-0002', label: 'Customer API v2' },
  { id: 'DB-001', label: 'Policy Master DB' },
  { id: 'APP-056', label: 'MuleSoft Anypoint' },
  { id: 'APP-057', label: 'Kafka Event Platform' },
];
const CHANGES = [
  { value: 'breaking_change', label: 'Breaking change' },
  { value: 'outage', label: 'Outage' },
  { value: 'retirement', label: 'Retirement' },
] as const;

export default function ImpactPage() {
  const [sp, setSp] = useSearchParams();
  const assetId = sp.get('asset') ?? 'API-0002';
  const [change, setChange] = useState<(typeof CHANGES)[number]['value']>('breaking_change');
  const [hops, setHops] = useState(3);
  const [tab, setTab] = useState('apps');
  const [q, setQ] = useState('');
  const open = useOpenRef();
  const found = useGet<Paged<Asset>>('/assets', { q, type: 'application,api,database', page_size: 6 }, { enabled: q.length >= 2 });
  const { data, isLoading, isFetching } = useGet<ImpactData>(`/impact/${assetId}`, { change_type: change, max_hops: hops }, { placeholderData: (p) => p });
  const pick = (id: string) => { setSp({ asset: id }, { replace: true }); setQ(''); };

  const { flowNodes, flowEdges } = useMemo(() => {
    if (!data) return { flowNodes: [] as FlowNodeIn[], flowEdges: [] as FlowEdgeIn[] };
    const rank: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
    const hop: Record<string, number> = Object.fromEntries(data.nodes.map((n) => [n.id, n.hop]));
    const direct = data.nodes.filter((n) => n.hop === 1 && n.type === 'application');
    const second = data.nodes.filter((n) => n.hop === 2 && n.type === 'application').sort((a, b) => (rank[a.criticality ?? 'low'] ?? 3) - (rank[b.criticality ?? 'low'] ?? 3)).slice(0, 14);
    const keep = new Map([[assetId, data.nodes.find((n) => n.id === assetId)], ...direct.map((n) => [n.id, n] as const), ...second.map((n) => [n.id, n] as const)]);
    const parent = new Map<string, string>();
    for (const e of data.edges) if (keep.has(e.source) && keep.has(e.target) && hop[e.target] === hop[e.source] + 1 && !parent.has(e.target)) parent.set(e.target, e.source);
    const nodes = [...keep.values()].filter((n): n is NonNullable<typeof n> => !!n).filter((n) => n.id === assetId || parent.has(n.id));
    return {
      flowNodes: nodes.map((n) => ({ id: n.id, name: n.name, type: n.type, criticality: n.criticality, focus: n.id === assetId, sub: n.id === assetId ? 'changed asset' : n.hop === 1 ? 'direct' : 'indirect' })),
      flowEdges: [...parent.entries()].map(([t, s]) => ({ source: s, target: t })),
    };
  }, [data, assetId]);

  const cols = useMemo<ColumnDef<Asset & { hop: number }>[]>(() => [
    { accessorKey: 'name', header: 'Application', cell: (c) => <span className="text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'hop', header: 'Reach', size: 100, cell: (c) => <Badge tone={c.getValue<number>() === 1 ? 'critical' : 'medium'}>{c.getValue<number>() === 1 ? 'Direct' : `${c.getValue<number>()} hops`}</Badge> },
    { accessorKey: 'domain', header: 'Domain', size: 170 },
    { accessorKey: 'criticality', header: 'Criticality', size: 100, cell: (c) => <Badge tone={severityTone(c.getValue<string>())}>{c.getValue<string>()}</Badge> },
    { id: 'owner', header: 'Owning team', accessorFn: (r) => r.owner?.team ?? '', size: 180 },
  ], []);

  const s = data?.summary;
  return (
    <Page>
      <PageHeader title="Change impact analysis" description="Pick an application, API or data store and a type of change to see everything that would be affected." />
      <Panel>
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-[minmax(0,1.2fr)_auto_minmax(0,1fr)] md:items-end">
          <div className="relative">
            <p className="micro mb-1.5">Asset</p>
            <SearchInput value={q} onChange={setQ} placeholder={data?.asset.name ?? 'Search an asset'} />
            {q.length >= 2 && found.data && (
              <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-line bg-overlay shadow-lg">
                {found.data.items.map((a) => <li key={a.id}><button type="button" className="flex w-full items-center justify-between px-3 py-1.5 text-left text-xs hover:bg-raised" onClick={() => pick(a.id)}><span className="truncate text-fg">{a.name}</span><Badge>{a.type}</Badge></button></li>)}
              </ul>
            )}
            <div className="mt-2 flex flex-wrap gap-1.5">{QUICK.map((qk) => <button key={qk.id} type="button" onClick={() => pick(qk.id)} className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${assetId === qk.id ? 'border-accent/50 bg-accent/10 text-accent' : 'border-line text-fg-2 hover:bg-raised'}`}>{qk.label}</button>)}</div>
          </div>
          <div><p className="micro mb-1.5">Change type</p><SegmentedControl label="Change type" value={change} onChange={setChange} options={CHANGES.map((c) => ({ value: c.value, label: c.label }))} /></div>
          <Slider label="Traversal depth" value={hops} onChange={setHops} min={1} max={5} format={(v) => `${v} hops`} />
        </div>
      </Panel>

      <div className="mt-4 rounded-lg border border-line bg-surface p-5" aria-live="polite">
        {isLoading || !data ? <Skeleton className="h-8 w-2/3" /> : <h2 className="text-xl font-semibold text-fg">{data.headline}</h2>}
        <p className="mt-1 text-sm text-fg-3">{isFetching ? 'Recalculating…' : data ? `${data.asset.name}${data.asset.domain ? ' · ' + data.asset.domain : ''}` : ''}</p>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-6">
        {!s ? Array.from({ length: 6 }).map((_, i) => <SkeletonTile key={i} />) : (<>
          <MetricTile label="Direct applications" value={s.direct} sparkTone="critical" />
          <MetricTile label="Indirect applications" value={s.indirect} />
          <MetricTile label="Workflows" value={s.workflows} />
          <MetricTile label="Teams" value={s.teams} />
          <MetricTile label="Critical apps" value={s.critical_apps} />
          <div className="hairline flex items-center justify-between gap-2 rounded-lg border border-line bg-surface p-3"><div><p className="micro">Blast radius</p><p className="mt-1 text-xs capitalize text-fg-2">{s.risk_rating}</p></div><ScoreRing score={s.risk_score} size={64} invert /></div>
        </>)}
      </div>

      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Panel title="Impact map" description="The changed asset, then the applications that break: direct dependents first, then the most critical indirect ones">
          {data ? <Suspense fallback={<Skeleton className="h-[500px]" />}><LazyFlow nodes={flowNodes} edges={flowEdges} height={500} label="Impact map" onNodeClick={(id) => open({ type: 'application', id })} /></Suspense> : <Skeleton className="h-[500px]" />}
        </Panel>
        <AISummary ai={data?.ai} loading={isLoading} title="AI impact summary" thinking={['Building impact graph', 'Traversing dependencies', 'Scoring blast radius']} />
      </div>

      <Tabs className="mt-5" value={tab} onValueChange={setTab} items={[
        { value: 'apps', label: 'Applications', count: data?.applications.length, content: <div className="pt-3"><DataTable data={data?.applications ?? []} columns={cols} getRowId={(r) => r.id} onRowClick={(r) => open({ type: 'application', id: r.id })} maxHeight={420} ariaLabel="Affected applications" initialSort={[{ id: 'hop', desc: false }]} /></div> },
        { value: 'workflows', label: 'Workflows', count: data?.workflows.length, content: <ul className="mt-3 divide-y divide-line-subtle rounded-lg border border-line bg-surface">{data?.workflows.map((w) => <li key={w.id} className="flex items-center justify-between px-4 py-2.5 text-sm"><span className="text-fg">{w.name}</span><span className="text-xs text-fg-3">{w.domain} · <span className="num font-mono">{w.volume_per_day.toLocaleString()}</span>/day</span></li>)}</ul> },
        { value: 'teams', label: 'Teams', count: data?.teams.length, content: <ul className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">{data?.teams.map((t) => <li key={t.team} className="rounded-lg border border-line bg-surface p-3 text-sm"><p className="font-medium text-fg">{t.team}</p><p className="text-xs text-fg-3">{t.owner}</p><p className="mt-2 text-xs text-fg-2"><span className="num font-mono">{t.direct}</span> direct · <span className="num font-mono">{t.indirect}</span> indirect</p></li>)}</ul> },
        { value: 'caps', label: 'Capabilities', count: data?.capabilities.length, content: <div className="mt-3 flex flex-wrap gap-2">{data?.capabilities.map((c) => <Badge key={c.id} tone="accent">{c.name}</Badge>)}</div> },
      ]} />
    </Page>
  );
}
