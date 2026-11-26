import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Cloud, Database, FileText, GitBranch, ListTodo, Plug, RefreshCw, ShieldCheck } from 'lucide-react';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { Panel, MetricTile, EmptyState } from '@/components/ui/Panel';
import { Badge, type Tone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { useUI } from '@/store/ui';
import { ApiError } from '@/api/client';
import { useConnectionActions, useConnections, type Connection, type LiveDrift, type Status } from './api';
import { ConnectionDrawer } from './ConnectionDrawer';

const ICON = { cmdb: Database, work: ListTodo, cloud: Cloud, code: GitBranch, docs: FileText } as const;
const STATUS: Record<Status, { label: string; tone: Tone }> = {
  not_connected: { label: 'Not connected', tone: 'neutral' },
  configured: { label: 'Saved, not synced', tone: 'medium' },
  connected: { label: 'Connected', tone: 'healthy' },
  demo: { label: 'Not live', tone: 'neutral' },
  error: { label: 'Error', tone: 'critical' },
};

function when(at?: string | null) {
  if (!at) return '';
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? at : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function message(e: unknown) {
  return e instanceof ApiError ? e.message : (e as Error).message;
}

export default function ConnectionsPage() {
  const { data, isLoading } = useConnections();
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const { sync } = useConnectionActions();
  const toast = useUI((s) => s.toast);

  const runSync = async (c: Connection) => {
    setBusy(c.id);
    try {
      const r = await sync(c.id);
      toast(r.ok ? { title: `${c.name} synced`, description: r.headline, tone: 'success' } : { title: `${c.name} sync failed`, description: r.error ?? undefined, tone: 'error' });
    } catch (e) {
      toast({ title: `${c.name} sync failed`, description: message(e), tone: 'error' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Page>
      <PageHeader
        title="Connections"
        description="Connect the platforms ArchIQ reads from. Every connection is read-only: ArchIQ never changes anything in the platform. Offline mode runs the same flow when a live connection is not active."
      />
      <p className="mb-4 rounded-md border border-line bg-raised px-3 py-2 text-sm text-fg-2" data-testid="connections-hint">
        Connected tools feed an analysis. To see what they bring on the other pages, tick them in <Link to="/start" className="text-accent underline">a new analysis</Link>. Syncing here only checks that the connection works.
      </p>
      {data && (
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricTile label="Platforms" value={data.summary.total} />
          <MetricTile label="Configured platforms" value={data.summary.connected} />
          <MetricTile label="With errors" value={data.summary.errors} />
          <MetricTile label="Live drift items" value={data.drift ? data.drift.drifted : '–'} hint={data.drift ? `${data.drift.compared} resources compared` : 'Sync Azure and GitHub'} />
        </div>
      )}
      {isLoading && <p className="text-sm text-fg-3">Loading connections…</p>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" role="list" aria-label="Platforms">
        {data?.items.map((c) => {
          const Icon = ICON[c.category];
          const st = STATUS[c.status];
          return (
            <section key={c.id} role="listitem" aria-labelledby={`conn-${c.id}`} className="flex flex-col rounded-lg border border-line bg-surface p-4">
              <div className="flex items-start gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-line bg-raised text-fg-2" aria-hidden>
                  <Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <h2 id={`conn-${c.id}`} className="text-sm font-semibold text-fg">{c.name}</h2>
                  <p className="text-xs text-fg-3">{c.vendor}</p>
                </div>
                <Badge tone={st.tone} dot>{st.label}</Badge>
              </div>
              <p className="mt-3 text-sm text-fg-2">{c.description}</p>
              <ul className="mt-2 space-y-1 text-xs text-fg-3">
                {c.provides.map((p) => (
                  <li key={p} className="flex gap-1.5"><span aria-hidden>→</span>{p}</li>
                ))}
              </ul>
              <div className="mt-auto pt-4">
                {c.last_sync ? (
                  <p className={c.last_sync.ok ? 'text-xs text-fg-3' : 'text-xs text-critical'}>
                    {c.last_sync.ok ? `Last sync ${when(c.last_sync.at)}: ${c.last_sync.headline}` : `Last sync failed: ${c.last_sync.error}`}
                  </p>
                ) : (
                  <p className="text-xs text-fg-3">{c.configured ? 'Not synced yet' : 'Not set up'}</p>
                )}
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant="secondary" leading={<Plug className="h-3.5 w-3.5" />} onClick={() => setOpen(c.id)}>
                    {c.configured ? 'Settings' : 'Connect'}
                  </Button>
                  {c.configured && (
                    <Button size="sm" variant="primary" loading={busy === c.id} leading={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => runSync(c)} aria-label={`Sync ${c.name} now`}>
                      Sync now
                    </Button>
                  )}
                </div>
              </div>
            </section>
          );
        })}
      </div>
      {data && <DriftPanel drift={data.drift} />}
      <ConnectionDrawer id={open} onClose={() => setOpen(null)} />
    </Page>
  );
}

function DriftPanel({ drift }: { drift: LiveDrift | null }) {
  if (!drift)
    return (
      <Panel className="mt-6" title="Live drift" description="Approved infrastructure code from GitHub compared with what Azure reports as deployed.">
        <EmptyState icon={<ShieldCheck className="h-5 w-5" />} title="Sync both Azure and GitHub to see live drift" description="Resources are matched by name; any setting that differs is listed here." />
      </Panel>
    );
  return (
    <Panel
      className="mt-6"
      title="Live drift"
      description={`${drift.compared} resources matched between GitHub (approved) and Azure (deployed); ${drift.drifted} differ.${drift.mode === 'demo' ? ' Offline snapshot.' : ''}`}
    >
      {drift.items.length === 0 ? (
        <p className="text-sm text-fg-2">Every matched resource is deployed as approved.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Resources whose deployed settings differ from the approved code</caption>
            <thead className="text-xs text-fg-3">
              <tr><th className="py-1.5 pr-3 font-medium">Resource</th><th className="py-1.5 pr-3 font-medium">Type</th><th className="py-1.5 pr-3 font-medium">Setting</th><th className="py-1.5 pr-3 font-medium">Approved</th><th className="py-1.5 font-medium">Deployed</th></tr>
            </thead>
            <tbody className="divide-y divide-line-subtle">
              {drift.items.slice(0, 15).flatMap((it) =>
                it.changes.map((ch, k) => (
                  <tr key={`${it.name}-${ch.attribute}`}>
                    <td className="py-1.5 pr-3 font-mono text-xs">{k === 0 ? it.name : ''}</td>
                    <td className="py-1.5 pr-3 text-xs text-fg-3">{k === 0 ? it.type.replace(/_/g, ' ') : ''}</td>
                    <td className="py-1.5 pr-3 text-xs">{ch.attribute.replace(/_/g, ' ')}</td>
                    <td className="py-1.5 pr-3 font-mono text-xs">{String(ch.approved)}</td>
                    <td className="py-1.5 font-mono text-xs text-critical">{String(ch.deployed)}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
          {drift.items.length > 15 && <p className="mt-2 text-xs text-fg-3">Showing 15 of {drift.items.length} drifted resources.</p>}
        </div>
      )}
    </Panel>
  );
}
