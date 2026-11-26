import { useMemo, useState } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { ArrowLeft, ArrowRight, ExternalLink, Network } from 'lucide-react';
import type { GraphData, GraphNode } from '@/api/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import { relationLabel } from './filter';

const TYPE_LABEL: Record<string, string> = { App: 'Application', API: 'API', Data: 'Data store', Capability: 'Capability', Owner: 'Owner', Cloud: 'Cloud resource' };
const TONE: Record<string, 'critical' | 'high' | 'medium' | 'low' | 'neutral'> = { critical: 'critical', high: 'high', medium: 'medium', low: 'low' };

/**
 * The graph as a table, for anyone who cannot or would rather not use the canvas. It shows exactly the nodes the filters leave,
 * and selecting a row lists that node's connections, each of which can be followed to the node at the other end.
 */
export function NodeTable({ graph, selectedId, onSelect, onOpen, onShowInGraph, maxHeight }: {
  graph: GraphData;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpen: (id: string) => void;
  onShowInGraph: (id: string) => void;
  maxHeight: number;
}) {
  const [q, setQ] = useState('');
  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? graph.nodes.filter((n) => n.name.toLowerCase().includes(s) || (n.domain ?? '').toLowerCase().includes(s)) : graph.nodes;
  }, [graph.nodes, q]);
  const byId = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph.nodes]);
  const selected = selectedId ? byId.get(selectedId) : undefined;

  const cols = useMemo<ColumnDef<GraphNode>[]>(() => [
    { accessorKey: 'name', header: 'Name', size: 230, cell: (c) => <span className="font-medium text-fg">{c.getValue<string>()}</span> },
    { accessorKey: 'type', header: 'Type', size: 110, cell: (c) => <span className="text-fg-2">{TYPE_LABEL[c.getValue<string>()] ?? c.getValue<string>()}</span> },
    { accessorKey: 'domain', header: 'Domain', size: 150, cell: (c) => <span className="text-fg-2">{c.getValue<string | null>() ?? '—'}</span> },
    { accessorKey: 'criticality', header: 'Criticality', size: 100, cell: (c) => { const v = c.getValue<string | null>(); return v ? <Badge tone={TONE[v] ?? 'neutral'}>{v}</Badge> : <span className="text-fg-3">—</span>; } },
    { accessorKey: 'lifecycle', header: 'Lifecycle', size: 100, cell: (c) => <span className="capitalize text-fg-2">{c.getValue<string>() || '—'}</span> },
    { accessorKey: 'degree', header: 'Links', size: 70, cell: (c) => <span className="num font-mono text-xs">{c.getValue<number>()}</span> },
  ], []);

  const links = useMemo(() => {
    if (!selected) return [];
    const out: { key: string; rel: string; dir: 'out' | 'in'; other: GraphNode }[] = [];
    for (const e of graph.edges) {
      if (e.source === selected.id) { const o = byId.get(e.target); if (o) out.push({ key: e.id, rel: e.rel, dir: 'out', other: o }); }
      else if (e.target === selected.id) { const o = byId.get(e.source); if (o) out.push({ key: e.id, rel: e.rel, dir: 'in', other: o }); }
    }
    return out.sort((a, b) => a.rel.localeCompare(b.rel) || a.other.name.localeCompare(b.other.name));
  }, [graph.edges, selected, byId]);
  const grouped = useMemo(() => {
    const m = new Map<string, typeof links>();
    for (const l of links) (m.get(l.rel) ?? m.set(l.rel, []).get(l.rel)!).push(l);
    return [...m.entries()];
  }, [links]);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-3 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]" data-testid="node-table">
      <div className="min-w-0 space-y-2">
        <div className="flex items-center gap-3">
          <label htmlFor="node-table-filter" className="sr-only">Filter the table by name or domain</label>
          <input id="node-table-filter" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by name or domain" className="h-8 w-64 max-w-full rounded border border-line bg-bg px-2.5 text-sm text-fg placeholder:text-fg-3 hover:border-fg-3/40 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30" />
          <p className="text-xs text-fg-3" role="status"><span className="num font-mono text-fg-2">{rows.length}</span> of <span className="num font-mono text-fg-2">{graph.nodes.length}</span> nodes</p>
        </div>
        <DataTable data={rows} columns={cols} getRowId={(r) => r.id} selectedId={selectedId} onRowClick={(r) => onSelect(r.id)} maxHeight={maxHeight} rowHeight={40} initialSort={[{ id: 'degree', desc: true }]} ariaLabel="Graph nodes" empty={<p className="text-sm text-fg-3">No nodes match. Clear the filter or the toolbar filters.</p>} />
      </div>

      <aside className="min-w-0 rounded-lg border border-line bg-surface p-4" aria-label="Connections of the selected node">
        {!selected ? (
          <p className="text-sm text-fg-3">Select a row to see what that node is connected to, and to follow those connections.</p>
        ) : (
          <div>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0"><h3 className="truncate text-sm font-semibold text-fg">{selected.name}</h3><p className="text-xs text-fg-3">{TYPE_LABEL[selected.type] ?? selected.type}{selected.domain ? ` · ${selected.domain}` : ''} · {links.length} connection{links.length === 1 ? '' : 's'}</p></div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" leading={<ExternalLink className="h-3 w-3" aria-hidden />} onClick={() => onOpen(selected.id)}>Open details</Button>
              <Button size="sm" variant="ghost" leading={<Network className="h-3 w-3" aria-hidden />} onClick={() => onShowInGraph(selected.id)}>Show in graph</Button>
            </div>
            <div className="mt-3 max-h-[420px] space-y-3 overflow-auto pr-1">
              {grouped.map(([rel, items]) => (
                <section key={rel} aria-label={`${relationLabel(rel)}, ${items.length}`}>
                  <h4 className="micro mb-1">{relationLabel(rel)} <span className="num font-mono normal-case text-fg-3">{items.length}</span></h4>
                  <ul className="space-y-0.5">
                    {items.map((l) => (
                      <li key={l.key}>
                        <button type="button" onClick={() => onSelect(l.other.id)} className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm text-fg-2 hover:bg-raised hover:text-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
                          {l.dir === 'out' ? <ArrowRight className="h-3 w-3 shrink-0 text-fg-3" aria-label="to" /> : <ArrowLeft className="h-3 w-3 shrink-0 text-fg-3" aria-label="from" />}
                          <span className="min-w-0 flex-1 truncate">{l.other.name}</span>
                          <span className="text-xs text-fg-3">{TYPE_LABEL[l.other.type] ?? l.other.type}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
              {!links.length && <p className="text-sm text-fg-3">Nothing is connected to this node with the current filters.</p>}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
