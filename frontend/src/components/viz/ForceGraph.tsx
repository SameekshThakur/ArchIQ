import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d';
import { Maximize2, ZoomIn, ZoomOut } from 'lucide-react';
import { forwardRef, useCallback, useEffect, useId, useImperativeHandle, useMemo, useRef, useState } from 'react';
import type { GraphData } from '@/api/types';
import { useUI } from '@/store/ui';
import { buildSvg, composePng, nodeRadius, type ExportNode, type LegendItem } from './graphExport';
import { bubbleId } from '@/features/graph/collapse';
import { relationLabel } from '@/features/graph/filter';

const TYPE_COLOR: Record<string, string> = { Domain: 'accent', App: 'accent', API: 'low', Data: 'medium', Capability: 'healthy', Owner: 'fg-3', Cloud: 'high' };
const TYPE_LABEL: Record<string, string> = { Domain: 'Collapsed domain', App: 'Application', API: 'API', Data: 'Data store', Capability: 'Capability', Owner: 'Owner', Cloud: 'Cloud resource' };
const CRIT: Record<string, string> = { critical: 'critical', high: 'high', medium: 'medium', low: 'low' };
const LIFE: Record<string, string> = { eol: 'critical', extended: 'high', retired: 'critical', supported: 'healthy' };

interface N {
  id: string;
  name: string;
  type: string;
  domain?: string | null;
  degree: number;
  criticality?: string | null;
  lifecycle?: string;
  members?: number;
  memberIds?: string[];
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}
interface L {
  source: string | N;
  target: string | N;
  rel: string;
  count?: number;
  rels?: Record<string, number>;
}

const radius = (n: N) => nodeRadius(n);

/** "consumes", or "consumes ×12 · hosted on ×3" for a link that stands for several. */
const linkText = (l: L) => (l.rels ? Object.entries(l.rels).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([r, n]) => `${relationLabel(r).toLowerCase()} ×${n}`).join(' · ') : relationLabel(l.rel).toLowerCase());
/** Node names can come from uploaded files, so they are escaped before going into the HTML tooltip. */
const esc = (v: unknown) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
const endId = (e: string | N) => (typeof e === 'string' ? e : e.id);

/** Pulls each node toward its business-domain centre, so domains read as neighbourhoods rather than one hairball. */
function clusterForce(centres: Map<string, { x: number; y: number }>, strength: number) {
  let nodes: N[] = [];
  const force = (alpha: number) => {
    for (const n of nodes) {
      const c = centres.get(n.domain ?? '') ?? { x: 0, y: 0 };
      n.vx = (n.vx ?? 0) + (c.x - (n.x ?? 0)) * strength * alpha;
      n.vy = (n.vy ?? 0) + (c.y - (n.y ?? 0)) * strength * alpha;
    }
  };
  force.initialize = (ns: N[]) => { nodes = ns; };
  return force;
}

/** Keeps nodes from sitting on top of each other (and their labels), without pulling in another dependency. */
function collideForce(pad: number) {
  let nodes: N[] = [];
  const force = () => {
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = (b.x ?? 0) - (a.x ?? 0);
        let dy = (b.y ?? 0) - (a.y ?? 0);
        const min = radius(a) + radius(b) + pad;
        const d2 = dx * dx + dy * dy;
        if (d2 >= min * min) continue;
        const d = Math.sqrt(d2) || 0.01;
        if (d2 === 0) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; }
        const push = ((min - d) / d) * 0.5;
        a.vx = (a.vx ?? 0) - dx * push;
        a.vy = (a.vy ?? 0) - dy * push;
        b.vx = (b.vx ?? 0) + dx * push;
        b.vy = (b.vy ?? 0) + dy * push;
      }
    }
  };
  force.initialize = (ns: N[]) => { nodes = ns; };
  return force;
}

export interface GraphHandle {
  /** Centres and zooms on a node. Returns false when the node is not in the graph. */
  zoomToNode: (id: string) => boolean;
  fit: () => void;
  exportPng: () => Promise<Blob>;
  exportSvg: () => string;
}

