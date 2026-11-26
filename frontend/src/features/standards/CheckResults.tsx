import { CheckCircle2, ChevronDown, TriangleAlert, XCircle } from 'lucide-react';
import { useState } from 'react';
import type { AIMeta, Severity } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { Badge, SeverityBadge } from '@/components/ui/Badge';
import { SegmentedControl } from '@/components/ui/Inputs';
import { ScoreRing } from '@/components/ui/Panel';
import { cn } from '@/lib/cn';
import { Link } from 'react-router-dom';

export interface StdResult {
  standard_id: string;
  title: string;
  category: string;
  kind: string;
  severity: Severity;
  status: 'pass' | 'warn' | 'fail';
  components: string[];
  rationale: string;
  remediation: string;
  statement: string;
}
export interface CheckData {
  design_name: string;
  format: string;
  components: number;
  results: StdResult[];
  passed: number;
  warned: number;
  failed: number;
  score: number;
  headline: string;
  ai?: AIMeta;
  notes?: string[];
}

const ICON = { pass: CheckCircle2, warn: TriangleAlert, fail: XCircle };
const TONE = { pass: 'text-healthy', warn: 'text-high', fail: 'text-critical' };

export function ResultRow({ r }: { r: StdResult }) {
  const [open, setOpen] = useState(r.status === 'fail');
  const Icon = ICON[r.status];
  return (
    <li className="border-b border-line-subtle last:border-0">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-raised/50">
        <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', TONE[r.status])} aria-label={r.status} />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs text-fg-3">{r.standard_id}</span><span className="text-sm font-medium text-fg">{r.title}</span></span>
          {!open && <span className="mt-0.5 block truncate text-xs text-fg-3">{r.rationale}</span>}
        </span>
        <SeverityBadge severity={r.severity} />
        <ChevronDown className={cn('mt-1 h-4 w-4 shrink-0 text-fg-3 transition-transform', open && 'rotate-180')} aria-hidden />
      </button>
      {open && (
        <div className="space-y-2 px-4 pb-4 pl-11 text-xs">
          <p className="text-fg-2">{r.rationale}</p>
          {r.status !== 'pass' && <p className="rounded border border-line bg-bg px-3 py-2 text-fg-2"><span className="micro mr-2">Fix</span>{r.remediation}</p>}
          <p className="text-fg-3">{r.statement}</p>
          <div className="flex flex-wrap items-center gap-1.5">
            {r.components.map((c) => <Badge key={c} mono>{c}</Badge>)}
            <Link to={`/standards?id=${r.standard_id}`} className="ml-auto text-accent hover:underline">View standard</Link>
          </div>
        </div>
      )}
    </li>
  );
}

export function CheckResults({ data, loading }: { data?: CheckData; loading?: boolean }) {
  const [f, setF] = useState<'all' | 'fail' | 'warn' | 'pass'>('all');
  const order = { fail: 0, warn: 1, pass: 2 } as const;
  const rows = (data?.results ?? []).filter((r) => f === 'all' || r.status === f).sort((a, b) => order[a.status] - order[b.status]);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 rounded-lg border border-line bg-surface p-4">
        <ScoreRing score={data?.score ?? 0} size={84} />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-fg">{loading ? 'Checking design…' : data?.headline}</p>
          {data && <p className="mt-1 text-xs text-fg-3">{data.design_name} · {data.components} components · {data.results.length} standards applied</p>}
          {data && <div className="mt-2 flex gap-1.5"><Badge tone="critical" dot>{data.failed} failed</Badge><Badge tone="high" dot>{data.warned} warnings</Badge><Badge tone="healthy" dot>{data.passed} passed</Badge></div>}
        </div>
      </div>
      {!!data?.notes?.length && (
        <div role="note" className="rounded-lg border border-medium/30 bg-medium/5 p-3 text-xs text-fg-2">
          <p className="mb-1 font-medium text-fg">Not analysed ({data.notes.length})</p>
          <ul className="list-disc space-y-0.5 pl-4">{data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </div>)}
      {(data?.ai || loading) && <AISummary ai={data?.ai} loading={loading} title="AI compliance summary" thinking={['Parsing the design', 'Matching standards to components', 'Evaluating rules']} />}
      {data && (
        <div className="overflow-hidden rounded-lg border border-line bg-surface">
          <div className="flex items-center justify-between border-b border-line-subtle px-4 py-2.5">
            <h3 className="text-sm font-semibold text-fg">Results</h3>
            <SegmentedControl size="sm" label="Filter results" value={f} onChange={setF} options={[{ value: 'all', label: 'All' }, { value: 'fail', label: 'Failed' }, { value: 'warn', label: 'Warnings' }, { value: 'pass', label: 'Passed' }]} />
          </div>
          <ul>{rows.map((r) => <ResultRow key={r.standard_id} r={r} />)}</ul>
          {rows.length === 0 && <p className="px-4 py-6 text-sm text-fg-3">Nothing in this category.</p>}
        </div>
      )}
    </div>
  );
}
