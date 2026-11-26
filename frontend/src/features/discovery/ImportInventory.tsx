import type { ColumnDef } from '@tanstack/react-table';
import { useMemo, useState } from 'react';
import { post } from '@/api/client';
import type { AIMeta } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { RefLink } from '@/components/Ref';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import { FileDrop, SampleFiles, type DroppedFile, type SampleDef } from '@/components/ui/FileDrop';
import { Modal } from '@/components/ui/Overlay';
import { MetricTile, Panel } from '@/components/ui/Panel';
import { titleCase } from '@/lib/format';

export interface ImportItem {
  row: number;
  name: string;
  number: string | null;
  status: 'matched' | 'conflict' | 'probable' | 'new' | 'retired';
  confidence: number;
  asset_id: string | null;
  asset_name: string | null;
  domain: string | null;
  owner: string | null;
  diffs: { field: string; export: string; estate: string }[];
}
export interface ImportReport {
  filename: string;
  rows: number;
  matched: number;
  conflicts: number;
  probable: number;
  new: number;
  retired: number;
  conflict_fields: Record<string, number>;
  estate_total: number;
  items: ImportItem[];
  missing: { id: string; name: string; domain: string; criticality: string; team: string }[];
  ai: AIMeta;
}

const SAMPLES: SampleDef[] = [
  { file: 'sample-cmdb-export-2026-11.xlsx', label: 'Reference CMDB export (Excel)', note: 'ServiceNow-style export of 66 applications with drift' },
  { file: 'sample-cmdb-export-2026-11.csv', label: 'Reference CMDB export (CSV)', note: 'The same data as plain CSV' },
];
const TONE: Record<ImportItem['status'], 'high' | 'medium' | 'low' | 'healthy' | 'neutral'> = { conflict: 'high', new: 'medium', probable: 'low', retired: 'neutral', matched: 'healthy' };

export function ImportModal({ open, onOpenChange, onReport }: { open: boolean; onOpenChange: (o: boolean) => void; onReport: (r: ImportReport) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onFiles = async ([f]: DroppedFile[]) => {
    if (!f) return;
    setBusy(true);
    setError(null);
    try {
      onReport(await post<ImportReport>('/discovery/import', { filename: f.file.name, text: f.extracted.text }));
      onOpenChange(false);
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Import an inventory export" description="Upload a CMDB or asset-register export. It is compared with the discovered estate; nothing is changed." width={640}
      footer={<Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>}>
      <div className="space-y-3">
        <FileDrop disabled={busy} onFiles={onFiles} accept=".csv,.tsv,.xlsx,.txt" label="Drop a CSV or Excel export here or browse" hint="Needs an application name column; owner, criticality, hosting and status are compared when present" />
        <SampleFiles samples={SAMPLES} onFiles={onFiles} />
        {busy && <p className="text-xs text-fg-3" role="status">Reconciling with the estate…</p>}
        {error && <p role="alert" className="text-xs text-critical">{error}</p>}
      </div>
    </Modal>
  );
}

export function ImportResult({ report, onClose, closeLabel = 'Dismiss' }: { report: ImportReport; onClose: () => void; closeLabel?: string }) {
  const [only, setOnly] = useState<'issues' | 'all'>('issues');
  const rows = useMemo(() => (only === 'all' ? report.items : report.items.filter((i) => i.status !== 'matched')), [report, only]);
  const cols = useMemo<ColumnDef<ImportItem>[]>(() => [
    { accessorKey: 'name', header: 'Application in export', cell: (c) => <span className="text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'status', header: 'Result', size: 110, cell: (c) => <Badge tone={TONE[c.getValue<ImportItem['status']>()]}>{titleCase(c.getValue<string>())}</Badge> },
    { id: 'estate', header: 'Matched estate asset', size: 190, cell: (c) => (c.row.original.asset_id ? <RefLink type="application" id={c.row.original.asset_id} name={c.row.original.asset_name ?? c.row.original.asset_id} /> : <span className="text-fg-3">Not in estate</span>) },
    { id: 'diffs', header: 'Differences', cell: (c) => (c.row.original.diffs.length ? <span className="line-clamp-2 min-w-[220px] text-xs text-fg-2">{c.row.original.diffs.map((d) => `${titleCase(d.field)}: export “${d.export}”, discovered “${d.estate}”`).join(' · ')}</span> : <span className="text-fg-3">{c.row.original.status === 'probable' ? `Name similarity ${Math.round(c.row.original.confidence * 100)}%` : '—'}</span>) },
  ], []);
  return (
    <section className="mt-4 space-y-4" aria-label={`Import report for ${report.filename}`}>
      <div className="flex items-center justify-between"><h2 className="text-sm font-semibold text-fg">Inventory import · {report.filename}</h2><Button size="sm" variant="ghost" onClick={onClose}>{closeLabel}</Button></div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <MetricTile label="Rows in export" value={report.rows} hint={`${report.estate_total} in estate`} />
        <MetricTile label="Clean matches" value={report.matched} />
        <MetricTile label="Conflicts" value={report.conflicts} hint={Object.entries(report.conflict_fields).map(([k, v]) => `${v} ${k}`).join(', ') || undefined} sparkTone="high" />
        <MetricTile label="Not in estate" value={report.new} hint={report.retired ? `+${report.retired} retired` : undefined} />
        <MetricTile label="Missing from export" value={report.missing.length} hint="in estate only" sparkTone="high" />
      </div>
      <AISummary ai={report.ai} title="Reconciliation summary" />
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Panel title="Rows to review" description={`${rows.length} of ${report.rows} shown`} flush actions={<Button size="sm" variant="ghost" onClick={() => setOnly(only === 'issues' ? 'all' : 'issues')}>{only === 'issues' ? 'Show all rows' : 'Only differences'}</Button>}>
          <DataTable data={rows} columns={cols} getRowId={(r) => String(r.row)} maxHeight={420} rowHeight={48} ariaLabel="Import reconciliation" />
        </Panel>
        <Panel title="In the estate, absent from the export" description="Discovered but not recorded in this CMDB">
          <ul className="divide-y divide-line-subtle">{report.missing.map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-2 py-2 text-sm"><RefLink type="application" id={m.id} name={m.name} /><span className="flex items-center gap-2 text-xs text-fg-3">{m.domain}<Badge tone={m.criticality === 'critical' ? 'critical' : m.criticality === 'high' ? 'high' : 'neutral'}>{titleCase(m.criticality)}</Badge></span></li>))}</ul>
        </Panel>
      </div>
    </section>
  );
}
