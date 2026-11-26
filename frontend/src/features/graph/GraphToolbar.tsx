import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { Bookmark, ChevronDown, Download, Filter, Group, Layers, Maximize, Minimize, Palette, Search, Share2, Table2, Network, Trash2, X } from 'lucide-react';
import type { GraphNode, GraphView } from '@/api/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/cn';
import { relationLabel, searchNodes, UNRATED } from './filter';

/*
 * Everything here is deliberately built without portals. The toolbar has to keep working in full screen, and only the
 * full-screen element's own subtree is painted, so a menu that renders into <body> would silently disappear.
 */

export function InlineMenu({ label, icon, count, width = 260, align = 'left', children }: { label: string; icon: ReactNode; count?: number; width?: number; align?: 'left' | 'right'; children: (close: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); setOpen(false); button.current?.focus(); } };
    document.addEventListener('pointerdown', down);
    document.addEventListener('keydown', key, true);
    return () => { document.removeEventListener('pointerdown', down); document.removeEventListener('keydown', key, true); };
  }, [open]);
  return (
    <div ref={root} className="relative">
      <Button ref={button} size="sm" variant={count ? 'outline' : 'secondary'} aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => setOpen((o) => !o)} leading={icon} trailing={<ChevronDown className={cn('h-3 w-3 transition-transform', open && 'rotate-180')} aria-hidden />}>
        {label}
        {!!count && <span className="num ml-0.5 rounded-full bg-accent/15 px-1.5 font-mono text-[10px] text-accent">{count}</span>}
      </Button>
      {open && (
        <div id={id} role="dialog" aria-label={label} style={{ width }} className={cn('glass absolute top-full z-30 mt-1.5 max-w-[88vw] animate-fadeIn rounded-lg border border-line p-2 shadow-pop', align === 'right' ? 'right-0' : 'left-0')}>
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

function CheckRow({ checked, onChange, children, hint }: { checked: boolean; onChange: (on: boolean) => void; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm text-fg-2 hover:bg-raised hover:text-fg">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-3.5 w-3.5 accent-accent" />
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {hint !== undefined && <span className="num font-mono text-xs text-fg-2">{hint}</span>}
    </label>
  );
}

const toggle = (list: string[], v: string, on: boolean) => (on ? [...new Set([...list, v])] : list.filter((x) => x !== v));

/* ------------------------------------------------------------------ find in view */
export function FindInView({ nodes, onPick }: { nodes: GraphNode[]; onPick: (n: GraphNode) => void }) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const id = useId();
  const results = useMemo(() => searchNodes(nodes, q), [nodes, q]);
  useEffect(() => setCursor(0), [q]);
  const pick = (n: GraphNode) => { onPick(n); setQ(''); setOpen(false); };
  return (
    <div className="relative w-56 max-w-full">
      <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-3" aria-hidden />
      <input
        role="combobox"
        aria-label="Find a node in this view"
        aria-expanded={open && q.length > 0}
        aria-controls={`${id}-list`}
        aria-activedescendant={open && results[cursor] ? `${id}-${cursor}` : undefined}
        aria-autocomplete="list"
        value={q}
        placeholder="Find in view"
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, results.length - 1)); }
          else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
          else if (e.key === 'Enter' && results[cursor]) { e.preventDefault(); pick(results[cursor]); }
          else if (e.key === 'Escape') { setQ(''); setOpen(false); }
        }}
        className="h-7 w-full rounded border border-line bg-bg pl-7 pr-2 text-xs text-fg placeholder:text-fg-3 hover:border-fg-3/40 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
      />
      {open && q.length > 0 && (
        <ul id={`${id}-list`} role="listbox" aria-label="Matching nodes" className="glass absolute left-0 top-full z-30 mt-1.5 max-h-72 w-72 max-w-[88vw] overflow-auto rounded-lg border border-line py-1 shadow-pop">
          {results.map((n, i) => (
            <li key={n.id} id={`${id}-${i}`} role="option" aria-selected={i === cursor}>
              <button type="button" tabIndex={-1} onMouseDown={(e) => e.preventDefault()} onClick={() => pick(n)} onMouseEnter={() => setCursor(i)} className={cn('flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs', i === cursor ? 'bg-raised' : 'hover:bg-raised')}>
                <span className="min-w-0"><span className="block truncate text-fg">{n.name}</span>{n.domain && <span className="block truncate text-fg-3">{n.domain}</span>}</span>
                <Badge>{n.type}</Badge>
              </button>
            </li>
          ))}
          {!results.length && <li className="px-3 py-2 text-xs text-fg-3">Nothing in this view matches. Turn on more layers, or clear the filters.</li>}
        </ul>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ the toolbar */
export interface Layer { key: string; label: string; dot: string }
type ColourBy = 'type' | 'criticality' | 'lifecycle';

export interface GraphToolbarProps {
  nodes: GraphNode[];
  shown: number;
  total: number;
  layerDefs: Layer[];
  layers: string[];
  onLayers: (l: string[]) => void;
  colorBy: ColourBy;
  onColorBy: (c: ColourBy) => void;
  domains: [string, number][];
  criticalities: [string, number][];
  filterDomains: string[];
  filterCrit: string[];
  onDomains: (d: string[]) => void;
  onCrit: (c: string[]) => void;
  onClearFilters: () => void;
  relations: [string, number][];
  filterRelations: string[];
  onRelations: (r: string[]) => void;
  collapsed: string[];
  onCollapsed: (d: string[]) => void;
  view: 'graph' | 'table';
  onView: (v: 'graph' | 'table') => void;
  onPick: (n: GraphNode) => void;
  selectedName?: string | null;
  onClearSelected: () => void;
  views: GraphView[];
  onApplyView: (v: GraphView) => void;
  onDeleteView: (v: GraphView) => void;
  onSaveView: (name: string) => Promise<string | null>;
  onExport: (kind: 'png' | 'svg' | 'csv') => void;
  exporting: boolean;
  fullscreen: boolean;
  onFullscreen: () => void;
}

const COLOUR_OPTS: { value: ColourBy; label: string }[] = [{ value: 'type', label: 'Type' }, { value: 'criticality', label: 'Criticality' }, { value: 'lifecycle', label: 'Lifecycle' }];

export function GraphToolbar(p: GraphToolbarProps) {
  const filterCount = p.filterDomains.length + p.filterCrit.length + p.filterRelations.length;
  const table = p.view === 'table';
  return (
    <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Graph controls">
      <div role="group" aria-label="View" className="inline-flex overflow-hidden rounded-md border border-line">
        {([['graph', 'Graph', Network], ['table', 'Table', Table2]] as const).map(([v, label, Icon]) => (
          <button key={v} type="button" aria-pressed={p.view === v} onClick={() => p.onView(v)} className={cn('inline-flex h-7 items-center gap-1.5 px-2.5 text-xs font-medium focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent', p.view === v ? 'bg-accent/15 text-fg' : 'text-fg-2 hover:bg-raised hover:text-fg')}><Icon className="h-3.5 w-3.5" aria-hidden />{label}</button>
        ))}
      </div>
      {!table && <FindInView nodes={p.nodes} onPick={p.onPick} />}
      {!table && p.selectedName && (
        <span className="inline-flex h-7 max-w-[220px] items-center gap-1 rounded-full border border-accent/30 bg-accent/10 pl-2.5 pr-1 text-xs text-fg">
          <span className="truncate">{p.selectedName}</span>
          <button type="button" aria-label="Clear selection" onClick={p.onClearSelected} className="rounded-full p-0.5 text-fg-3 hover:text-fg"><X className="h-3 w-3" /></button>
        </span>
      )}

      <InlineMenu label="Layers" icon={<Layers className="h-3.5 w-3.5" aria-hidden />} width={230}>
        {() => (
          <div>
            {p.layerDefs.map((l) => (
              <CheckRow key={l.key} checked={p.layers.includes(l.key)} onChange={(on) => p.onLayers(on ? [...p.layers, l.key] : p.layers.filter((x) => x !== l.key))}>
                <span className="flex items-center gap-2"><span className={cn('h-2 w-2 rounded-full', l.dot)} aria-hidden />{l.label}</span>
              </CheckRow>
            ))}
          </div>
        )}
      </InlineMenu>

      <InlineMenu label="Domains" icon={<Filter className="h-3.5 w-3.5" aria-hidden />} count={p.filterDomains.length} width={260}>
        {() => (
          <div>
            <div className="max-h-72 overflow-auto">
              {p.domains.map(([d, n]) => <CheckRow key={d} checked={p.filterDomains.includes(d)} onChange={(on) => p.onDomains(toggle(p.filterDomains, d, on))} hint={n}>{d}</CheckRow>)}
              {!p.domains.length && <p className="px-2 py-1.5 text-xs text-fg-3">No domains in this view.</p>}
            </div>
            <p className="px-2 pb-1 pt-2 text-xs text-fg-3">{p.filterDomains.length ? `${p.filterDomains.length} selected` : 'None selected shows every domain.'}</p>
          </div>
        )}
      </InlineMenu>

      <InlineMenu label="Criticality" icon={<Filter className="h-3.5 w-3.5" aria-hidden />} count={p.filterCrit.length} width={220}>
        {() => (
          <div>
            {p.criticalities.map(([c, n]) => <CheckRow key={c} checked={p.filterCrit.includes(c)} onChange={(on) => p.onCrit(toggle(p.filterCrit, c, on))} hint={n}><span className="capitalize">{c === UNRATED ? 'Unrated' : c}</span></CheckRow>)}
            {!p.criticalities.length && <p className="px-2 py-1.5 text-xs text-fg-3">No rated nodes in this view.</p>}
          </div>
        )}
      </InlineMenu>

      <InlineMenu label="Relationships" icon={<Share2 className="h-3.5 w-3.5" aria-hidden />} count={p.filterRelations.length} width={250}>
        {() => (
          <div>
            <div className="max-h-72 overflow-auto">
              {p.relations.map(([r, n]) => <CheckRow key={r} checked={p.filterRelations.includes(r)} onChange={(on) => p.onRelations(toggle(p.filterRelations, r, on))} hint={n}>{relationLabel(r)}</CheckRow>)}
              {!p.relations.length && <p className="px-2 py-1.5 text-xs text-fg-3">No relationships in this view.</p>}
            </div>
            <p className="px-2 pb-1 pt-2 text-xs text-fg-3">{p.filterRelations.length ? 'Showing only the nodes these relationships connect.' : 'None selected shows every relationship.'}</p>
          </div>
        )}
      </InlineMenu>

      {!table && (
        <InlineMenu label="Fold domains" icon={<Group className="h-3.5 w-3.5" aria-hidden />} count={p.collapsed.length} width={270}>
          {() => (
            <div>
              <div className="flex gap-1.5 px-1 pb-1.5">
                <Button size="sm" variant="secondary" onClick={() => p.onCollapsed(p.domains.map(([d]) => d))}>Fold all</Button>
                <Button size="sm" variant="ghost" disabled={!p.collapsed.length} onClick={() => p.onCollapsed([])}>Open all</Button>
              </div>
              <div className="max-h-64 overflow-auto border-t border-line pt-1">
                {p.domains.map(([d, n]) => <CheckRow key={d} checked={p.collapsed.includes(d)} onChange={(on) => p.onCollapsed(toggle(p.collapsed, d, on))} hint={n}>{d}</CheckRow>)}
              </div>
              <p className="px-2 pb-1 pt-2 text-xs text-fg-3">A folded domain becomes one bubble. Click a bubble, or its name when open, to switch.</p>
            </div>
          )}
        </InlineMenu>
      )}

      {!table && <InlineMenu label={`Colour: ${COLOUR_OPTS.find((o) => o.value === p.colorBy)!.label}`} icon={<Palette className="h-3.5 w-3.5" aria-hidden />} width={190}>
        {(close) => (
          <div role="radiogroup" aria-label="Colour by">
            {COLOUR_OPTS.map((o) => (
              <label key={o.value} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm text-fg-2 hover:bg-raised hover:text-fg">
                <input type="radio" name="graph-colour" checked={p.colorBy === o.value} onChange={() => { p.onColorBy(o.value); close(); }} className="h-3.5 w-3.5 accent-accent" />{o.label}
              </label>
            ))}
          </div>
        )}
      </InlineMenu>}

      <ViewsMenu views={p.views} onApply={p.onApplyView} onDelete={p.onDeleteView} onSave={p.onSaveView} />

      <InlineMenu label="Export" icon={<Download className="h-3.5 w-3.5" aria-hidden />} width={270} align="right">
        {(close) => (
          <div className="space-y-1">
            {table ? (
              <button type="button" disabled={p.exporting} onClick={() => { p.onExport('csv'); close(); }} className="block w-full rounded px-2 py-1.5 text-left hover:bg-raised disabled:opacity-50"><span className="block text-sm text-fg">CSV spreadsheet</span><span className="block text-xs text-fg-3">The nodes the filters leave, opens in Excel</span></button>
            ) : (<>
            <button type="button" disabled={p.exporting} onClick={() => { p.onExport('png'); close(); }} className="block w-full rounded px-2 py-1.5 text-left hover:bg-raised disabled:opacity-50"><span className="block text-sm text-fg">PNG image</span><span className="block text-xs text-fg-3">Exactly what you see now, with title and legend</span></button>
            <button type="button" disabled={p.exporting} onClick={() => { p.onExport('svg'); close(); }} className="block w-full rounded px-2 py-1.5 text-left hover:bg-raised disabled:opacity-50"><span className="block text-sm text-fg">SVG vector</span><span className="block text-xs text-fg-3">The whole graph, editable in Figma or PowerPoint</span></button>
            </>)}
          </div>
        )}
      </InlineMenu>

      <Button size="sm" variant="secondary" aria-pressed={p.fullscreen} onClick={p.onFullscreen} leading={p.fullscreen ? <Minimize className="h-3.5 w-3.5" aria-hidden /> : <Maximize className="h-3.5 w-3.5" aria-hidden />}>{p.fullscreen ? 'Exit full screen' : 'Full screen'}</Button>

      <span className="ml-auto flex items-center gap-2 text-xs text-fg-3" aria-live="polite">
        <span><span className="num font-mono text-fg-2">{p.shown}</span>{p.shown !== p.total && <> of <span className="num font-mono text-fg-2">{p.total}</span></>} nodes</span>
        {filterCount > 0 && <button type="button" onClick={p.onClearFilters} className="text-accent hover:underline">Clear filters</button>}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ saved views */
const summarise = (v: GraphView) => [v.focus ? `focused on ${v.focus}` : null, `${v.layers.length} layer${v.layers.length === 1 ? '' : 's'}`, v.domains.length ? `${v.domains.length} domain${v.domains.length === 1 ? '' : 's'}` : null, v.criticality.length ? v.criticality.join('/') : null, v.relations?.length ? `${v.relations.length} relationship${v.relations.length === 1 ? '' : 's'}` : null, v.collapsed?.length ? `${v.collapsed.length} folded` : null].filter(Boolean).join(' · ');

function ViewsMenu({ views, onApply, onDelete, onSave }: { views: GraphView[]; onApply: (v: GraphView) => void; onDelete: (v: GraphView) => void; onSave: (name: string) => Promise<string | null> }) {
  const [name, setName] = useState('');
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    const n = name.trim();
    if (!n) { setMsg({ tone: 'err', text: 'Give the view a name first.' }); return; }
    setBusy(true);
    const err = await onSave(n);
    setBusy(false);
    if (err) setMsg({ tone: 'err', text: err });
    else { setMsg({ tone: 'ok', text: `Saved “${n}”.` }); setName(''); }
  };
  return (
    <InlineMenu label="Views" icon={<Bookmark className="h-3.5 w-3.5" aria-hidden />} count={views.length || undefined} width={300}>
      {(close) => (
        <div>
          <p className="micro px-2 pb-1">Saved views</p>
          <ul className="max-h-56 overflow-auto">
            {views.map((v) => (
              <li key={v.id} className="group flex items-center gap-1 rounded hover:bg-raised">
                <button type="button" onClick={() => { onApply(v); close(); }} className="min-w-0 flex-1 px-2 py-1.5 text-left"><span className="block truncate text-sm text-fg">{v.name}</span><span className="block truncate text-xs text-fg-3">{summarise(v)}</span></button>
                <button type="button" aria-label={`Delete view ${v.name}`} onClick={() => onDelete(v)} className="mr-1 rounded p-1.5 text-fg-3 hover:text-critical"><Trash2 className="h-3.5 w-3.5" /></button>
              </li>
            ))}
            {!views.length && <li className="px-2 py-1.5 text-xs text-fg-3">None yet. Set up layers, filters and focus, then save them here.</li>}
          </ul>
          <form className="mt-2 border-t border-line pt-2" onSubmit={(e) => { e.preventDefault(); void save(); }}>
            <label className="micro block px-2 pb-1" htmlFor="graph-view-name">Save the current view</label>
            <div className="flex gap-1.5 px-1">
              <input id="graph-view-name" value={name} maxLength={60} onChange={(e) => { setName(e.target.value); setMsg(null); }} placeholder="e.g. Claims, critical only" className="h-7 min-w-0 flex-1 rounded border border-line bg-bg px-2 text-xs text-fg placeholder:text-fg-3 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30" />
              <Button size="sm" variant="primary" type="submit" loading={busy}>Save</Button>
            </div>
            {msg && <p role="status" className={cn('px-2 pt-1.5 text-xs', msg.tone === 'ok' ? 'text-healthy' : 'text-critical')}>{msg.text}</p>}
            <p className="px-2 pt-1.5 text-xs text-fg-3">Saves layers, filters, colouring and focus. Using an existing name replaces that view.</p>
          </form>
        </div>
      )}
    </InlineMenu>
  );
}
