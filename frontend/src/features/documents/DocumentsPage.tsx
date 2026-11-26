import type { ColumnDef } from '@tanstack/react-table';
import { FileUp, Trash2 } from 'lucide-react';
import { Suspense, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, post } from '@/api/client';
import { useGet } from '@/api/hooks';
import type { AIMeta, Paged } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { RefLink, useOpenRef } from '@/components/Ref';
import { LazyMermaid } from '@/components/viz/LazyChart';
import { Badge, SeverityBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import { FilterBar, Modal, TextArea, TextInput, Field, Tabs, FileDrop, SampleFiles, type DroppedFile, type SampleDef } from '@/components/ui';
import { MetricTile, Panel, ProgressBar, Skeleton, SkeletonTile, scoreColor } from '@/components/ui/Panel';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { useUI } from '@/store/ui';
import { titleCase } from '@/lib/format';
import type { DocAnalysis } from '@/features/inspector/DocumentInspector';

interface Row { id: string; title: string; doc_type: string; source: string; domain: string; status: string; updated_at: string; age_days: number; stale: boolean; author: string; entities: number; relations: number; conflicts: number; uploaded: boolean }
interface Conflict { id: string; title: string; severity: string; recommended: string; rationale: string; basis: string; claims: { value: string; doc_id: string; doc_title: string; status: string; updated_at: string; matches_estate: boolean | null; sentence: string }[] }
interface Gap { id: string; kind: string; severity: string; title: string; detail: string; app_id: string | null; evidence_asset: string }
interface Summary { summary: { documents: number; entities: number; relations: number; conflicts: number; gaps: number; stale: number; coverage: number }; coverage: { overall: number; by_domain: { domain: string; coverage: number; apps: number }[] }; ai: AIMeta }

const DOC_SAMPLES: SampleDef[] = [
  { file: 'Policy-Admin-Operations-Runbook.pdf', label: 'Policy Admin operations runbook (PDF)', note: 'Documents Policy Admin Core → Policy Master DB and closes the largest gap' },
  { file: 'Claims-Intake-Modernization-HLD-v1.2.docx', label: 'Claims Intake Modernization HLD (Word)', note: 'Agrees with the estate in most places, but contradicts it on one hosting claim' },
  { file: 'ADR-0052-Event-Driven-Claims-Notifications.md', label: 'ADR-0052 Event-driven notifications (Markdown)', note: 'An accepted decision record that adds Kafka relationships' },
];

const SAMPLE = `# Payments Hub HLD\n\nStatus: Draft.\n\nPolicy Admin Core stores its data in Policy Master DB. Policy Admin Core calls Customer API v2. Claims Payments Hub integrates with SAP S/4HANA Finance using api.`;

export default function DocumentsPage() {
  const qc = useQueryClient();
  const open = useOpenRef();
  const toast = useUI((s) => s.toast);
  const [tab, setTab] = useState('documents');
  const [filters, setFilters] = useState<Record<string, string>>({ doc_type: 'all', status: 'all' });
  const [q, setQ] = useState('');
  const [upload, setUpload] = useState(false);
  const [form, setForm] = useState({ title: 'Payments Hub HLD', text: SAMPLE });
  const [ingested, setIngested] = useState<{ title: string; a: DocAnalysis }[]>([]);
  const [busy, setBusy] = useState(false);
  const sum = useGet<Summary>('/documents/summary');
  const docs = useGet<Paged<Row>>('/documents', { q: q || undefined, doc_type: filters.doc_type === 'all' ? undefined : filters.doc_type, status: filters.status === 'all' ? undefined : filters.status, page_size: 200 });
  const conflicts = useGet<{ items: Conflict[] }>('/documents/conflicts');
  const gaps = useGet<{ items: Gap[]; total: number }>('/documents/gaps', { limit: 60 });
  const diagram = useGet<{ mermaid: string }>('/documents/diagram');

  const refresh = () => Promise.all(['/documents', '/documents/gaps', '/documents/summary', '/documents/conflicts', '/documents/diagram'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  const remove = async (r: Row) => {
    try {
      await api(`/documents/${r.id}`, { method: 'DELETE' });
      toast({ title: 'Document removed', description: r.title, tone: 'success' });
      await refresh();
    } catch (e) { toast({ title: 'Could not remove document', description: (e as Error).message, tone: 'error' }); }
  };
  const cols = useMemo<ColumnDef<Row>[]>(() => [
    { accessorKey: 'title', header: 'Document', cell: (c) => <span className="text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'doc_type', header: 'Type', size: 90, cell: (c) => <Badge>{c.getValue<string>()}</Badge> },
    { accessorKey: 'status', header: 'Status', size: 100, cell: (c) => { const v = c.getValue<string>(); return <Badge tone={v === 'Outdated' || v === 'Superseded' ? 'high' : v === 'Draft' ? 'medium' : 'healthy'}>{v}</Badge>; } },
    { accessorKey: 'domain', header: 'Domain', size: 170 },
    { accessorKey: 'updated_at', header: 'Updated', size: 100, cell: (c) => <span className="num font-mono text-xs">{c.getValue<string>()}</span> },
    { accessorKey: 'entities', header: 'Entities', size: 80, cell: (c) => <span className="num font-mono text-xs">{c.getValue<number>()}</span> },
    { accessorKey: 'conflicts', header: 'Conflicts', size: 90, cell: (c) => (c.getValue<number>() ? <Badge tone="high">{c.getValue<number>()}</Badge> : <span className="text-fg-3">—</span>) },
    { id: 'remove', header: '', size: 44, cell: (c) => (c.row.original.uploaded ? <button type="button" aria-label={`Remove ${c.row.original.title}`} title="Remove this uploaded document" onClick={(e) => { e.stopPropagation(); void remove(c.row.original); }} className="inline-flex h-7 w-7 items-center justify-center rounded text-fg-3 hover:bg-raised hover:text-critical focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"><Trash2 className="h-3.5 w-3.5" /></button> : null) },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], []);

  const analyse = async (items: { title: string; text: string }[]) => {
    setBusy(true);
    const done: { title: string; a: DocAnalysis }[] = [];
    try {
      for (const it of items) done.push({ title: it.title, a: await post<DocAnalysis>('/documents/ingest', { title: it.title, text: it.text }) });
      const rel = done.reduce((n, d) => n + d.a.relations.length, 0);
      toast({ title: items.length > 1 ? `${items.length} documents analysed` : 'Document analysed', description: `${rel} relations extracted`, tone: 'success' });
    } catch (e) {
      toast({ title: 'Could not analyse document', description: (e as Error).message, tone: 'error' });
    } finally {
      setIngested((prev) => [...done, ...prev]);
      await refresh();
      setBusy(false);
    }
  };
  const ingest = () => analyse([{ title: form.title, text: form.text }]);
  const onFiles = (files: DroppedFile[]) => analyse(files.map((f) => ({ title: f.file.name.replace(/\.[^.]+$/, ''), text: f.extracted.text })));

  const s = sum.data?.summary;
  return (
    <Page>
      <PageHeader title="Document intelligence" description="Read architecture documents, extract what they say about the estate, and reveal where they disagree with each other and with reality." actions={<Button variant="primary" leading={<FileUp className="h-4 w-4" />} onClick={() => { setIngested([]); setUpload(true); }}>Upload documents</Button>} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {!s ? Array.from({ length: 5 }).map((_, i) => <SkeletonTile key={i} />) : (<>
          <MetricTile label="Documents" value={s.documents} />
          <MetricTile label="Relations extracted" value={s.relations} hint={`${s.entities} assets recognised`} />
          <MetricTile label="Conflicts" value={s.conflicts} sparkTone="high" hint="documents disagree" />
          <MetricTile label="Gaps" value={s.gaps} hint={`${s.stale} stale documents`} />
          <MetricTile label="Estate documented" value={s.coverage} unit="%" />
        </>)}
      </div>
      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <AISummary ai={sum.data?.ai} loading={sum.isLoading} title="What the documents say" thinking={['Extracting entities', 'Extracting relations', 'Comparing claims across documents']} />
        <Panel title="Coverage by domain" description="Share of known dependencies that a document records">
          <ul className="space-y-2.5">{sum.data?.coverage.by_domain.map((d) => (<li key={d.domain} className="text-xs"><div className="mb-1 flex justify-between text-fg-2"><span>{d.domain}</span><span className="num font-mono">{d.coverage}%</span></div><ProgressBar value={d.coverage} tone={scoreColor(d.coverage) as 'healthy'} label={`${d.domain} coverage`} /></li>))}</ul>
        </Panel>
      </div>
      <Tabs className="mt-5" value={tab} onValueChange={setTab} items={[
        { value: 'documents', label: 'Documents', count: docs.data?.total, content: (
          <div className="space-y-3 pt-3">
            <FilterBar search={q} onSearch={setQ} searchPlaceholder="Search documents" values={filters} onChange={(k, v) => setFilters((f) => ({ ...f, [k]: v }))}
              filters={[{ key: 'doc_type', label: 'Type', options: Object.keys(docs.data?.facets?.doc_type ?? {}).map((v) => ({ value: v, label: v })) }, { key: 'status', label: 'Status', options: Object.keys(docs.data?.facets?.status ?? {}).map((v) => ({ value: v, label: v })) }]} />
            <DataTable data={docs.data?.items ?? []} columns={cols} loading={docs.isLoading} getRowId={(r) => r.id} onRowClick={(r) => open({ type: 'document', id: r.id })} ariaLabel="Documents" maxHeight={480} />
          </div>) },
        { value: 'conflicts', label: 'Conflicts', count: conflicts.data?.items.length, content: (
          <div className="space-y-3 pt-3">{conflicts.data?.items.map((c) => (
            <Panel key={c.id} title={<span className="flex items-center gap-2">{c.title}<SeverityBadge severity={c.severity as 'high'} /></span>}>
              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">{c.claims.map((cl) => (
                <div key={cl.doc_id} className="rounded-md border border-line-subtle bg-bg p-2.5 text-xs">
                  <div className="flex items-center justify-between"><span className="font-medium text-fg">{cl.value}</span><Badge tone={cl.matches_estate ? 'healthy' : cl.status === 'Outdated' || cl.status === 'Superseded' ? 'high' : 'neutral'}>{cl.matches_estate ? 'matches estate' : cl.status}</Badge></div>
                  <p className="mt-1 text-fg-3"><RefLink type="document" id={cl.doc_id} name={cl.doc_title} /> · reviewed {cl.updated_at}</p>
                </div>))}</div>
              <p className="mt-3 rounded-md border border-accent/25 bg-accent/5 p-2.5 text-xs text-fg-2"><span className="font-medium text-accent">Recommended: {c.recommended}.</span> {c.rationale}</p>
            </Panel>))}</div>) },
        { value: 'gaps', label: 'Gaps', count: gaps.data?.total, content: (
          <ul className="mt-3 divide-y divide-line-subtle rounded-lg border border-line bg-surface">{gaps.data?.items.map((g) => (
            <li key={g.id} className="flex items-start justify-between gap-3 px-4 py-2.5 text-sm"><div className="min-w-0"><p className="text-fg">{g.title}</p><p className="text-xs text-fg-3">{g.detail}</p></div><div className="flex shrink-0 items-center gap-2"><Badge>{titleCase(g.kind)}</Badge><SeverityBadge severity={g.severity as 'high'} /></div></li>))}</ul>) },
        { value: 'diagram', label: 'Reconstructed diagram', content: (
          <Panel className="mt-3" title="SAP → MuleSoft → Salesforce → Snowflake" description="Rebuilt from the Finance and Customer Integration HLD. Dotted red lines are undocumented dependencies; dotted grey lines are claims that conflict with other documents.">
            {diagram.data ? <Suspense fallback={<Skeleton className="h-40" />}><LazyMermaid code={diagram.data.mermaid} /></Suspense> : <Skeleton className="h-40" />}
          </Panel>) },
      ]} />
      <Modal open={upload} onOpenChange={setUpload} title="Analyse documents" description="Upload design documents or paste text. Entities and relations are extracted and compared with the rest of the corpus." width={720}
        footer={<><Button variant="ghost" onClick={() => setUpload(false)}>Close</Button><Button variant="primary" loading={busy} onClick={ingest} disabled={form.text.trim().length < 20 || form.title.trim().length < 3}>Analyse pasted text</Button></>}>
        <div className="space-y-3">
          <FileDrop multiple disabled={busy} onFiles={onFiles} label="Drop documents here or browse" hint="Word, PDF, Markdown, text or HTML · up to 10 files · 8 MB each" />
          <SampleFiles samples={DOC_SAMPLES} onFiles={onFiles} />
          {ingested.length > 0 && (
            <ul className="space-y-2" aria-label="Analysed documents">{ingested.map((d) => (
              <li key={d.a.id} className="rounded-md border border-line bg-bg p-3 text-xs">
                <div className="flex items-center justify-between gap-2"><p className="font-medium text-fg">{d.title}</p><Button size="sm" variant="secondary" onClick={() => { setUpload(false); open({ type: 'document', id: d.a.id }); }}>Open analysis</Button></div>
                <p className="mt-1 text-fg-2">{d.a.entities.length} assets · {d.a.relations.length} relations · {d.a.conflicts.length} conflicts</p>
                {d.a.relations.length > 0 && <ul className="mt-1.5 space-y-0.5 text-fg-3">{d.a.relations.slice(0, 4).map((r, i) => <li key={i}>{r.subject.name} <span className="text-accent">{r.label}</span> {r.object.name}</li>)}{d.a.relations.length > 4 && <li>+{d.a.relations.length - 4} more</li>}</ul>}
              </li>))}</ul>)}
          <details className="rounded-md border border-line px-3 py-2">
            <summary className="cursor-pointer text-sm text-fg-2">Or paste text</summary>
            <div className="mt-2 space-y-3">
              <Field label="Title"><TextInput value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} /></Field>
              <Field label="Document text" hint="Statements like “X stores its data in Y” or “X calls Y” are recognised."><TextArea rows={6} value={form.text} onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))} className="font-mono text-xs" /></Field>
            </div>
          </details>
        </div>
      </Modal>
    </Page>
  );
}