/** Canvas force-directed graph, grouped by domain. Hubs are labelled; hover isolates a node's neighbourhood. */
const ForceGraphView = forwardRef<GraphHandle, {
  data: GraphData;
  /** Pixels, or 'fill' to take the height of the parent (used in full screen). */
  height: number | 'fill';
  focusId?: string | null;
  /** A node picked from search: kept isolated (like hover) until the background is clicked. */
  selectedId?: string | null;
  highlight?: Set<string>;
  onNodeClick?: (id: string) => void;
  onBackgroundClick?: () => void;
  /** Keyboard navigation moved the selection (null clears it). */
  onSelect?: (id: string | null) => void;
  /** A domain label was clicked, or C was pressed on a node: fold or unfold that domain. */
  onToggleDomain?: (domain: string) => void;
  colorBy?: 'type' | 'criticality' | 'lifecycle';
  exportMeta?: { title: string; subtitle: string };
}>(function ForceGraphView({
  data,
  height,
  focusId,
  selectedId,
  highlight,
  onNodeClick,
  onBackgroundClick,
  onSelect,
  onToggleDomain,
  colorBy = 'type',
  exportMeta,
}, handle) {
  const theme = useUI((s) => s.theme);
  const ref = useRef<ForceGraphMethods<N, L>>();
  const wrap = useRef<HTMLDivElement>(null);
  const animating = useRef(false);
  const hoverRef = useRef<string | null>(null);
  const pressAt = useRef<{ x: number; y: number } | null>(null);
  const labelBoxes = useRef<{ x: number; y: number; w: number; h: number }[]>([]);
  const [w, setW] = useState(800);
  const [measuredH, setMeasuredH] = useState(600);
  const [hover, setHover] = useState<string | null>(null);
  const [settled, setSettled] = useState(false);
  const [hoverLink, setHoverLink] = useState<L | null>(null);
  const [hoverDomain, setHoverDomain] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const [announce, setAnnounce] = useState('');
  const territories = useRef<{ d: string; cx: number; cy: number; r: number }[]>([]);
  // where every node last settled, so folding a domain or applying a filter moves things from where they were instead of starting over
  const posCache = useRef(new Map<string, { x: number; y: number }>());
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const measure = () => { setW(el.clientWidth); setMeasuredH(el.clientHeight); };
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    measure();
    return () => ro.disconnect();
  }, []);
  const h = height === 'fill' ? Math.max(240, measuredH) : height;

  const colors = useMemo(() => {
    void theme;
    // read each design token once per theme: getComputedStyle inside the per-node and per-link draw callbacks was the main cost of this view
    const style = getComputedStyle(document.documentElement);
    const raw = new Map<string, string>();
    const cache = new Map<string, string>();
    const c = (n: string, a = 1) => {
      const key = `${n}|${a}`;
      let v = cache.get(key);
      if (v === undefined) {
        let r = raw.get(n);
        if (r === undefined) { r = style.getPropertyValue(`--${n}`).trim().replace(/\s+/g, ' '); raw.set(n, r); }
        // comma syntax: the same string is written into exported SVGs, which older design tools only read this way
        const p = r.split(' ');
        v = p.length === 3 ? (a >= 1 ? `rgb(${p.join(',')})` : `rgba(${p.join(',')},${a})`) : `rgb(${r} / ${a})`;
        cache.set(key, v);
      }
      return v;
    };
    return { c, fg: c('fg'), bg: c('bg') };
  }, [theme]);

  const graph = useMemo(() => {
    const cache = posCache.current;
    const nodes = data.nodes.map((n) => {
      const c = { ...n } as N;
      const at = cache.get(n.id);
      if (at) { c.x = at.x; c.y = at.y; return c; }
      // a folded domain starts where its members were; an unfolded member starts where its domain was
      const seen = n.memberIds?.map((id) => cache.get(id)).filter(Boolean) as { x: number; y: number }[] | undefined;
      if (seen?.length) { c.x = seen.reduce((a, p) => a + p.x, 0) / seen.length; c.y = seen.reduce((a, p) => a + p.y, 0) / seen.length; return c; }
      const home = n.domain ? cache.get(bubbleId(n.domain)) : undefined;
      if (home) { c.x = home.x + (Math.random() - 0.5) * 24; c.y = home.y + (Math.random() - 0.5) * 24; }
      return c;
    }).sort((a, b) => b.degree - a.degree) as N[];
    const links = data.edges.map((e) => ({ source: e.source, target: e.target, rel: e.rel, count: e.count, rels: e.rels })) as L[];
    const all = [...new Set(nodes.map((n) => n.domain).filter(Boolean) as string[])].sort();
    // The integration platform is what everything else connects through, so it sits in the middle of the other domains.
    const hub = all.find((d) => /integration/i.test(d));
    const domains = all.filter((d) => d !== hub);
    const ring = 210 + domains.length * 18 + Math.sqrt(nodes.length) * 6;
    const centres = new Map<string, { x: number; y: number }>();
    if (hub) centres.set(hub, { x: 0, y: 0 });
    domains.forEach((d, i) => { const a = (i / domains.length) * Math.PI * 2 - Math.PI / 2; centres.set(d, { x: Math.cos(a) * ring, y: Math.sin(a) * ring }); });
    return { nodes, links, centres };
  }, [data]);

  // a stable object: handing the library a new graphData on every render restarts the layout, and with it the auto-fit
  const graphData = useMemo(() => ({ nodes: graph.nodes, links: graph.links }), [graph]);
  useEffect(() => setSettled(false), [graphData]);
  // remember positions when the graph is replaced, and again once the layout stops
  const remember = useCallback(() => { for (const n of graph.nodes) if (n.x !== undefined && n.y !== undefined) posCache.current.set(n.id, { x: n.x, y: n.y }); }, [graph]);
  useEffect(() => remember, [remember]);
  const hubCut = useMemo(() => [...graph.nodes.map((n) => n.degree)].sort((a, b) => b - a)[Math.min(11, graph.nodes.length - 1)] ?? 99, [graph]);
  const neighbours = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const l of graph.links) {
      const s = endId(l.source), t = endId(l.target);
      (m.get(s) ?? m.set(s, new Set()).get(s)!).add(t);
      (m.get(t) ?? m.set(t, new Set()).get(t)!).add(s);
    }
    return m;
  }, [graph]);
  // a selection that a filter has since removed must not dim everything else
  const selected = useMemo(() => (selectedId && graph.nodes.some((n) => n.id === selectedId) ? selectedId : null), [selectedId, graph]);
  const active = hover ?? selected ?? focusId ?? null;
  const near = useMemo(() => (active ? new Set([active, ...(neighbours.get(active) ?? [])]) : null), [active, neighbours]);

  const colorOf = useCallback(
    (n: N) => {
      if (colorBy === 'criticality') return colors.c(CRIT[n.criticality ?? ''] ?? 'fg-3');
      if (colorBy === 'lifecycle') return colors.c(LIFE[n.lifecycle ?? ''] ?? 'fg-3');
      return colors.c(TYPE_COLOR[n.type] ?? 'fg-3');
    },
    [colors, colorBy],
  );

  useEffect(() => {
    const fg = ref.current;
    if (!fg) return;
    fg.d3Force('charge')?.strength(-110).distanceMax(150);
    const same = (l: L) => ((l.source as N).domain ?? 'a') === ((l.target as N).domain ?? 'b');
    fg.d3Force('link')?.distance((l: L) => (focusId ? 70 : same(l) ? 42 : 170)).strength((l: L) => (focusId ? 0.5 : same(l) ? 0.35 : 0.01));
    fg.d3Force('center', null);
    fg.d3Force('cluster', focusId ? null : (clusterForce(graph.centres, 0.22) as never));
    fg.d3Force('collide', collideForce(11) as never);
    fg.d3ReheatSimulation();
  }, [graph, focusId]);

  const legend = useMemo(() => {
    if (colorBy === 'criticality') return [['Critical', 'critical', false], ['High', 'high', false], ['Medium', 'medium', false], ['Low', 'low', false], ['Unrated', 'fg-3', false]] as const;
    if (colorBy === 'lifecycle') return [['Supported', 'healthy', false], ['Extended', 'high', false], ['End of life / retired', 'critical', false], ['Other', 'fg-3', false]] as const;
    return [...new Set(graph.nodes.map((n) => n.type))].map((t) => [TYPE_LABEL[t] ?? t, TYPE_COLOR[t] ?? 'fg-3', t === 'Data'] as const);
  }, [colorBy, graph]);

  const nodeById = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph]);
  const hintId = useId();

  // ---- keyboard: arrow keys hop to the connected node that lies in that direction
  const describe = (n: N) => (n.members
    ? `${n.name} domain, folded, ${n.members} nodes. Press Enter to open it.`
    : `${n.name}, ${TYPE_LABEL[n.type] ?? n.type}${n.domain ? `, ${n.domain}` : ''}, ${n.degree} connection${n.degree === 1 ? '' : 's'}.`);
  const neighbourInDirection = (cur: N, dx: number, dy: number): N | null => {
    let best: N | null = null, bestScore = -Infinity;
    for (const id of neighbours.get(cur.id) ?? []) {
      const v = nodeById.get(id);
      if (!v || v.x === undefined || v.y === undefined || cur.x === undefined || cur.y === undefined) continue;
      const vx = v.x - cur.x, vy = v.y - cur.y, len = Math.hypot(vx, vy) || 1;
      const cos = (vx * dx + vy * dy) / len;
      if (cos < 0.35) continue; // not roughly that way
      const score = cos - len / 2000; // straightest first, nearer breaks ties
      if (score > bestScore) { bestScore = score; best = v; }
    }
    return best;
  };
  const moveTo = (n: N, say: string) => {
    onSelect?.(n.id);
    setAnnounce(say);
    const fg = ref.current;
    if (!fg || n.x === undefined || n.y === undefined) return;
    animating.current = true;
    window.setTimeout(() => { animating.current = false; }, 500);
    fg.centerAt(n.x, n.y, 300);
    if (fg.zoom() < 1.4) fg.zoom(1.4, 300);
  };
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget || e.altKey || e.ctrlKey || e.metaKey) return; // leave the zoom buttons and browser shortcuts alone
    const cur = selected ? nodeById.get(selected) : undefined;
    const dirs: Record<string, [number, number]> = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] };
    const dir = dirs[e.key];
    if (dir) {
      e.preventDefault();
      if (!cur) { const first = graph.nodes[0]; if (first) moveTo(first, `${describe(first)} Arrow keys move to connected nodes.`); return; }
      const next = neighbourInDirection(cur, dir[0], dir[1]);
      if (next) moveTo(next, describe(next));
      else setAnnounce(`${cur.name} has no connected node in that direction.`);
      return;
    }
    switch (e.key) {
      case 'Home': { const first = graph.nodes[0]; if (first) { e.preventDefault(); moveTo(first, describe(first)); } break; }
      case 'Enter': case ' ': if (cur) { e.preventDefault(); onNodeClick?.(cur.id); } break;
      case 'Escape': if (cur) { e.preventDefault(); onSelect?.(null); setAnnounce('Selection cleared.'); } break;
      case 'c': case 'C': if (cur?.domain) { e.preventDefault(); onToggleDomain?.(cur.domain); setAnnounce(`${cur.members ? 'Opening' : 'Folding'} the ${cur.domain} domain.`); } break;
      case '+': case '=': e.preventDefault(); ref.current?.zoom((ref.current?.zoom() ?? 1) * 1.4, 200); break;
      case '-': case '_': e.preventDefault(); ref.current?.zoom((ref.current?.zoom() ?? 1) / 1.4, 200); break;
      case '0': e.preventDefault(); ref.current?.zoomToFit(400, 60); break;
    }
  };

  // ---- domain labels double as fold controls; find the one under a point
  const labelAt = (clientX: number, clientY: number): string | null => {
    const fg = ref.current, el = wrap.current;
    if (!fg || !el || !territories.current.length) return null;
    const box = el.getBoundingClientRect();
    const p = fg.screen2GraphCoords(clientX - box.left, clientY - box.top);
    const k = fg.zoom();
    for (const t of territories.current) {
      const halfW = (t.d.length * 6.6 + 22) / k / 2, y = t.cy - t.r - 6 / k;
      if (Math.abs(p.x - t.cx) <= halfW && p.y <= y + 3 / k && p.y >= y - 14 / k) return t.d;
    }
    return null;
  };

  useImperativeHandle(handle, () => ({
    zoomToNode: (id: string) => {
      const n = graph.nodes.find((x) => x.id === id);
      const fg = ref.current;
      if (!n || !fg || n.x === undefined || n.y === undefined) return false;
      animating.current = true;
      window.setTimeout(() => { animating.current = false; }, 800);
      fg.centerAt(n.x, n.y, 600);
      fg.zoom(Math.max(fg.zoom(), 3.5), 600);
      return true;
    },
    fit: () => ref.current?.zoomToFit(400, 60),
    exportPng: () => {
      const canvas = wrap.current?.querySelector('canvas');
      if (!canvas) return Promise.reject(new Error('The graph has not drawn yet'));
      return composePng(canvas, { bg: colors.bg, fg: colors.fg, muted: colors.c('fg-3'), title: exportMeta?.title ?? 'Knowledge graph', subtitle: exportMeta?.subtitle ?? '', legend: legend.map(([l, tok, sq]) => [l, colors.c(tok), sq] as LegendItem) });
    },
    exportSvg: () => {
      const ex = graph.nodes as ExportNode[];
      return buildSvg(ex, graph.links.map((l) => ({ source: endId(l.source), target: endId(l.target) })), {
        fg: colors.fg, muted: colors.c('fg-3'), bg: colors.bg, line: colors.c('fg-3', 0.3), accent: colors.c('accent'),
        territory: colors.c('fg', 0.035), territoryLine: colors.c('fg', 0.1),
        colorOf: (n) => colorOf(n as N), legend: legend.map(([l, tok, sq]) => [l, colors.c(tok), sq] as const),
        title: exportMeta?.title ?? 'Knowledge graph', subtitle: exportMeta?.subtitle ?? '', hubCut, focusId, highlight,
      });
    },
  }), [graph, colors, colorOf, legend, exportMeta, hubCut, focusId, highlight]);

  // force-graph pauses redrawing once the layout settles, so re-setting the zoom is the way to repaint when only highlighting or colouring changed
  useEffect(() => {
    const fg = ref.current;
    // a zoom animation repaints every frame already, and setting the zoom here would cancel it
    if (fg && !animating.current) fg.zoom(fg.zoom());
  }, [selected, hover, hoverLink, hoverDomain, focused, colorBy, highlight, theme]);

  // legend entries carry a token name for the on-screen swatch; exports resolve it to a real colour above
  return (
    <div
      ref={wrap}
      data-testid="force-graph"
      data-settled={settled}
      data-nodes={graph.nodes.length}
      style={{ height: height === 'fill' ? '100%' : height, backgroundImage: `radial-gradient(${colors.c('fg', 0.07)} 1px, transparent 1px)`, backgroundSize: '22px 22px' }}
      className="relative w-full overflow-hidden rounded-lg border border-line bg-bg outline-none focus-visible:ring-2 focus-visible:ring-accent/70"
      // the library never notices the pointer leaving the canvas, which left the last node isolated until the next move
      onPointerLeave={() => { hoverRef.current = null; setHover(null); setHoverLink(null); setHoverDomain(null); }}
      onPointerMove={(e) => {
        if (!(e.target instanceof HTMLCanvasElement)) return;
        const d = hoverRef.current ? null : labelAt(e.clientX, e.clientY);
        setHoverDomain((prev) => (prev === d ? prev : d));
        e.currentTarget.style.cursor = d ? 'pointer' : '';
      }}
      onKeyDown={onKeyDown}
      onFocus={(e) => { if (e.target === e.currentTarget) setFocused(true); }}
      onBlur={(e) => { if (e.target === e.currentTarget) setFocused(false); }}
      tabIndex={0}
      aria-describedby={hintId}
      onPointerDown={(e) => { pressAt.current = e.button === 0 && e.target instanceof HTMLCanvasElement ? { x: e.clientX, y: e.clientY } : null; }}
      onPointerUp={(e) => {
        const start = pressAt.current;
        pressAt.current = null;
        // a click is a press and release within a few pixels; anything further is a pan and is left alone
        if (!start || Math.hypot(e.clientX - start.x, e.clientY - start.y) > 6) return;
        const { clientX, clientY } = e;
        requestAnimationFrame(() => { // let the hover state settle first, which touch screens need
          const id = hoverRef.current;
          if (id) { onNodeClick?.(id); return; }
          const domain = labelAt(clientX, clientY);
          if (domain) onToggleDomain?.(domain);
          else onBackgroundClick?.();
        });
      }}
      role="group"
      aria-label={`Knowledge graph with ${data.nodes.length} nodes and ${data.edges.length} edges, grouped by business domain`}
    >
      <p id={hintId} className="sr-only">Interactive graph. Arrow keys move to the connected node in that direction. Enter opens details. C folds or unfolds the node's domain. Plus and minus zoom, 0 fits the view, Escape clears. The table view lists the same nodes.</p>
      <div className="sr-only" role="status" aria-live="polite">{announce}</div>
      <ForceGraph2D<N, L>
        ref={ref}
        graphData={graphData}
        width={w}
        height={h}
        backgroundColor="rgba(0,0,0,0)"
        cooldownTicks={60}
        warmupTicks={150}
        onEngineStop={() => {
          remember();
          ref.current?.zoomToFit(500, focusId ? 90 : 60, focusId ? (n) => near?.has(n.id) ?? true : undefined);
          window.setTimeout(() => setSettled(true), 650); // after the fit animation, so tests and exports can rely on a still picture
        }}
        onZoom={(t) => { if (wrap.current) wrap.current.dataset.zoom = t.k.toFixed(2); }}
        d3VelocityDecay={0.35}
        minZoom={0.3}
        maxZoom={8}
        linkColor={(l) => {
          if (l === hoverLink) return colors.c('accent', 0.95);
          if (!near) return colors.c('fg-3', 0.2);
          return near.has(endId(l.source)) && near.has(endId(l.target)) && (endId(l.source) === active || endId(l.target) === active) ? colors.c('accent', 0.9) : colors.c('fg-3', 0.05);
        }}
        linkWidth={(l) => (l === hoverLink ? 2.4 : (near && (endId(l.source) === active || endId(l.target) === active) ? 1.4 : 0.6) + (l.count ? Math.min(3, Math.log2(l.count) * 0.45) : 0))}
        linkHoverPrecision={6}
        onLinkHover={(l) => setHoverLink(l ?? null)}
        linkLabel={(l) => `<div style="font:12px Inter,sans-serif"><b>${esc((l.source as N).name ?? l.source)}</b><br/><span style="opacity:.75">${esc(linkText(l))}</span><br/><b>${esc((l.target as N).name ?? l.target)}</b></div>`}
        linkCanvasObjectMode={() => 'after'}
        linkCanvasObject={(l, ctx, k) => {
          // name the relationship on the links of the isolated node once zoomed in, and always on the link under the pointer
          const a = l.source as N, b = l.target as N;
          const shown = l === hoverLink || (active !== null && k >= 2 && (a.id === active || b.id === active));
          if (!shown || a.x === undefined || b.x === undefined || a.y === undefined || b.y === undefined) return;
          const dx = b.x - a.x, dy = b.y - a.y;
          const mx = (a.x + b.x) / 2 + dy * 0.06, my = (a.y + b.y) / 2 - dx * 0.06; // the apex of the 0.12 curvature
          const text = linkText(l);
          const size = Math.max(2.6, 10 / k);
          ctx.font = `500 ${size}px Inter, sans-serif`;
          const tw = ctx.measureText(text).width;
          ctx.fillStyle = colors.c('bg', 0.92);
          ctx.fillRect(mx - tw / 2 - 2, my - size / 2 - 1.5, tw + 4, size + 3);
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = l === hoverLink ? colors.c('accent') : colors.fg;
          ctx.fillText(text, mx, my);
          ctx.textBaseline = 'alphabetic';
        }}
        linkCurvature={0.12}
        linkDirectionalArrowLength={(l) => (near && (endId(l.source) === active || endId(l.target) === active) ? 4 : 0)}
        linkDirectionalArrowRelPos={0.92}
        nodeRelSize={4}
        nodeLabel={(n) => `<div style="font:12px Inter,sans-serif"><b>${n.name}</b><br/>${TYPE_LABEL[n.type] ?? n.type}${n.domain ? ` · ${n.domain}` : ''}<br/>${n.degree} connections</div>`}
        // Nodes cannot be dragged: a press that wobbles by a pixel used to restart the layout and swallow the click.
        // Clicks are detected on the wrapper below, with a small tolerance, instead of through the library's drag-sensitive handlers.
        enableNodeDrag={false}
        onNodeHover={(n) => { hoverRef.current = n ? n.id : null; setHover(n ? n.id : null); }}
        onRenderFramePre={(ctx, scale) => {
          labelBoxes.current = [];
          territories.current = [];
          // soft domain territories behind the nodes
          const byDomain = new Map<string, N[]>();
          for (const n of graph.nodes) if (n.domain && n.x !== undefined) (byDomain.get(n.domain) ?? byDomain.set(n.domain, []).get(n.domain)!).push(n);
          for (const [d, ns] of byDomain) {
            if (ns.length < 3 || focusId) continue;
            const cx = ns.reduce((s, n) => s + (n.x ?? 0), 0) / ns.length;
            const cy = ns.reduce((s, n) => s + (n.y ?? 0), 0) / ns.length;
            const r = Math.max(...ns.map((n) => Math.hypot((n.x ?? 0) - cx, (n.y ?? 0) - cy) + radius(n))) + 14;
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.fillStyle = colors.c('fg', 0.035);
            ctx.fill();
            ctx.lineWidth = 1 / scale;
            ctx.strokeStyle = colors.c('fg', 0.1);
            ctx.stroke();
            // the label doubles as the control for folding the domain into a bubble
            territories.current.push({ d, cx, cy, r });
            ctx.font = `600 ${10 / scale}px Inter, sans-serif`;
            ctx.textAlign = 'center';
            ctx.fillStyle = d === hoverDomain ? colors.c('accent') : colors.c('fg-3', 0.9);
            ctx.fillText(`${d === hoverDomain ? '⊖ ' : '− '}${d.toUpperCase()}`, cx, cy - r - 6 / scale);
          }
        }}
        nodeCanvasObject={(n, ctx, scale) => {
          const r = radius(n);
          const x = n.x ?? 0, y = n.y ?? 0;
          const path = highlight && highlight.size > 0;
          const dim = (near && !near.has(n.id)) || (path && !highlight!.has(n.id));
          ctx.globalAlpha = dim ? 0.14 : 1;
          if (n.id === focusId || n.id === hover || n.id === selected || (path && highlight!.has(n.id))) {
            ctx.beginPath();
            ctx.arc(x, y, r + 4, 0, Math.PI * 2);
            ctx.fillStyle = colors.c('accent', 0.25);
            ctx.fill();
          }
          if (n.members) {
            // a folded domain: a large soft disc with its name and size, ringed in dashes to say "click to open"
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fillStyle = colors.c('accent', 0.16);
            ctx.fill();
            ctx.lineWidth = 1.6 / scale;
            ctx.strokeStyle = colorOf(n);
            ctx.setLineDash([4 / scale, 3 / scale]);
            ctx.stroke();
            ctx.setLineDash([]);
            const big = Math.max(3.5, 12 / scale), small = Math.max(3, 10 / scale);
            ctx.textAlign = 'center';
            ctx.fillStyle = colors.fg;
            ctx.font = `600 ${big}px Inter, sans-serif`;
            ctx.fillText(n.name, x, y - small * 0.1);
            ctx.fillStyle = colors.c('fg-3');
            ctx.font = `${small}px Inter, sans-serif`;
            ctx.fillText(`${n.members} nodes`, x, y + big * 1.05);
            if (focused && n.id === selected) { ctx.beginPath(); ctx.arc(x, y, r + 5, 0, Math.PI * 2); ctx.lineWidth = 2 / scale; ctx.strokeStyle = colors.c('accent'); ctx.stroke(); }
            ctx.globalAlpha = 1;
            return;
          }
          ctx.beginPath();
          if (n.type === 'Data') ctx.roundRect(x - r * 0.9, y - r * 0.9, r * 1.8, r * 1.8, r * 0.3);
          else ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fillStyle = colorOf(n);
          ctx.fill();
          ctx.lineWidth = 1.2 / scale;
          ctx.strokeStyle = colors.bg;
          ctx.stroke();
          if (focused && n.id === selected) { // the keyboard cursor
            ctx.beginPath();
            ctx.arc(x, y, r + 6, 0, Math.PI * 2);
            ctx.lineWidth = 2 / scale;
            ctx.strokeStyle = colors.c('accent');
            ctx.stroke();
          }

          const isHub = n.degree >= hubCut && hubCut > 0;
          const show = !dim && (isHub || scale > 1.9 || n.id === active || (near?.has(n.id) ?? false));
          if (show) {
            const size = Math.max(3.2, 11 / scale);
            ctx.font = `${isHub || n.id === active ? 600 : 500} ${size}px Inter, sans-serif`;
            const tw = ctx.measureText(n.name).width;
            const box = { x: x - tw / 2 - 2, y: y + r + 2, w: tw + 4, h: size + 2 };
            const clash = n.id !== active && labelBoxes.current.some((b) => box.x < b.x + b.w && box.x + box.w > b.x && box.y < b.y + b.h && box.y + box.h > b.y);
            if (!clash) {
              labelBoxes.current.push(box);
              ctx.fillStyle = colors.c('bg', 0.9);
              ctx.fillRect(box.x, box.y, box.w, box.h);
              ctx.textAlign = 'center';
              ctx.textBaseline = 'top';
              ctx.fillStyle = colors.fg;
              ctx.fillText(n.name, x, y + r + 3);
              ctx.textBaseline = 'alphabetic';
            }
          }
          ctx.globalAlpha = 1;
        }}
        nodePointerAreaPaint={(n, color, ctx) => {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(n.x ?? 0, n.y ?? 0, radius(n) + 3, 0, 2 * Math.PI);
          ctx.fill();
        }}
      />
      <div className="absolute right-3 top-3 flex flex-col overflow-hidden rounded-md border border-line bg-surface/90 shadow-sm backdrop-blur">
        {([['Zoom in', ZoomIn, () => ref.current?.zoom((ref.current?.zoom() ?? 1) * 1.5, 250)], ['Zoom out', ZoomOut, () => ref.current?.zoom((ref.current?.zoom() ?? 1) / 1.5, 250)], ['Fit to view', Maximize2, () => ref.current?.zoomToFit(400, 60)]] as const).map(([label, Icon, fn]) => (
          <button key={label} type="button" aria-label={label} title={label} onClick={fn} className="flex h-8 w-8 items-center justify-center text-fg-2 hover:bg-raised hover:text-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"><Icon className="h-4 w-4" /></button>
        ))}
      </div>
      <ul className="absolute bottom-3 left-3 flex flex-wrap gap-x-3 gap-y-1 rounded-md border border-line bg-surface/90 px-3 py-2 text-xs text-fg-2 shadow-sm backdrop-blur" aria-label="Legend">
        {legend.map(([label, tok, square]) => (<li key={label} className="flex items-center gap-1.5"><span className={square ? 'h-2.5 w-2.5 rounded-sm' : 'h-2.5 w-2.5 rounded-full'} style={{ background: colors.c(tok) }} aria-hidden />{label}</li>))}
      </ul>
    </div>
  );
});

export default ForceGraphView;
