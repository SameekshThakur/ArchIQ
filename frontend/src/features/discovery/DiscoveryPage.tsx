import { useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { CheckCircle2, FileUp, Loader2, ScanSearch } from 'lucide-react';
import { useMemo, useState } from 'react';
import { post, streamSSE } from '@/api/client';
import { useGet } from '@/api/hooks';
import type { Paged } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { RefLink } from '@/components/Ref';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import { FilterBar } from '@/components/ui/Inputs';
import { MetricTile, Panel, Skeleton, SkeletonTile } from '@/components/ui/Panel';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { useOpenRef } from '@/components/Ref';
import { fmtNum, titleCase } from '@/lib/format';
import { cn } from '@/lib/cn';
import { useUI } from '@/store/ui';
import type { AIMeta } from '@/api/types';
import { Modal } from '@/components/ui/Overlay';
import { ImportModal, ImportResult, type ImportReport } from './ImportInventory';

interface Source {
  id: string;
  name: string;
  kind: string;
  detail: string;
  found: number;
  new: number;
}
interface Results {
  total: number;
  by_type: Record<string, number>;
  shadow: number;
  drifted: number;
  duplicates: number;
  new: number;
  shadow_assets: DAsset[];
}
interface DAsset {
  id: string;
  type: string;
  name: string;
  domain: string;
  source: string;
  status: 'known' | 'shadow' | 'drifted';
  confidence: number;
}
type ScanState = Record<string, { status: 'pending' | 'scanning' | 'done'; found?: number; new?: number }>;

export default function DiscoveryPage() {
  const qc = useQueryClient();
  const toast = useUI((s) => s.toast);
  const open = useOpenRef();
  const sources = useGet<{ sources: Source[] }>('/discovery/sources');
  const results = useGet<Results>('/discovery/results');
  const [scan, setScan] = useState<ScanState>({});
  const [running, setRunning] = useState(false);
  const [ai, setAi] = useState<AIMeta | undefined>();
  const [importOpen, setImportOpen] = useState(false);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [dismissed, setDismissed] = useState(false);
  // the most recent import is kept on the server, so it is still here after a refresh or restart
  const [reportOpen, setReportOpen] = useState(false);
  const imports = useGet<{ items: { id: number; filename: string; matched: number; conflicts: number; new: number; missing: number }[] }>('/discovery/imports');
  const latestSummary = imports.data?.items[0];
  // the full report is only fetched when someone asks for it; the page itself only shows a one-line banner
  const latest = useGet<ImportReport>(`/discovery/imports/${latestSummary?.id}`, undefined, { enabled: !!latestSummary && !report && reportOpen });
  const shown = report ?? latest.data ?? null;
  const banner = dismissed ? null : report ? { filename: report.filename, matched: report.matched, conflicts: report.conflicts, new: report.new, missing: report.missing.length } : latestSummary ?? null;
  const [filters, setFilters] = useState<Record<string, string>>({ type: 'all', status: 'all' });
  const [q, setQ] = useState('');
  const assets = useGet<Paged<DAsset>>('/discovery/assets', { type: filters.type === 'all' ? undefined : filters.type, status: filters.status === 'all' ? undefined : filters.status, q: q || undefined, page_size: 500 });

  const run = async () => {
    setRunning(true);
    setAi(undefined);
    setScan(Object.fromEntries((sources.data?.sources ?? []).map((s) => [s.id, { status: 'pending' as const }])));
    try {
      const { id } = await post<{ id: string }>('/discovery/scans');
      await streamSSE(`/discovery/scans/${id}/stream`, {}, (event, data) => {
        const d = data as { id: string; status: 'scanning' | 'done'; found?: number; new?: number };
        if (event === 'source') setScan((s) => ({ ...s, [d.id]: { status: d.status, found: d.found, new: d.new } }));
      });
      const s = await post<{ ai: AIMeta }>('/discovery/summary');
      setAi(s.ai);
      await qc.invalidateQueries({ queryKey: ['/discovery/results'] });
      await qc.invalidateQueries({ queryKey: ['/discovery/assets'] });
      toast({ title: 'Discovery complete', description: `${results.data?.total ?? ''} assets reconciled`, tone: 'success' });
    } catch (e) {
      toast({ title: 'Scan failed', description: (e as Error).message, tone: 'error' });
    } finally {
      setRunning(false);
    }
  };

  const cols = useMemo<ColumnDef<DAsset>[]>(
    () => [
      { accessorKey: 'name', header: 'Name', cell: (c) => <span className="text-fg">{c.getValue<string>()}</span> },
      { accessorKey: 'type', header: 'Type', size: 110, cell: (c) => <Badge>{c.getValue<string>()}</Badge> },
      { accessorKey: 'domain', header: 'Domain', size: 180 },
      { accessorKey: 'source', header: 'Discovered by', size: 220 },
      { accessorKey: 'status', header: 'Status', size: 100, cell: (c) => { const v = c.getValue<string>(); return <Badge tone={v === 'shadow' ? 'high' : v === 'drifted' ? 'critical' : 'healthy'} dot>{titleCase(v)}</Badge>; } },
      { accessorKey: 'confidence', header: 'Match', size: 80, cell: (c) => <span className="num font-mono text-xs">{c.getValue<number>().toFixed(2)}</span> },
    ],
    [],
  );

  const r = results.data;
  const done = Object.values(scan).filter((s) => s.status === 'done').length;
  return (
    <Page>
      <PageHeader
        title="Discovery"
        description="Scan cloud, CMDB, code and document sources, then reconcile everything into one asset inventory."
        actions={<><Button variant="secondary" onClick={() => setImportOpen(true)} leading={<FileUp className="h-4 w-4" />}>Import inventory</Button><Button variant="primary" onClick={run} loading={running} leading={<ScanSearch className="h-4 w-4" />}>{running ? `Scanning ${done}/${sources.data?.sources.length ?? 9}` : 'Run discovery scan'}</Button></>}
      />
      <ImportModal open={importOpen} onOpenChange={setImportOpen} onReport={(r) => { setReport(r); setDismissed(false); setReportOpen(true); void imports.refetch(); }} />
      {/* a one-line banner rather than the whole report: a saved report arriving after load would otherwise push the page down by 600px */}
      {banner && (
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm" role="region" aria-label={`Last inventory import: ${banner.filename}`}>
          <span className="min-w-0 flex-1 text-fg-2"><span className="font-medium text-fg">Last inventory import</span> · {banner.filename} · <span className="num font-mono">{banner.matched}</span> matched, <span className="num font-mono">{banner.conflicts}</span> conflicts, <span className="num font-mono">{banner.new}</span> new, <span className="num font-mono">{banner.missing}</span> missing from the export</span>
          <span className="flex items-center gap-2"><Button size="sm" variant="secondary" onClick={() => setReportOpen(true)}>View report</Button><Button size="sm" variant="ghost" onClick={() => { setReport(null); setDismissed(true); setReportOpen(false); }}>Dismiss</Button></span>
        </div>
      )}
      <Modal open={reportOpen} onOpenChange={setReportOpen} title="Inventory reconciliation" description="Your CMDB export compared with the discovered estate. Nothing has been changed." width={1100}>
        {shown ? <ImportResult report={shown} onClose={() => setReportOpen(false)} closeLabel="Close" /> : <div role="status" aria-label="Loading report"><Skeleton className="h-40 w-full" /></div>}
      </Modal>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {!r ? Array.from({ length: 5 }).map((_, i) => <SkeletonTile key={i} />) : (
          <>
            <MetricTile label="Assets discovered" value={fmtNum(r.total)} />
            <MetricTile label="Applications" value={r.by_type.application ?? 0} />
            <MetricTile label="Shadow IT" value={r.shadow} hint="not in the CMDB" sparkTone="high" />
            <MetricTile label="Drifted resources" value={r.drifted} hint="differ from approved IaC" />
            <MetricTile label="Duplicates merged" value={r.duplicates} />
          </>
        )}
      </div>

      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <Panel title="Sources" description="Connectors scanned in this run" flush>
          <ul className="divide-y divide-line-subtle" aria-busy={!sources.data}>
            {/* rows of the final height while loading, so the table below is not pushed down when the connectors arrive */}
            {!sources.data && Array.from({ length: 9 }).map((_, i) => (
              <li key={i} aria-hidden className="flex min-h-[56px] items-center gap-3 px-4 py-2.5"><Skeleton className="h-5 w-5 rounded-full" /><div className="flex-1 space-y-1.5"><Skeleton className="h-3.5 w-40" /><Skeleton className="h-3 w-56 max-w-full" /></div></li>
            ))}
            {sources.data?.sources.map((s) => {
              const st = scan[s.id];
              const status = st?.status ?? (running ? 'pending' : 'done');
              const found = st?.found ?? s.found;
              return (
                <li key={s.id} className="flex min-h-[56px] items-center gap-3 px-4 py-2.5">
                  <span className={cn('flex h-5 w-5 items-center justify-center', status === 'done' ? 'text-healthy' : status === 'scanning' ? 'text-accent' : 'text-fg-3')}>
                    {status === 'scanning' ? <Loader2 className="h-4 w-4 animate-spin" aria-label="scanning" /> : <CheckCircle2 className={cn('h-4 w-4', status === 'pending' && 'opacity-30')} aria-label={status} />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-fg">{s.name}</p>
                    <p className="truncate text-xs text-fg-3">{s.detail}</p>
                  </div>
                  {status === 'done' && <span className="num font-mono text-xs text-fg-2">{fmtNum(found)}{(st?.new ?? s.new) > 0 && <span className="ml-1.5 text-accent">+{st?.new ?? s.new} new</span>}</span>}
                </li>
              );
            })}
          </ul>
        </Panel>
        <div className="space-y-4">
          <AISummary ai={ai} loading={running && !ai} title="Discovery summary" thinking={['Scanning sources', 'Reconciling identities', 'Flagging shadow IT']} className={!ai && !running ? 'hidden' : undefined} />
          {!ai && !running && <Panel title="Shadow IT candidates" description="Seen in code repositories but missing from the CMDB"><ul className="divide-y divide-line-subtle">{r?.shadow_assets.map((a) => <li key={a.id} className="flex items-center justify-between py-2 text-sm"><RefLink type="application" id={a.id} name={a.name} /><span className="text-xs text-fg-3">{a.domain}</span></li>)}</ul></Panel>}
          {(ai || running) && r && r.shadow_assets.length > 0 && <Panel title="Shadow IT candidates"><ul className="divide-y divide-line-subtle">{r.shadow_assets.map((a) => <li key={a.id} className="flex items-center justify-between py-2 text-sm"><RefLink type="application" id={a.id} name={a.name} /><span className="text-xs text-fg-3">{a.domain}</span></li>)}</ul></Panel>}
        </div>
      </div>

      <Panel className="mt-4" title="Discovered assets" description={`${assets.data?.total ?? 0} matching`} flush>
        <div className="p-3">
          <FilterBar
            search={q}
            onSearch={setQ}
            searchPlaceholder="Search assets"
            values={filters}
            onChange={(k, v) => setFilters((f) => ({ ...f, [k]: v }))}
            filters={[
              { key: 'type', label: 'Type', options: ['application', 'api', 'database', 'cloud'].map((t) => ({ value: t, label: titleCase(t) })) },
              { key: 'status', label: 'Status', options: ['known', 'shadow', 'drifted'].map((t) => ({ value: t, label: titleCase(t) })) },
            ]}
          />
        </div>
        <DataTable data={assets.data?.items ?? []} columns={cols} loading={assets.isLoading} getRowId={(r) => r.id} onRowClick={(r) => open({ type: r.type, id: r.id })} maxHeight={460} ariaLabel="Discovered assets" />
      </Panel>
    </Page>
  );
}
