import { ArrowRight } from 'lucide-react';
import { Fragment, lazy, Suspense } from 'react';
import type { CopilotCard } from '@/api/types';
import { RefLink } from '@/components/Ref';
import { Badge, SeverityBadge, type Severity, type Tone } from '@/components/ui';
import { Skeleton } from '@/components/ui/Panel';
import { cn } from '@/lib/cn';
import { fmtMoneyK, fmtNum, titleCase } from '@/lib/format';

const FlowGraph = lazy(() => import('@/components/viz/FlowGraph'));

type Row = Record<string, unknown>;
interface RefVal { id: string; type: string; name: string }
const isRef = (v: unknown): v is RefVal => !!v && typeof v === 'object' && 'id' in v && 'name' in v && 'type' in v;

function Cell({ kind, value, row, colKey }: { kind: string; value: unknown; row: Row; colKey: string }) {
  if (value === null || value === undefined || value === '') return <span className="text-fg-3">—</span>;
  if (isRef(value)) return <RefLink type={value.type} id={value.id} name={value.name} />;
  if (colKey === 'name' && isRef(row.ref)) return <RefLink type={row.ref.type} id={row.ref.id} name={String(value)} />;
  switch (kind) {
    case 'severity':
      return <SeverityBadge severity={String(value) as Severity} />;
    case 'score': {
      const n = Number(value);
      return <span className={cn('num font-mono text-xs', n >= 40 ? 'text-critical' : n >= 25 ? 'text-high' : 'text-fg-2')}>{n}</span>;
    }
    case 'money':
      return <span className="num font-mono text-xs">{fmtMoneyK(Number(value))}</span>;
    case 'number':
      return <span className="num font-mono text-xs">{fmtNum(Number(value))}</span>;
    default:
      {
        const text = Array.isArray(value) ? value.join(', ') : String(value);
        return text.length > 48 ? <span className="line-clamp-3 min-w-[200px] text-fg-2" title={text}>{text}</span> : <span className="whitespace-nowrap text-fg-2">{text}</span>;
      }
  }
}

