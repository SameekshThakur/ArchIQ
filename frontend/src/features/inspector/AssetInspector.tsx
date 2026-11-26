import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Crosshair, Network } from 'lucide-react';
import { useGet } from '@/api/hooks';
import type { Asset, ChainNode, Severity } from '@/api/types';
import { Badge, SeverityBadge, severityTone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Tabs } from '@/components/ui/Inputs';
import { KeyValueList, ScoreRing, SkeletonBlock, EmptyState } from '@/components/ui/Panel';
import { TagList } from '@/components/ui/Timeline';
import { RefLink } from '@/components/Ref';
import { useUI } from '@/store/ui';
import { fmtNum, titleCase } from '@/lib/format';
import type { InspectorProps } from './registry';

interface Neighbor {
  rel: string;
  style?: string | null;
  asset: Asset;
}
interface Detail {
  asset: Asset;
  record: Record<string, unknown>;
  neighbors: { outgoing: Neighbor[]; incoming: Neighbor[] };
  findings: { id: string; title: string; severity: Severity; category: string }[];
  drift: { id: string; summary: string; severity: Severity; status: string }[];
  documents: { id: string; title: string; status: string; updated_at: string }[];
  debt: { overall: number; scores: Record<string, number>; why: Record<string, string[]> } | null;
  impact: { direct: number; indirect: number; workflows: number; risk: number; rating: string } | null;
  chain: ChainNode[];
}

const HIDE = new Set(['id', 'name', 'description', 'capabilities', 'consumers', 'contract', 'tags', 'steps', 'apps', 'apis', 'approved', 'deployed', 'drift_meta']);

function Rel({ n }: { n: Neighbor }) {
  return (
    <li className="flex items-center justify-between gap-2 rounded border border-line-subtle px-2.5 py-1.5 text-xs">
      <span className="min-w-0 truncate">
        <RefLink type={n.asset.type} id={n.asset.id} name={n.asset.name} />
        <span className="ml-1.5 text-fg-3">{n.asset.type}</span>
      </span>
      <Badge mono>{n.style ? `${n.rel} · ${n.style.replace(/_/g, ' ')}` : n.rel.replace(/_/g, ' ')}</Badge>
    </li>
  );
}

