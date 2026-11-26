import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Crosshair, ExternalLink, X } from 'lucide-react';
import { api, useGet } from '@/api/hooks';
import type { Asset, GraphData, GraphNode, GraphView, Paged, PathNode } from '@/api/types';
import { LazyForce } from '@/components/viz/LazyChart';
import type { GraphHandle } from '@/components/viz/ForceGraph';
import { downloadBlob, exportFileName } from '@/components/viz/graphExport';
import { RefLink } from '@/components/Ref';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { SearchInput, SegmentedControl, Select } from '@/components/ui/Inputs';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { Panel, Skeleton } from '@/components/ui/Panel';
import { useUI } from '@/store/ui';
import { cn } from '@/lib/cn';
import { bubbleDomain, collapseGraph, isBubble } from './collapse';
import { criticalityCounts, domainCounts, filterGraph, isFiltered, relationCounts, relationLabel } from './filter';
import { NodeTable } from './NodeTable';
import { GraphToolbar } from './GraphToolbar';

const LAYERS = [
  { key: 'app', label: 'Applications', dot: 'bg-accent' },
  { key: 'api', label: 'APIs', dot: 'bg-low' },
  { key: 'data', label: 'Data stores', dot: 'bg-medium' },
  { key: 'capability', label: 'Capabilities', dot: 'bg-healthy' },
  { key: 'cloud', label: 'Cloud resources', dot: 'bg-high' },
  { key: 'owner', label: 'Owners', dot: 'bg-fg-3' },
];

