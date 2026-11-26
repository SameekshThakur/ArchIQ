import { useGet } from '@/api/hooks';
import type { AIMeta, Evidence, Ref, Severity } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { RefLink } from '@/components/Ref';
import { Badge, SeverityBadge } from '@/components/ui/Badge';
import { EmptyState, KeyValueList, SkeletonBlock } from '@/components/ui/Panel';
import { titleCase } from '@/lib/format';
import type { InspectorProps } from './registry';

interface Finding {
  id: string;
  rule_id: string;
  category: string;
  severity: Severity;
  title: string;
  affected: Ref[];
  affected_count: number;
  evidence: Evidence[];
  recommendation: string;
  why_it_matters: string;
  effort: { size: string; person_days: number };
  domain: string;
}

export default function FindingInspector({ id }: InspectorProps) {
  const { data, isLoading, error } = useGet<{ finding: Finding; ai: AIMeta }>(`/assessment/findings/${id}`);
  if (isLoading) return <SkeletonBlock className="h-80" />;
  if (error || !data) return <EmptyState title="Finding not found" description={(error as Error)?.message} />;
  const f = data.finding;
  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <SeverityBadge severity={f.severity} />
          <Badge>{titleCase(f.category)}</Badge>
          <Badge mono>{f.rule_id}</Badge>
        </div>
        <h3 className="mt-2 text-base font-semibold text-fg">{f.title}</h3>
      </div>
      <AISummary ai={data.ai} title="Why this matters" />
      <KeyValueList items={[{ label: 'Recommendation', value: f.recommendation }, { label: 'Effort', value: `${f.effort.size} · about ${f.effort.person_days} person-days` }, { label: 'Domain', value: f.domain }, { label: 'Affected', value: `${f.affected_count} assets` }]} />
      <div>
        <p className="micro mb-1.5">Affected assets</p>
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
          {f.affected.slice(0, 40).map((a) => (
            <li key={a.id}><RefLink type={a.type} id={a.id} name={a.name} /></li>
          ))}
        </ul>
      </div>
    </div>
  );
}