export default function AssetInspector({ id }: InspectorProps) {
  const { data, isLoading, error } = useGet<Detail>(`/assets/${id}`);
  const [tab, setTab] = useState('overview');
  const close = useUI((s) => s.closeInspector);
  if (isLoading) return <SkeletonBlock className="h-80" />;
  if (error || !data) return <EmptyState title="Asset not found" description={(error as Error)?.message} />;
  const a = data.asset;
  const rows = Object.entries(data.record)
    .filter(([k, v]) => !HIDE.has(k) && v !== null && v !== '' && typeof v !== 'object')
    .slice(0, 18)
    .map(([k, v]) => ({ label: titleCase(k), value: typeof v === 'number' ? fmtNum(v) : String(v), mono: /id$|key$|repo/.test(k) }));
  const desc = typeof data.record.description === 'string' ? data.record.description : null;
  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="accent">{a.type}</Badge>
          <Badge tone={severityTone(a.criticality)}>{a.criticality}</Badge>
          <Badge tone={a.lifecycle === 'eol' || a.lifecycle === 'retired' ? 'critical' : a.lifecycle === 'extended' ? 'high' : 'healthy'}>{a.lifecycle}</Badge>
          {a.domain && <Badge>{a.domain}</Badge>}
        </div>
        <h3 className="mt-2 text-lg font-semibold text-fg">{a.name}</h3>
        {desc && <p className="mt-1 text-sm text-fg-2">{desc}</p>}
        {a.tech.length > 0 && <div className="mt-2"><TagList tags={a.tech} /></div>}
        <div className="mt-3 flex flex-wrap gap-2">
          <Link to={`/graph?focus=${a.id}`} onClick={close}>
            <Button size="sm" variant="secondary" leading={<Network className="h-3.5 w-3.5" />}>Open in graph</Button>
          </Link>
          {['application', 'api', 'database'].includes(a.type) && (
            <Link to={`/impact?asset=${a.id}`} onClick={close}>
              <Button size="sm" variant="secondary" leading={<Crosshair className="h-3.5 w-3.5" />}>Impact analysis</Button>
            </Link>
          )}
        </div>
      </div>
      <Tabs
        value={tab}
        onValueChange={setTab}
        items={[
          {
            value: 'overview',
            label: 'Overview',
            content: (
              <div className="space-y-4 pt-3">
                {(data.debt || data.impact) && (
                  <div className="flex items-center gap-4 rounded-lg border border-line bg-bg p-3">
                    {data.debt && <ScoreRing score={data.debt.overall} size={72} label="debt" invert />}
                    <div className="grid flex-1 grid-cols-2 gap-x-4 gap-y-1 text-xs">
                      {data.impact && (
                        <>
                          <span className="text-fg-3">Direct dependents</span>
                          <span className="num font-mono text-fg">{data.impact.direct}</span>
                          <span className="text-fg-3">Workflows</span>
                          <span className="num font-mono text-fg">{data.impact.workflows}</span>
                          <span className="text-fg-3">Blast radius</span>
                          <span className="num font-mono text-fg">{data.impact.risk}/100 · {data.impact.rating}</span>
                        </>
                      )}
                    </div>
                  </div>
                )}
                <KeyValueList items={[{ label: 'Owner', value: a.owner ? `${a.owner.name} · ${a.owner.team}` : '—' }, ...rows]} />
                {data.chain.length > 1 && (
                  <div>
                    <p className="micro mb-2">Dependency chain</p>
                    <div className="flex flex-wrap items-center gap-1.5 text-xs">
                      {data.chain.map((c, i) => (
                        <span key={c.id} className="flex items-center gap-1.5">
                          {i > 0 && <ArrowRight className="h-3 w-3 text-fg-3" aria-hidden />}
                          <RefLink type={c.type === 'Data' ? 'database' : 'application'} id={c.id} name={c.name} />
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ),
          },
          {
            value: 'deps',
            label: 'Dependencies',
            count: data.neighbors.outgoing.length + data.neighbors.incoming.length,
            content: (
              <div className="space-y-4 pt-3">
                <div>
                  <p className="micro mb-1.5">Depends on ({data.neighbors.outgoing.length})</p>
                  <ul className="space-y-1">{data.neighbors.outgoing.map((n) => <Rel key={`${n.rel}${n.asset.id}`} n={n} />)}</ul>
                </div>
                <div>
                  <p className="micro mb-1.5">Used by ({data.neighbors.incoming.length})</p>
                  <ul className="space-y-1">{data.neighbors.incoming.map((n) => <Rel key={`${n.rel}${n.asset.id}`} n={n} />)}</ul>
                </div>
              </div>
            ),
          },
          {
            value: 'findings',
            label: 'Findings',
            count: data.findings.length + data.drift.length,
            content: (
              <ul className="space-y-1.5 pt-3">
                {data.findings.map((f) => (
                  <li key={f.id} className="flex items-start justify-between gap-2 rounded border border-line-subtle px-2.5 py-2 text-xs">
                    <RefLink type="finding" id={f.id} name={f.title} />
                    <SeverityBadge severity={f.severity} />
                  </li>
                ))}
                {data.drift.map((d) => (
                  <li key={d.id} className="flex items-start justify-between gap-2 rounded border border-line-subtle px-2.5 py-2 text-xs">
                    <RefLink type="drift" id={d.id} name={d.summary} />
                    <SeverityBadge severity={d.severity} />
                  </li>
                ))}
                {!data.findings.length && !data.drift.length && <p className="text-xs text-fg-3">No open findings or drift.</p>}
              </ul>
            ),
          },
          {
            value: 'docs',
            label: 'Documents',
            count: data.documents.length,
            content: (
              <ul className="space-y-1.5 pt-3">
                {data.documents.map((d) => (
                  <li key={d.id} className="flex items-center justify-between gap-2 rounded border border-line-subtle px-2.5 py-2 text-xs">
                    <RefLink type="document" id={d.id} name={d.title} />
                    <Badge tone={d.status === 'Outdated' || d.status === 'Superseded' ? 'high' : 'neutral'}>{d.status}</Badge>
                  </li>
                ))}
                {!data.documents.length && <p className="text-xs text-fg-3">No document mentions this asset.</p>}
              </ul>
            ),
          },
        ]}
      />
    </div>
  );
}