function TableCard({ card }: { card: CopilotCard }) {
  const columns = (card.columns as { key: string; label: string; kind: string }[]) ?? [];
  const rows = (card.rows as Row[]) ?? [];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-line">
            {columns.map((c) => (
              <th key={c.key} scope="col" className="micro whitespace-nowrap px-3 py-2 font-medium">{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line-subtle last:border-0">
              {columns.map((c) => (
                <td key={c.key} className="max-w-[320px] px-3 py-2 align-top"><Cell kind={c.kind} value={r[c.key]} row={r} colKey={c.key} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="px-3 py-4 text-xs text-fg-3">No matching rows.</p>}
    </div>
  );
}

function PathsCard({ card }: { card: CopilotCard }) {
  const paths = (card.paths as { label: string; nodes: { id: string; name: string; type: string; rel?: string | null; payload?: string | null }[] }[]) ?? [];
  return (
    <ul className="space-y-2.5 p-3">
      {paths.map((p, i) => (
        <li key={i} className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
          {p.nodes.map((n, j) => (
            <Fragment key={`${n.id}-${j}`}>
              {j > 0 && (
                <span className="flex items-center gap-1 text-[10px] text-fg-3" title={n.payload ?? undefined}>
                  <ArrowRight className="h-3 w-3" aria-hidden />
                  {n.rel && <span className="font-mono">{n.rel.replace('_', ' ')}</span>}
                </span>
              )}
              <span className="inline-flex items-center rounded border border-line bg-raised px-2 py-1 text-xs">
                <RefLink type={n.type} id={n.id} name={n.name} />
              </span>
            </Fragment>
          ))}
        </li>
      ))}
      {paths.some((p) => p.nodes.some((n) => n.payload)) && <li className="pt-1 text-[11px] text-fg-3">Hover an arrow to see what flows along it.</li>}
    </ul>
  );
}

const toneText: Record<string, string> = { danger: 'text-critical', warning: 'text-high', neutral: 'text-fg', good: 'text-healthy' };
function MetricsCard({ card }: { card: CopilotCard }) {
  const items = (card.items as { label: string; value: number | string; tone?: string }[]) ?? [];
  return (
    <div className="grid grid-cols-2 gap-px bg-line-subtle sm:grid-cols-3 lg:grid-cols-5">
      {items.map((m) => (
        <div key={m.label} className="bg-surface px-3 py-2.5">
          <p className="micro">{m.label}</p>
          <p className={cn('num mt-1 text-xl font-semibold', toneText[m.tone ?? 'neutral'])}>{typeof m.value === 'number' ? fmtNum(m.value) : m.value}</p>
        </div>
      ))}
    </div>
  );
}

function GraphCard({ card }: { card: CopilotCard }) {
  const nodes = ((card.nodes as { id: string; name: string; kind: string; focus?: boolean }[]) ?? []).slice(0, 40);
  const edges = (card.edges as { source: string; target: string; rel?: string }[]) ?? [];
  return (
    <div className="p-3">
      <Suspense fallback={<Skeleton className="h-[320px] w-full" />}>
        <FlowGraph nodes={nodes.map((n) => ({ id: n.id, name: n.name, type: n.kind, focus: n.focus }))} edges={edges} height={320} label={card.title ?? 'Dependency graph'} />
      </Suspense>
    </div>
  );
}

function BulletsCard({ card }: { card: CopilotCard }) {
  const items = (card.items as string[]) ?? [];
  return (
    <ul className="space-y-1.5 p-3 text-sm text-fg-2">
      {items.map((t, i) => (
        <li key={i} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" aria-hidden />{t}</li>
      ))}
    </ul>
  );
}

function KVCard({ card }: { card: CopilotCard }) {
  const rows = (card.rows as { label: string; value: unknown }[]) ?? [];
  const sev = new Set(['critical', 'high', 'medium', 'low']);
  return (
    <dl className="grid grid-cols-[120px_1fr] gap-x-4 gap-y-2 p-3 text-xs">
      {rows.map((r) => (
        <div key={r.label} className="contents">
          <dt className="micro self-start pt-0.5">{r.label}</dt>
          <dd className="min-w-0 break-words text-fg-2">{isRef(r.value) ? <RefLink type={r.value.type} id={r.value.id} name={r.value.name} /> : sev.has(String(r.value)) ? <SeverityBadge severity={String(r.value) as Severity} /> : Array.isArray(r.value) ? r.value.join(', ') : String(r.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function CompareCard({ card }: { card: CopilotCard }) {
  const cols = (card.columns as { id: string; name: string }[]) ?? [];
  const rows = (card.rows as { label: string; values: unknown[] }[]) ?? [];
  const tone = (v: unknown): Tone | null => (['critical', 'high', 'medium', 'low'].includes(String(v)) ? (String(v) as Tone) : null);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className="w-36 px-3 py-2" />
            {cols.map((c) => (
              <th key={c.id} scope="col" className="px-3 py-2 text-sm font-semibold"><RefLink type="application" id={c.id} name={c.name} /></th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-line-subtle last:border-0">
              <th scope="row" className="micro px-3 py-2 font-medium">{r.label}</th>
              {r.values.map((v, i) => (
                <td key={i} className="px-3 py-2 text-fg-2">{tone(v) ? <Badge tone={tone(v)!} className="capitalize">{String(v)}</Badge> : Array.isArray(v) ? v.join(', ') : String(v ?? '—')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const RENDER: Record<string, (p: { card: CopilotCard }) => JSX.Element> = { table: TableCard, paths: PathsCard, metrics: MetricsCard, graph: GraphCard, bullets: BulletsCard, kv: KVCard, compare: CompareCard };

export function ResultCard({ card, flat }: { card: CopilotCard; flat?: boolean }) {
  const Body = RENDER[card.type];
  if (!Body) return null;
  return (
    <section className={cn('overflow-hidden rounded-lg border border-line bg-bg', flat && 'rounded-md')} aria-label={card.title ?? titleCase(card.type)}>
      {card.title && <h4 className="border-b border-line-subtle px-3 py-2 text-xs font-semibold text-fg">{card.title}</h4>}
      <Body card={card} />
    </section>
  );
}
