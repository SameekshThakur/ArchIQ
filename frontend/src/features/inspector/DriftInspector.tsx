import { useQueryClient } from '@tanstack/react-query';
import { useGet, useApiMutation } from '@/api/hooks';
import { post } from '@/api/client';
import type { Severity } from '@/api/types';
import { Badge, SeverityBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Diff } from '@/components/ui/Code';
import { EmptyState, KeyValueList, SkeletonBlock } from '@/components/ui/Panel';
import { CodeBlock } from '@/components/ui/Code';
import { useUI } from '@/store/ui';
import { RefLink } from '@/components/Ref';
import type { InspectorProps } from './registry';

export interface DriftItem {
  id: string;
  resource: { id: string; name: string; type: string; region: string; env: string; resource_group: string };
  app_id: string;
  domain: string;
  owner: { name: string; team: string };
  severity: Severity;
  changes: { attribute: string; approved: unknown; deployed: unknown }[];
  summary: string;
  detected_at: string;
  status: string;
  ticket: string | null;
  exception_expires: string | null;
  approved_iac: string;
  deployed_config: string;
  standard_id: string;
}

export default function DriftInspector({ id }: InspectorProps) {
  const { data, isLoading, error } = useGet<{ item: DriftItem; remediation_preview: string }>(`/drift/${id}`);
  const qc = useQueryClient();
  const toast = useUI((s) => s.toast);
  const act = useApiMutation<{ message: string }, { action: string; days?: number }>((b) => post(`/drift/${id}/actions`, b));
  if (isLoading) return <SkeletonBlock className="h-80" />;
  if (error || !data) return <EmptyState title="Drift item not found" description={(error as Error)?.message} />;
  const d = data.item;
  const run = (action: string) =>
    act.mutate({ action, days: 30 }, {
      onSuccess: (r) => {
        toast({ title: r.message, tone: 'success' });
        void qc.invalidateQueries({ queryKey: [`/drift/${id}`] });
        void qc.invalidateQueries({ queryKey: ['/drift'] });
        void qc.invalidateQueries({ queryKey: ['/overview/summary'] });
      },
    });
  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <SeverityBadge severity={d.severity} />
          <Badge tone={d.status === 'open' ? 'critical' : 'accent'}>{d.status.replace(/_/g, ' ')}</Badge>
          <Badge mono>{d.standard_id}</Badge>
        </div>
        <h3 className="mt-2 text-base font-semibold text-fg">{d.summary}</h3>
        <p className="mt-1 text-sm text-fg-2"><RefLink type="cloud" id={d.resource.id} name={d.resource.name} /> · {d.resource.type.replace(/_/g, ' ')} · {d.resource.region}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="primary" loading={act.isPending} onClick={() => run('remediate')} disabled={d.status === 'remediating'}>Remediate</Button>
        <Button size="sm" variant="secondary" onClick={() => run('ticket')} disabled={!!d.ticket}>{d.ticket ? d.ticket : 'Raise ticket'}</Button>
        <Button size="sm" variant="outline" onClick={() => run('exception')}>Grant 30-day exception</Button>
      </div>
      <KeyValueList items={[{ label: 'Owner', value: `${d.owner.name} · ${d.owner.team}` }, { label: 'Domain', value: d.domain }, { label: 'Detected', value: d.detected_at.slice(0, 16).replace('T', ' ') }, ...(d.exception_expires ? [{ label: 'Exception until', value: d.exception_expires }] : [])]} />
      <div>
        <p className="micro mb-1.5">Configuration differences</p>
        <ul className="space-y-1">
          {d.changes.map((c) => (
            <li key={c.attribute} className="flex items-center justify-between rounded border border-line-subtle px-2.5 py-1.5 font-mono text-xs">
              <span className="text-fg-2">{c.attribute}</span>
              <span><span className="text-healthy">{String(c.approved)}</span> <span className="text-fg-3">→</span> <span className="text-critical">{String(c.deployed)}</span></span>
            </li>
          ))}
        </ul>
      </div>
      <Diff left={d.approved_iac} right={d.deployed_config} />
      <div>
        <p className="micro mb-1.5">Remediation preview</p>
        <CodeBlock code={data.remediation_preview} language="bash" lineNumbers={false} />
      </div>
    </div>
  );
}