export default function GraphPage() {
  const [sp, setSp] = useSearchParams();
  const focus = sp.get('focus');
  const [layers, setLayers] = useState<string[]>(['app', 'data']);
  const [hops, setHops] = useState(2);
  const [colorBy, setColorBy] = useState<'type' | 'criticality' | 'lifecycle'>('type');
  // arriving from the start page's results opens the graph already narrowed to the chosen domain
  const [filterDomains, setFilterDomains] = useState<string[]>(() => { const d = sp.get('domain'); return d ? [d] : []; });
  const [filterCrit, setFilterCrit] = useState<string[]>([]);
  const [filterRel, setFilterRel] = useState<string[]>([]);
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [view, setView] = useState<'graph' | 'table'>('graph');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [card, setCard] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [nativeFull, setNativeFull] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const stage = useRef<HTMLDivElement>(null);
  const handle = useRef<GraphHandle>(null);
  const [search, setSearch] = useState('');
  const [pathTo, setPathTo] = useState('');
  const openInspector = useUI((s) => s.openInspector);

  const graph = useGet<GraphData>('/graph', { layers: layers.join(','), focus: focus ?? undefined, hops });
  const hubs = useGet<{ hubs: { app_id: string; name: string; degree: number; betweenness: number }[]; spofs: { app_id: string; name: string; score: number; reasons: string[] }[] }>('/graph/hubs');
  const found = useGet<Paged<Asset>>('/assets', { q: search, type: 'application,api,database', page_size: 6 }, { enabled: search.length >= 2 });
  const path = useGet<{ path: PathNode[]; hops: number; found: boolean }>('/graph/path', { source: focus ?? '', target: pathTo }, { enabled: !!focus && !!pathTo });
  const focusAsset = useGet<{ asset: Asset }>(`/assets/${focus}`, undefined, { enabled: !!focus });

  const views = useGet<{ items: GraphView[] }>('/graph/views');

  const filter = useMemo(() => ({ domains: filterDomains, criticality: filterCrit, relations: filterRel }), [filterDomains, filterCrit, filterRel]);
  // the real nodes the filters leave: what the table lists, what search looks through, and what the counts describe
  // (with every layer off the server would fall back to its default set, so an empty selection is answered here instead)
  const filtered = useMemo<GraphData | undefined>(() => {
    if (layers.length === 0) return { nodes: [], edges: [], total_nodes: 0, total_edges: 0 } as unknown as GraphData;
    return graph.data ? filterGraph(graph.data, filter) : undefined;
  }, [graph.data, filter, layers]);
  // and what the canvas draws: the same, with folded domains standing in as single bubbles
  const shownGraph = useMemo(() => (filtered ? collapseGraph(filtered, collapsed) : undefined), [filtered, collapsed]);
  const domainOpts = useMemo(() => (graph.data ? domainCounts(graph.data) : []), [graph.data]);
  const critOpts = useMemo(() => (graph.data ? criticalityCounts(graph.data) : []), [graph.data]);
  const relOpts = useMemo(() => (graph.data ? relationCounts(graph.data) : []), [graph.data]);
  const full = nativeFull || expanded;
  const byId = useMemo(() => new Map(filtered?.nodes.map((n) => [n.id, n]) ?? []), [filtered]);

  const highlight = useMemo(() => new Set(path.data?.path.map((p) => p.id) ?? []), [path.data]);
  const setFocus = (id: string | null) => {
    const n = new URLSearchParams(sp);
    if (id) n.set('focus', id);
    else n.delete('focus');
    setSp(n, { replace: true });
    setPathTo('');
  };

  const flash = useCallback((text: string) => { setNotice(text); window.setTimeout(() => setNotice((n) => (n === text ? null : n)), 4000); }, []);

  // full screen: the browser's own fullscreen where it exists, otherwise the stage fills the window
  useEffect(() => {
    const on = () => setNativeFull(document.fullscreenElement === stage.current);
    document.addEventListener('fullscreenchange', on);
    return () => document.removeEventListener('fullscreenchange', on);
  }, []);
  useEffect(() => {
    if (!expanded) return;
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setExpanded(false); };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, [expanded]);
  useEffect(() => { const t = window.setTimeout(() => handle.current?.fit(), 350); return () => window.clearTimeout(t); }, [full]);
  const toggleFullscreen = async () => {
    if (nativeFull) { await document.exitFullscreen().catch(() => undefined); return; }
    if (expanded) { setExpanded(false); return; }
    const el = stage.current;
    if (el?.requestFullscreen) {
      try { await el.requestFullscreen(); return; } catch { /* fall through to the in-page version */ }
    }
    setExpanded(true);
  };

  const toggleDomain = useCallback((d: string) => {
    setCollapsed((c) => (c.includes(d) ? c.filter((x) => x !== d) : [...c, d]));
    setCard(null);
  }, []);
  /** Selects a node and flies to it, opening its domain first if it is folded away. */
  const pick = (n: GraphNode) => {
    setSelectedId(n.id);
    const hidden = !!n.domain && collapsed.includes(n.domain);
    if (hidden) setCollapsed((c) => c.filter((x) => x !== n.domain));
    const go = () => { if (!handle.current?.zoomToNode(n.id)) flash('That node is not on the canvas yet. Try again in a moment.'); };
    if (hidden) window.setTimeout(go, 1300); // after the unfolded layout has settled
    else go();
  };
  const showInGraph = (id: string) => {
    const n = byId.get(id);
    setView('graph');
    if (n) window.setTimeout(() => pick(n), 450); // the canvas has to be visible again before it can fly anywhere
  };
  const clearSelection = () => { setSelectedId(null); setCard(null); };
  const onNodeClick = (id: string) => {
    if (isBubble(id)) { toggleDomain(bubbleDomain(id)); return; } // a folded domain opens when clicked
    if (full) { setCard(id); setSelectedId(id); }
    else openInspector({ kind: 'asset', id });
  };
  const openDetails = (id: string) => {
    const go = () => openInspector({ kind: 'asset', id });
    if (nativeFull) void document.exitFullscreen().then(go, go);
    else { setExpanded(false); go(); }
  };

  const exportMeta = useMemo(() => ({
    title: 'Knowledge graph',
    subtitle: [`${filtered?.nodes.length ?? 0} nodes`, `${filtered?.edges.length ?? 0} edges`, collapsed.length ? `${collapsed.length} domain${collapsed.length === 1 ? '' : 's'} folded` : null, focus ? `focused on ${focusAsset.data?.asset.name ?? focus}` : null, filterDomains.length ? `domains: ${filterDomains.join(', ')}` : null, filterCrit.length ? `criticality: ${filterCrit.join(', ')}` : null, filterRel.length ? `relationships: ${filterRel.map(relationLabel).join(', ')}` : null, new Date().toISOString().slice(0, 10)].filter(Boolean).join(' · '),
  }), [filtered, collapsed, focus, focusAsset.data, filterDomains, filterCrit, filterRel]);
  const exportGraph = async (kind: 'png' | 'svg' | 'csv') => {
    const h = handle.current;
    setExporting(true);
    try {
      if (kind === 'csv') {
        const cell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
        const lines = [['id', 'name', 'type', 'domain', 'criticality', 'lifecycle', 'links'].join(',')];
        for (const n of filtered?.nodes ?? []) lines.push([n.id, n.name, n.type, n.domain, n.criticality, n.lifecycle, n.degree].map(cell).join(','));
        downloadBlob(new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }), exportFileName('csv'));
        flash('CSV saved to your downloads.');
      } else if (!h) { return; }
      else if (kind === 'png') { downloadBlob(await h.exportPng(), exportFileName('png')); flash('PNG saved to your downloads.'); }
      else { downloadBlob(new Blob([h.exportSvg()], { type: 'image/svg+xml;charset=utf-8' }), exportFileName('svg')); flash('SVG saved to your downloads.'); }
    } catch (e) { flash(`Export failed: ${(e as Error).message}`); }
    finally { setExporting(false); }
  };

  const saveView = async (name: string): Promise<string | null> => {
    try {
      await api('/graph/views', { method: 'POST', body: { name, layers, hops, color_by: colorBy, focus, domains: filterDomains, criticality: filterCrit, relations: filterRel, collapsed } });
      await views.refetch();
      return null;
    } catch (e) { return (e as Error).message; }
  };
  const applyView = (v: GraphView) => {
    setLayers(v.layers.length ? v.layers : ['app', 'data']);
    setHops(v.hops);
    setColorBy(v.color_by);
    setFilterDomains(v.domains);
    setFilterCrit(v.criticality);
    setFilterRel(v.relations ?? []);
    setCollapsed(v.collapsed ?? []);
    clearSelection();
    setFocus(v.focus ?? null);
    flash(`Applied view “${v.name}”.`);
  };
  const deleteView = async (v: GraphView) => {
    try { await api(`/graph/views/${v.id}`, { method: 'DELETE' }); await views.refetch(); } catch (e) { flash(`Could not delete the view: ${(e as Error).message}`); }
  };
  const clearFilters = () => { setFilterDomains([]); setFilterCrit([]); setFilterRel([]); };
  const cardNode = card ? byId.get(card) : undefined;
  const stageHeight = Math.max(520, Math.min(680, typeof window === 'undefined' ? 600 : window.innerHeight - 260));

  return (
    <Page wide>
      <PageHeader
        title="Knowledge graph"
        description="The living architecture graph: applications, APIs, data stores, capabilities and owners, with every dependency the platform has discovered."
        secondary={shownGraph && <span className="text-xs text-fg-3"><span className="num font-mono text-fg-2">{shownGraph.nodes.length}</span> nodes · <span className="num font-mono text-fg-2">{shownGraph.edges.length}</span> edges</span>}
      />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[280px_minmax(0,1fr)_300px]">
        <div className="space-y-4">
          <Panel title="Find and focus">
            <div className="space-y-3">
              <div className="relative">
                <SearchInput value={search} onChange={setSearch} placeholder="Find an asset" />
                {search.length >= 2 && found.data && (
                  <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-line bg-overlay shadow-lg">
                    {found.data.items.map((a) => (
                      <li key={a.id}><button type="button" className="flex w-full items-center justify-between px-3 py-1.5 text-left text-xs hover:bg-raised" onClick={() => { setFocus(a.id); setSearch(''); }}><span className="truncate text-fg">{a.name}</span><Badge>{a.type}</Badge></button></li>
                    ))}
                    {!found.data.items.length && <li className="px-3 py-2 text-xs text-fg-3">No matches</li>}
                  </ul>
                )}
              </div>
              {focus && (
                <div className="rounded-md border border-accent/30 bg-accent/5 p-2.5 text-xs">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0"><p className="micro">Focused</p><p className="truncate text-sm font-medium text-fg">{focusAsset.data?.asset.name ?? focus}</p></div>
                    <button type="button" aria-label="Clear focus" onClick={() => setFocus(null)} className="text-fg-3 hover:text-fg"><X className="h-4 w-4" /></button>
                  </div>
                  <div className="mt-2 flex items-center justify-between"><span className="text-fg-3">Hops</span><SegmentedControl size="sm" label="Hops" value={String(hops) as '1'} onChange={(v) => setHops(Number(v))} options={['1', '2', '3'].map((v) => ({ value: v as '1', label: v }))} /></div>
                  <div className="mt-2"><p className="micro mb-1">Trace path to</p>
                    <PathPicker value={pathTo} onChange={setPathTo} /></div>
                  {path.data && (
                    <div className="mt-2 text-fg-2">{path.data.found ? <ol className="space-y-0.5">{path.data.path.map((p) => <li key={p.id}>{p.rel && <span className="text-fg-3">↳ {p.rel} </span>}<RefLink type={p.type === 'Data' ? 'database' : 'application'} id={p.id} name={p.name} /></li>)}</ol> : 'No path found.'}</div>
                  )}
                </div>
              )}
            </div>
          </Panel>
        </div>

                    <div className="min-w-0">
          <div ref={stage} className={cn('min-w-0', full && 'flex flex-col gap-2 bg-bg p-3', nativeFull && 'h-screen w-screen', expanded && 'fixed inset-0 z-[55] h-screen')}>
            <GraphToolbar
              nodes={filtered?.nodes ?? []}
              shown={filtered?.nodes.length ?? 0}
              total={graph.data?.nodes.length ?? 0}
              layerDefs={LAYERS}
              layers={layers}
              onLayers={setLayers}
              colorBy={colorBy}
              onColorBy={setColorBy}
              domains={domainOpts}
              criticalities={critOpts}
              filterDomains={filterDomains}
              filterCrit={filterCrit}
              onDomains={setFilterDomains}
              onCrit={setFilterCrit}
              onClearFilters={clearFilters}
              relations={relOpts}
              filterRelations={filterRel}
              onRelations={setFilterRel}
              collapsed={collapsed}
              onCollapsed={setCollapsed}
              view={view}
              onView={setView}
              onPick={pick}
              selectedName={selectedId ? byId.get(selectedId)?.name ?? selectedId : null}
              onClearSelected={clearSelection}
              views={views.data?.items ?? []}
              onApplyView={applyView}
              onDeleteView={(v) => void deleteView(v)}
              onSaveView={saveView}
              onExport={(k) => void exportGraph(k)}
              exporting={exporting}
              fullscreen={full}
              onFullscreen={() => void toggleFullscreen()}
            />
            {view === 'table' && filtered && (
              <div className={cn(full ? 'min-h-0 flex-1 overflow-auto' : 'mt-3')}>
                <NodeTable
                  graph={filtered}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  onOpen={openDetails}
                  onShowInGraph={showInGraph}
                  maxHeight={full ? Math.max(320, (typeof window === 'undefined' ? 800 : window.innerHeight) - 260) : Math.min(560, stageHeight)}
                />
              </div>
            )}
            {view === 'graph' && !full && shownGraph && !collapsed.length && shownGraph.nodes.length > 300 && (
              <p className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-line bg-surface-2 px-3 py-1.5 text-xs text-fg-2" data-testid="fold-hint">
                {shownGraph.nodes.length} nodes is a lot to read at once. Folding domains into bubbles gives a clearer picture.
                <Button size="sm" onClick={() => setCollapsed(domainOpts.map(([d]) => d))}>Fold all domains</Button>
              </p>
            )}
            <div className={cn('relative', view === 'table' ? 'hidden' : full ? 'min-h-0 flex-1' : 'mt-3')}>
              {graph.isLoading || !shownGraph ? <Skeleton className={cn('w-full', full ? 'h-full' : 'h-[calc(100vh-260px)] min-h-[520px]')} /> : (
                <Suspense fallback={<Skeleton className="h-[calc(100vh-260px)] min-h-[520px] w-full" />}>
                  <LazyForce ref={handle} data={shownGraph} height={full ? 'fill' : stageHeight} focusId={focus} selectedId={selectedId} highlight={highlight} colorBy={colorBy} exportMeta={exportMeta} onNodeClick={onNodeClick} onBackgroundClick={clearSelection} onSelect={setSelectedId} onToggleDomain={toggleDomain} />
                </Suspense>
              )}
              {shownGraph && shownGraph.nodes.length === 0 && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="rounded-lg border border-line bg-surface/95 px-5 py-4 text-center shadow-pop">
                    <p className="text-sm font-medium text-fg">No nodes match</p>
                    <p className="mt-1 text-xs text-fg-3">{isFiltered(filter) ? 'The current filters leave nothing to show.' : 'Turn on at least one layer.'}</p>
                    {isFiltered(filter) && <Button size="sm" className="mt-3" onClick={clearFilters}>Clear filters</Button>}
                  </div>
                </div>
              )}
              {cardNode && full && (
                <div className="absolute bottom-3 right-3 w-72 rounded-lg border border-line bg-surface/95 p-3 text-xs shadow-pop backdrop-blur" role="dialog" aria-label={`${cardNode.name} details`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0"><p className="truncate text-sm font-medium text-fg">{cardNode.name}</p><p className="text-fg-3">{cardNode.type}{cardNode.domain ? ` · ${cardNode.domain}` : ''}</p></div>
                    <button type="button" aria-label="Close details" onClick={() => setCard(null)} className="text-fg-3 hover:text-fg"><X className="h-4 w-4" /></button>
                  </div>
                  <dl className="mt-2 grid grid-cols-3 gap-2 text-fg-3">
                    <div><dt className="micro">Links</dt><dd className="num font-mono text-fg-2">{cardNode.degree}</dd></div>
                    <div><dt className="micro">Criticality</dt><dd className="capitalize text-fg-2">{cardNode.criticality ?? '—'}</dd></div>
                    <div><dt className="micro">Lifecycle</dt><dd className="capitalize text-fg-2">{cardNode.lifecycle || '—'}</dd></div>
                  </dl>
                  <div className="mt-3 flex gap-2">
                    <Button size="sm" variant="primary" leading={<ExternalLink className="h-3 w-3" aria-hidden />} onClick={() => openDetails(cardNode.id)}>Open details</Button>
                    <Button size="sm" onClick={() => { setFocus(cardNode.id); setCard(null); }}>Focus here</Button>
                  </div>
                </div>
              )}
              {notice && <p role="status" className="absolute left-3 top-3 rounded-md border border-line bg-surface/95 px-3 py-1.5 text-xs text-fg shadow-sm backdrop-blur">{notice}</p>}
            </div>
            {!full && view === 'graph' && <p className="mt-2 text-xs text-fg-3">Applications are grouped by business domain. Hover a node to isolate its connections, click to inspect, scroll to zoom and drag to pan. Use Find in view to jump to a node, and the filters to narrow by domain, criticality or relationship. Click a domain name or press C to fold it into a bubble. With the graph focused, arrow keys move between connected nodes.</p>}
          </div>
        </div>

        <div className="space-y-4">
          <Panel title="Integration hubs" description="Highest coupling">
            <ul className="space-y-2">
              {hubs.data?.hubs.slice(0, 6).map((h) => (
                <li key={h.app_id} className="flex items-center justify-between gap-2 text-xs">
                  <RefLink type="application" id={h.app_id} name={h.name} />
                  <span className="flex items-center gap-2"><span className="num font-mono text-fg-3">{h.degree} links</span><button type="button" aria-label={`Focus ${h.name}`} onClick={() => setFocus(h.app_id)} className="text-fg-3 hover:text-accent"><Crosshair className="h-3.5 w-3.5" /></button></span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Single points of failure" description={`${hubs.data?.spofs.length ?? 0} detected`}>
            <ul className="space-y-2.5">
              {hubs.data?.spofs.slice(0, 6).map((s) => (
                <li key={s.app_id} className="text-xs">
                  <div className="flex items-center justify-between"><RefLink type="application" id={s.app_id} name={s.name} /><Badge tone={s.score >= 75 ? 'critical' : 'high'} mono>{s.score}</Badge></div>
                  <p className="mt-0.5 text-fg-3">{s.reasons[0]}</p>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </Page>
  );
}

function PathPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const apps = useGet<Paged<Asset>>('/assets', { type: 'application', page_size: 100 });
  return <Select label="Path target" value={value || 'none'} onValueChange={(v) => onChange(v === 'none' ? '' : v)} placeholder="Choose an application" options={[{ value: 'none', label: 'None' }, ...(apps.data?.items.map((a) => ({ value: a.id, label: a.name })) ?? [])]} />;
}

export { Button };
