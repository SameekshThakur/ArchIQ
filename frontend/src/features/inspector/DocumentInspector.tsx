import { useMemo } from 'react';
import { useGet } from '@/api/hooks';
import { RefLink } from '@/components/Ref';
import { Badge } from '@/components/ui/Badge';
import { EmptyState, SkeletonBlock } from '@/components/ui/Panel';
import { KeyValueList } from '@/components/ui/Panel';
import { cn } from '@/lib/cn';
import type { InspectorProps } from './registry';

export interface Entity {
  text: string;
  kind: string;
  id: string | null;
  count: number;
  mentions: [number, number][];
}
export interface Relation {
  subject: { name: string; id: string | null };
  rel: string;
  label: string;
  object: { name: string; id: string | null; kind: string };
  style: string | null;
  sentence: string;
}
export interface DocAnalysis {
  id: string;
  title: string;
  doc_type: string;
  source: string;
  domain: string;
  status: string;
  updated_at: string;
  age_days: number;
  stale: boolean;
  author: string;
  path: string;
  text: string;
  entities: Entity[];
  relations: Relation[];
  conflicts: { id: string; title: string; recommended: string; severity: string }[];
  diagram: string;
}

const KIND_CLASS: Record<string, string> = { application: 'bg-accent/15 text-accent', database: 'bg-accent-2/15 text-accent-2', api: 'bg-low/15 text-low', technology: 'bg-medium/15 text-medium', host: 'bg-healthy/15 text-healthy' };

/** Document text with extracted entities highlighted in place. */
export function HighlightedText({ text, entities, className }: { text: string; entities: Entity[]; className?: string }) {
  const parts = useMemo(() => {
    const spans = entities.flatMap((e) => e.mentions.map(([s, t]) => ({ s, t, e }))).sort((a, b) => a.s - b.s);
    const out: { text: string; e?: Entity }[] = [];
    let at = 0;
    for (const sp of spans) {
      if (sp.s < at) continue;
      if (sp.s > at) out.push({ text: text.slice(at, sp.s) });
      out.push({ text: text.slice(sp.s, sp.t), e: sp.e });
      at = sp.t;
    }
    if (at < text.length) out.push({ text: text.slice(at) });
    return out;
  }, [text, entities]);
  return (
    <pre className={cn('whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-fg-2', className)}>
      {parts.map((p, i) =>
        p.e ? (
          <mark key={i} title={`${p.e.kind}${p.e.id ? ` · ${p.e.id}` : ''}`} className={cn('rounded px-0.5', KIND_CLASS[p.e.kind] ?? 'bg-raised text-fg')}>
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </pre>
  );
}

export default function DocumentInspector({ id }: InspectorProps) {
  const { data, isLoading, error } = useGet<DocAnalysis>(`/documents/${id}`);
  if (isLoading) return <SkeletonBlock className="h-80" />;
  if (error || !data) return <EmptyState title="Document not found" description={(error as Error)?.message} />;
  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="accent">{data.doc_type}</Badge>
          <Badge tone={data.stale ? 'high' : 'healthy'}>{data.status}</Badge>
          {data.stale && <Badge tone="high">stale · {data.age_days} days</Badge>}
        </div>
        <h3 className="mt-2 text-base font-semibold text-fg">{data.title}</h3>
      </div>
      <KeyValueList items={[{ label: 'Source', value: data.source }, { label: 'Author', value: data.author }, { label: 'Updated', value: data.updated_at }, { label: 'Path', value: data.path, mono: true }]} />
      {data.conflicts.length > 0 && (
        <div className="rounded-lg border border-high/30 bg-high/5 p-3 text-xs text-fg-2">
          <p className="mb-1 font-medium text-high">Conflicts with other documents</p>
          <ul className="list-disc pl-4">{data.conflicts.map((c) => <li key={c.id}>{c.title} Recommended: <span className="text-fg">{c.recommended}</span></li>)}</ul>
        </div>
      )}
      <div>
        <p className="micro mb-1.5">Recognised assets ({data.entities.length})</p>
        <div className="flex flex-wrap gap-1.5">
          {data.entities.map((e) => (e.id ? <Badge key={e.text} tone="accent"><RefLink type={e.kind} id={e.id} name={e.text} className="text-[11px]" /></Badge> : <Badge key={e.text}>{e.text}</Badge>))}
        </div>
      </div>
      <div className="max-h-[360px] overflow-y-auto rounded-md border border-line bg-bg p-3">
        <HighlightedText text={data.text} entities={data.entities} />
      </div>
    </div>
  );
}
