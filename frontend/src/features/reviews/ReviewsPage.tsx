import { useMutation } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { ClipboardCheck, Plus, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { api, get, post, useGet } from '@/api/hooks';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import { Field, FilterBar, Select, TextArea, TextInput } from '@/components/ui/Inputs';
import { Modal } from '@/components/ui/Overlay';
import { FileDrop, SampleFiles, type DroppedFile, type SampleDef } from '@/components/ui/FileDrop';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { MetricTile, Panel, SkeletonTile } from '@/components/ui/Panel';
import { fmtDate, titleCase } from '@/lib/format';
import { ReviewDetail, VerdictBadge, type ReviewData } from './ReviewDetail';

interface Row { id: string; title: string; domain: string; submitter: string; stage: string; submitted_at: string; arb_date: string; tier: string; summary: string; readiness: number; verdict: string; counts: Record<string, number> }

const STAGES = ['draft', 'ai_reviewed', 'arb_scheduled', 'conditions', 'approved', 'rejected'];

const REVIEW_SAMPLES: SampleDef[] = [
  { file: 'claims-notifications-design.md', label: 'Claims Notification Service v2 (Markdown)', note: 'An ARB submission written as prose, with deliberate policy breaches' },
  { file: 'claims-copilot-main.tf', label: 'Claims Copilot Terraform', note: 'Infrastructure as code reviewed the same way' },
];

export default function ReviewsPage() {
  const nav = useNavigate();
  const [filters, setFilters] = useState<Record<string, string>>({ stage: 'all', verdict: 'all' });
  const { data, isLoading } = useGet<{ items: Row[]; total: number; by_stage: Record<string, number> }>('/reviews');
  const [adhoc, setAdhoc] = useState(false);
  const [form, setForm] = useState({ title: '', tier: 'tier2', design: '' });
  const sample = useMutation({ mutationFn: () => get<{ text: string }>('/standards/sample-design') });
  const qc = useQueryClient();
  const saved = useGet<{ items: { id: number; title: string; tier: string; verdict: string; readiness: number; created_at: string }[] }>('/reviews/adhoc');
  const [result, setResult] = useState<ReviewData | null>(null);
  const reopen = async (id: number) => { setResult(await get<ReviewData>(`/reviews/adhoc/${id}`)); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  const drop = async (id: number) => { await api(`/reviews/adhoc/${id}`, { method: 'DELETE' }); await qc.invalidateQueries({ queryKey: ['/reviews/adhoc'] }); };
  const onFiles = ([f]: DroppedFile[]) => { if (f) setForm((cur) => ({ ...cur, design: f.extracted.text, title: cur.title.trim().length >= 3 ? cur.title : f.file.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ') })); };
  const run = useMutation<ReviewData, Error, void>({ mutationFn: () => post<ReviewData>('/reviews/run', { title: form.title, tier: form.tier, design: form.design, domain: 'Claims' }), onSuccess: (r) => { setResult(r); setAdhoc(false); void qc.invalidateQueries({ queryKey: ['/reviews/adhoc'] }); } });

  const rows = (data?.items ?? []).filter((r) => (filters.stage === 'all' || r.stage === filters.stage) && (filters.verdict === 'all' || r.verdict === filters.verdict));
  const cols = useMemo<ColumnDef<Row>[]>(() => [
    { accessorKey: 'id', header: 'Submission', size: 130, cell: (c) => <span className="font-mono text-xs">{c.getValue<string>()}</span> },
    { accessorKey: 'title', header: 'Title', cell: (c) => <span className="text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'domain', header: 'Domain', size: 150 },
    { accessorKey: 'stage', header: 'Stage', size: 130, cell: (c) => <Badge>{titleCase(c.getValue<string>())}</Badge> },
    { accessorKey: 'readiness', header: 'Readiness', size: 100, cell: (c) => <span className="num font-mono text-xs">{c.getValue<number>()}</span> },
    { accessorKey: 'verdict', header: 'AI verdict', size: 120, cell: (c) => <VerdictBadge verdict={c.getValue<string>()} /> },
    { accessorKey: 'arb_date', header: 'ARB date', size: 110, cell: (c) => <span className="num text-fg-2">{c.getValue<string>() ? fmtDate(c.getValue<string>()) : 'Not scheduled'}</span> },
  ], []);

  return (
    <Page>
      <PageHeader title="Review agent" description="Automated pre-ARB review: every submission is checked against standards, NFR completeness and approved patterns, then given a go, conditional or no-go verdict." actions={<Button variant="primary" leading={<Plus className="h-4 w-4" />} onClick={() => { setAdhoc(true); if (!form.design) sample.mutate(undefined, { onSuccess: (s) => setForm((f) => ({ ...f, design: s.text, title: f.title || 'Ad-hoc design review' })) }); }}>Review a design</Button>} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {!data ? Array.from({ length: 4 }).map((_, i) => <SkeletonTile key={i} />) : (<>
          <MetricTile label="Submissions" value={data.total} />
          <MetricTile label="Go" value={data.items.filter((i) => i.verdict === 'go').length} />
          <MetricTile label="Conditional" value={data.items.filter((i) => i.verdict === 'conditional').length} />
          <MetricTile label="No go" value={data.items.filter((i) => i.verdict === 'no_go').length} />
        </>)}
      </div>

      {result && (
        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between"><h2 className="flex items-center gap-2 text-sm font-semibold text-fg"><ClipboardCheck className="h-4 w-4 text-accent" aria-hidden />Ad-hoc review · {result.submission.title}</h2><Button size="sm" variant="ghost" onClick={() => setResult(null)}>Dismiss</Button></div>
          <ReviewDetail data={result} />
        </div>
      )}

      <Panel className="mt-4" title="Architecture review board queue" description={`${rows.length} submissions`} flush>
        <div className="p-3">
          <FilterBar values={filters} onChange={(k, v) => setFilters((f) => ({ ...f, [k]: v }))} filters={[{ key: 'stage', label: 'Stage', options: STAGES.map((v) => ({ value: v, label: `${titleCase(v)}${data?.by_stage[v] ? ` (${data.by_stage[v]})` : ''}` })) }, { key: 'verdict', label: 'Verdict', options: [{ value: 'go', label: 'Go' }, { value: 'conditional', label: 'Conditional' }, { value: 'no_go', label: 'No go' }] }]} />
        </div>
        <DataTable data={rows} columns={cols} loading={isLoading} getRowId={(r) => r.id} onRowClick={(r) => nav(`/reviews/${r.id}`)} maxHeight={520} rowHeight={48} ariaLabel="Review queue" />
      </Panel>

      {!!saved.data?.items.length && (
        <Panel className="mt-4" title="Your saved reviews" description="Ad-hoc reviews you have run are kept between sessions">
          <ul className="divide-y divide-line-subtle">{saved.data.items.map((r) => (
            <li key={r.id} className="flex items-center gap-3 py-2 text-sm">
              <button type="button" onClick={() => void reopen(r.id)} className="min-w-0 flex-1 truncate text-left text-fg hover:text-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">{r.title}</button>
              <span className="num font-mono text-xs text-fg-3">{r.readiness}</span><VerdictBadge verdict={r.verdict} />
              <span className="hidden w-28 text-right text-xs text-fg-3 sm:block">{fmtDate(r.created_at)}</span>
              <button type="button" aria-label={`Delete saved review ${r.title}`} onClick={() => void drop(r.id)} className="inline-flex h-7 w-7 items-center justify-center rounded text-fg-3 hover:bg-raised hover:text-critical focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"><Trash2 className="h-3.5 w-3.5" /></button>
            </li>))}</ul>
        </Panel>)}

      <Modal open={adhoc} onOpenChange={setAdhoc} title="Review a design" description="Upload a design document or paste JSON, Terraform or plain text. The agent reviews it as it would an ARB submission." width={680}
        footer={<><Button variant="ghost" onClick={() => setAdhoc(false)}>Cancel</Button><Button variant="primary" loading={run.isPending} disabled={form.title.trim().length < 3 || form.design.trim().length < 3} onClick={() => run.mutate()}>Run review</Button></>}>
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-[1fr_160px]">
            <Field label="Title"><TextInput value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} aria-label="Review title" /></Field>
            <Field label="Tier"><Select value={form.tier} onValueChange={(v) => setForm({ ...form, tier: v })} label="Tier" options={[{ value: 'tier1', label: 'Tier 1 · critical' }, { value: 'tier2', label: 'Tier 2' }, { value: 'tier3', label: 'Tier 3' }]} /></Field>
          </div>
          <FileDrop compact onFiles={onFiles} accept=".json,.yaml,.yml,.tf,.tfvars,.bicep,.md,.txt,.docx,.pdf" label="Upload a design document" hint="Word, PDF, Markdown, Terraform, JSON or YAML" />
          <SampleFiles samples={REVIEW_SAMPLES} onFiles={onFiles} />
          <Field label="Design"><TextArea rows={10} value={form.design} onChange={(e) => setForm({ ...form, design: e.target.value })} className="font-mono text-xs" spellCheck={false} aria-label="Design" /></Field>
          {run.isError && <p role="alert" className="text-xs text-critical">{run.error.message}</p>}
        </div>
      </Modal>
    </Page>
  );
}
