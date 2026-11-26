import { useMutation } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { FileJson, ShieldCheck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { post, useGet } from '@/api/hooks';
import type { Severity } from '@/api/types';
import { Badge, SeverityBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import { FilterBar, SearchInput, Tabs, TextArea } from '@/components/ui/Inputs';
import { Modal } from '@/components/ui/Overlay';
import { FileDrop, SampleFiles, type DroppedFile, type SampleDef } from '@/components/ui/FileDrop';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { KeyValueList, Panel, SkeletonBlock } from '@/components/ui/Panel';
import { titleCase } from '@/lib/format';
import { CheckResults, type CheckData } from './CheckResults';

interface Standard { id: string; title: string; category: string; kind: string; severity: Severity; statement: string; applies_to: string[]; remediation: string; owner: string; effective: string; technology?: string | null; status?: string | null }

const DESIGN_SAMPLES: SampleDef[] = [
  { file: 'claims-copilot-main.tf', label: 'Claims Copilot Terraform, as deployed', note: 'Public OpenAI endpoint, API keys, TLS 1.0 storage, missing tags and diagnostics' },
  { file: 'claims-copilot-main.fixed.tf', label: 'Claims Copilot Terraform, remediated', note: 'Run after the first to show every failure clear and the score recover' },
  { file: 'claims-copilot-main.bicep', label: 'Claims Copilot Bicep, as deployed', note: 'The same story for teams that deploy with Bicep' },
  { file: 'claims-copilot-main.fixed.bicep', label: 'Claims Copilot Bicep, remediated', note: 'Score recovers from 41 to 87' },
];

function CheckTab() {
  const sample = useGet<{ name: string; text: string }>('/standards/sample-design');
  const [text, setText] = useState('');
  const [touched, setTouched] = useState(false);
  useEffect(() => { if (sample.data && !touched) setText(sample.data.text); }, [sample.data, touched]);
  const check = useMutation<CheckData, Error, string>({ mutationFn: (design) => post<CheckData>('/standards/check', { design }) });
  const { mutate } = check;
  const [auto, setAuto] = useState(false);
  const [loaded, setLoaded] = useState<string | null>(null);
  const onFiles = ([f]: DroppedFile[]) => { if (!f) return; setText(f.extracted.text); setTouched(true); setLoaded(f.file.name); mutate(f.extracted.text); };
  useEffect(() => { if (sample.data && !auto) { setAuto(true); mutate(sample.data.text); } }, [sample.data, auto, mutate]);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <Panel title="Design under review" description="Upload a file or paste a design as JSON, Terraform or plain text. Evaluate infrastructure code or design specifications against enterprise policies." actions={<Button size="sm" variant="ghost" leading={<FileJson className="h-3.5 w-3.5" />} onClick={() => { setTouched(false); if (sample.data) setText(sample.data.text); }}>Load template</Button>}>
        <div className="mb-3 space-y-3"><FileDrop compact onFiles={onFiles} accept=".json,.yaml,.yml,.tf,.tfvars,.bicep,.md,.txt,.docx,.pdf" label="Upload a design or infrastructure file" hint="Terraform, Bicep, ARM template, JSON, YAML, Markdown, Word or PDF" /><SampleFiles collapsible samples={DESIGN_SAMPLES} onFiles={onFiles} />{loaded && <p className="text-xs text-fg-3">Loaded {loaded}</p>}</div>
        <TextArea value={text} onChange={(e) => { setText(e.target.value); setTouched(true); setLoaded(null); }} rows={loaded ? 14 : 18} spellCheck={false} className="font-mono text-xs leading-relaxed" aria-label="Design to check" />
        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="text-xs text-fg-3">{text.length.toLocaleString()} characters</p>
          <Button variant="primary" loading={check.isPending} disabled={text.trim().length < 3} leading={<ShieldCheck className="h-4 w-4" />} onClick={() => mutate(text)}>Check against standards</Button>
        </div>
        {check.isError && <p role="alert" className="mt-3 text-xs text-critical">{check.error.message}</p>}
      </Panel>
      <CheckResults data={check.data} loading={check.isPending || (!check.data && !check.isError)} />
    </div>
  );
}

function CatalogueTab({ openId, onOpen }: { openId: string | null; onOpen: (id: string | null) => void }) {
  const [filters, setFilters] = useState<Record<string, string>>({ category: 'all', kind: 'all' });
  const [q, setQ] = useState('');
  const { data, isLoading } = useGet<{ items: Standard[]; total: number; facets: Record<string, Record<string, number>> }>('/standards', { category: filters.category === 'all' ? undefined : filters.category, kind: filters.kind === 'all' ? undefined : filters.kind, q });
  const detail = useGet<Standard>(`/standards/${openId}`, undefined, { enabled: !!openId });
  const cols = useMemo<ColumnDef<Standard>[]>(() => [
    { accessorKey: 'id', header: 'ID', size: 130, cell: (c) => <span className="font-mono text-xs text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'title', header: 'Standard', cell: (c) => <span className="text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'category', header: 'Category', size: 120, cell: (c) => <Badge>{titleCase(c.getValue<string>())}</Badge> },
    { accessorKey: 'kind', header: 'Type', size: 150, cell: (c) => <span className="text-fg-2">{titleCase(c.getValue<string>())}</span> },
    { accessorKey: 'severity', header: 'Severity', size: 100, cell: (c) => <SeverityBadge severity={c.getValue<Severity>()} /> },
  ], []);
  const facet = (k: string) => Object.entries(data?.facets?.[k] ?? {}).map(([v, n]) => ({ value: v, label: `${titleCase(v)} (${n})` }));
  const d = detail.data;
  return (
    <Panel title="Standards catalogue" description={`${data?.total ?? 0} policies, approved technologies and patterns`} flush>
      <div className="flex flex-wrap items-center gap-2 p-3">
        <SearchInput value={q} onChange={setQ} placeholder="Search standards" data-search-input className="w-64" />
        <FilterBar values={filters} onChange={(k, v) => setFilters((f) => ({ ...f, [k]: v }))} filters={[{ key: 'category', label: 'Category', options: facet('category') }, { key: 'kind', label: 'Type', options: facet('kind') }]} />
      </div>
      <DataTable data={data?.items ?? []} columns={cols} loading={isLoading} getRowId={(r) => r.id} onRowClick={(r) => onOpen(r.id)} maxHeight={560} rowHeight={44} ariaLabel="Standards catalogue" />
      <Modal open={!!openId} onOpenChange={(o) => !o && onOpen(null)} title={d?.title ?? openId ?? ''} description={openId ?? undefined} width={640}>
        {d ? (
          <div className="space-y-4">
            <p className="text-sm text-fg-2">{d.statement}</p>
            <KeyValueList items={[{ label: 'Severity', value: <SeverityBadge severity={d.severity} /> }, { label: 'Category', value: titleCase(d.category) }, { label: 'Owner', value: d.owner }, { label: 'Effective', value: d.effective }, { label: 'Applies to', value: d.applies_to?.length ? <span className="flex flex-wrap gap-1">{d.applies_to.map((a) => <Badge key={a} mono>{a}</Badge>)}</span> : 'All components' }, { label: 'Remediation', value: d.remediation }]} />
          </div>
        ) : <SkeletonBlock className="h-40" />}
      </Modal>
    </Panel>
  );
}

export default function StandardsPage() {
  const [params, setParams] = useSearchParams();
  const id = params.get('id');
  const [tab, setTab] = useState(id ? 'catalogue' : 'check');
  useEffect(() => { if (id) setTab('catalogue'); }, [id]);
  return (
    <Page>
      <PageHeader title="Standards" description="The policy catalogue and an automated checker that tells you which standards a proposed design breaks, and how to fix each one." />
      <Tabs value={tab} onValueChange={setTab} items={[{ value: 'check', label: 'Check a design', content: <CheckTab /> }, { value: 'catalogue', label: 'Catalogue', content: <CatalogueTab openId={id} onOpen={(v) => setParams(v ? { id: v } : {})} /> }]} />
    </Page>
  );
}
