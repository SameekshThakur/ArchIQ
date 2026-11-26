import { Background, Controls, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, applyNodeChanges, useReactFlow, type Connection, type Edge as RFEdge, type Node as RFNode, type NodeChange, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Bot, Box, Building2, Database, KeyRound, Plug, Plus, Radio, Redo2, RotateCcw, Search, ShieldCheck, Sparkles, Trash2, Undo2, User, Workflow } from 'lucide-react';
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Button, IconButton } from '@/components/ui/Button';
import { Select, TextInput } from '@/components/ui/Inputs';
import { cn } from '@/lib/cn';
import type { Architecture, Catalog, Design, Gap, Node as ANode, PropRow } from './types';

type Op = Record<string, unknown>;
const ICON: Record<string, typeof Box> = { actor: User, edge: ShieldCheck, api: Plug, compute: Box, ai_agent: Bot, ai_llm: Sparkles, ai_search: Search, messaging: Radio, integration: Workflow, database: Database, security: KeyRound, external: Building2 };
const TINT: Record<string, string> = { actor: 'bg-raised text-fg-2', edge: 'bg-accent/10 text-accent', api: 'bg-healthy/10 text-healthy', compute: 'bg-accent/10 text-accent', ai_agent: 'bg-medium/10 text-medium', ai_llm: 'bg-medium/10 text-medium',
  ai_search: 'bg-high/10 text-high', messaging: 'bg-medium/10 text-medium', integration: 'bg-raised text-fg-2', database: 'bg-healthy/10 text-healthy', security: 'bg-critical/10 text-critical', external: 'bg-raised text-fg-2' };
const SEV_RING: Record<string, string> = { critical: 'border-critical/70', high: 'border-high/60', medium: 'border-medium/50', low: 'border-line' };

const FLOW_VARS = { '--xy-background-color': 'transparent', '--xy-controls-button-background-color-default': 'rgb(var(--raised))', '--xy-controls-button-color-default': 'rgb(var(--fg-2))', '--xy-controls-button-border-color-default': 'rgb(var(--border))', '--xy-controls-button-background-color-hover-default': 'rgb(var(--overlay))' } as React.CSSProperties;

type NodeData = { node: ANode; worst: string | null; w: number; h: number } & Record<string, unknown>;

const ArchNode = memo(function ArchNode({ data, selected }: NodeProps<RFNode<NodeData>>) {
  const n = data.node;
  const Icon = ICON[n.role] ?? Box;
  return (
    <div
      data-testid={`node-${n.id}`}
      aria-label={`${n.name}, ${n.role_label}${n.technology ? `, ${n.technology}` : ''}${data.worst ? `, ${data.worst} finding` : ''}`}
      className={cn('hairline flex items-center gap-2 rounded-md border bg-surface px-2.5 py-2 text-left shadow-sm', data.worst ? SEV_RING[data.worst] : 'border-line', !n.assessed && n.role !== 'actor' && n.role !== 'external' && 'border-dashed', selected && 'ring-2 ring-accent/70')}
      style={{ width: data.w, minHeight: data.h }}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-fg-3" />
      <span className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded', TINT[n.role] ?? 'bg-raised text-fg-2')}><Icon className="h-4 w-4" aria-hidden /></span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-xs font-medium text-fg">{n.name}</span>
        <span className="block truncate text-[10px] text-fg-3">{n.technology ?? n.role_label}</span>
      </span>
      {data.worst && <span className={cn('h-2 w-2 shrink-0 rounded-full', data.worst === 'critical' ? 'bg-critical' : data.worst === 'high' ? 'bg-high' : data.worst === 'medium' ? 'bg-medium' : 'bg-low')} aria-hidden />}
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-fg-3" />
    </div>
  );
});
const nodeTypes = { arch: ArchNode };

/* ---------- editing operations: the diagram is the blueprint plus this list ---------- */
const referencing = (o: Op, id: string) => o.id === id || o.source === id || o.target === id;

export function removeNodeOps(ops: Op[], id: string): Op[] {
  if (ops.some((o) => o.op === 'add_node' && o.id === id)) return ops.filter((o) => !referencing(o, id));
  return [...ops.filter((o) => !(o.op === 'move_node' && o.id === id) && !(o.op === 'add_edge' && referencing(o, id))), { op: 'remove_node', id }];
}
export function removeEdgeOps(ops: Op[], source: string, target: string): Op[] {
  if (ops.some((o) => o.op === 'add_edge' && o.source === source && o.target === target)) return ops.filter((o) => !(o.op === 'add_edge' && o.source === source && o.target === target));
  return [...ops, { op: 'remove_edge', source, target }];
}
export function updateNodeOps(ops: Op[], id: string, patch: { name?: string; role?: string; props?: Record<string, unknown> }): Op[] {
  const added = ops.find((o) => o.op === 'add_node' && o.id === id);
  if (added && !patch.role) {
    // an added component carries its own name and properties
    return ops.map((o) => (o === added ? { ...o, ...(patch.name ? { name: patch.name } : {}), props: Object.fromEntries(Object.entries({ ...(o.props as Record<string, unknown>), ...patch.props }).filter(([, v]) => v !== null)) } : o));
  }
  const cur = ops.find((o) => o.op === 'update_node' && o.id === id);
  const merged = { op: 'update_node', id, ...(cur ?? {}), ...(patch.name ? { name: patch.name } : {}), ...(patch.role ? { role: patch.role } : {}), props: { ...((cur?.props as Record<string, unknown>) ?? {}), ...(patch.props ?? {}) } };
  return cur ? ops.map((o) => (o === cur ? merged : o)) : [...ops, merged];
}
export function moveOps(ops: Op[], id: string, x: number, y: number): Op[] {
  return [...ops.filter((o) => !(o.op === 'move_node' && o.id === id)), { op: 'move_node', id, x: Math.round(x), y: Math.round(y) }];
}

function worstByNode(gaps: Gap[]): Record<string, string> {
  const rank = ['critical', 'high', 'medium', 'low'];
  const out: Record<string, string> = {};
  for (const g of gaps) {
    if (g.state === 'risk_accepted') continue;
    for (const c of g.components) if (!out[c] || rank.indexOf(g.severity) < rank.indexOf(out[c])) out[c] = g.severity;
  }
  return out;
}

function nextId(arch: Architecture, ops: Op[]): string {
  const used = new Set([...arch.nodes.map((n) => n.id), ...ops.filter((o) => o.op === 'add_node').map((o) => String(o.id))]);
  let i = 1;
  while (used.has(`N${i}`)) i += 1;
  return `N${i}`;
}

/* ---------- the canvas ---------- */
function Canvas({ design, onOps, busy, readOnly, height, selected, onSelect }: { design: Design; onOps: (ops: Op[]) => void; busy: boolean; readOnly: boolean; height: number; selected: string | null; onSelect: (id: string | null) => void }) {
  const arch = design.architecture as Architecture;
  const worst = useMemo(() => worstByNode(design.validation?.gaps ?? []), [design.validation]);
  const toRF = useCallback(() => arch.nodes.map((n): RFNode<NodeData> => ({ id: n.id, type: 'arch', position: n.pos, selected: n.id === selected, draggable: !readOnly, data: { node: n, worst: worst[n.id] ?? null, w: arch.node_size.w, h: arch.node_size.h } })), [arch, worst, selected, readOnly]);
  const [nodes, setNodes] = useState<RFNode<NodeData>[]>(toRF);
  useEffect(() => setNodes(toRF()), [toRF]);
  const rf = useReactFlow();
  const shape = arch.nodes.map((n) => n.id).join('|');
  // fit again when components are added or removed, and once the container has its final size; not on every drag
  useEffect(() => { const t = setTimeout(() => void rf.fitView({ padding: 0.1, minZoom: readOnly ? 0.2 : 0.6, maxZoom: 1.1 }), 80); return () => clearTimeout(t); }, [shape, rf, readOnly]);
  const edges = useMemo<RFEdge[]>(() => arch.edges.map((e) => ({
    id: e.id, source: e.source, target: e.target, label: e.label || undefined, animated: false, deletable: !readOnly, selectable: !readOnly,
    markerEnd: { type: MarkerType.ArrowClosed, color: 'rgb(var(--fg-3))' }, style: { stroke: e.blocked ? 'rgb(var(--critical))' : 'rgb(var(--fg-3))', strokeDasharray: e.dashed ? '5 4' : undefined, strokeWidth: 1.4 },
    labelStyle: { fontSize: 10, fill: 'rgb(var(--fg-2))' }, labelBgStyle: { fill: 'rgb(var(--bg))' },
  })), [arch.edges, readOnly]);
  const ops = design.ops as Op[];
  const onNodesChange = (c: NodeChange<RFNode<NodeData>>[]) => setNodes((cur) => applyNodeChanges(c, cur));
  return (
    <div className="relative overflow-hidden rounded-lg border border-line bg-bg" style={{ height }} data-testid="architecture-canvas">
      <ReactFlow
        nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange} fitView fitViewOptions={{ padding: 0.1, minZoom: readOnly ? 0.2 : 0.6, maxZoom: 1.1 }} minZoom={0.2} maxZoom={1.6} proOptions={{ hideAttribution: true }}
        nodesConnectable={!readOnly && !busy} nodesDraggable={!readOnly && !busy} elementsSelectable aria-label="Architecture diagram" style={FLOW_VARS}
        onNodeClick={(_, n) => onSelect(n.id)} onPaneClick={() => onSelect(null)}
        onNodeDragStop={(_, n) => onOps(moveOps(ops, n.id, n.position.x, n.position.y))}
        onConnect={(c: Connection) => { if (c.source && c.target && c.source !== c.target && !arch.edges.some((e) => e.source === c.source && e.target === c.target)) onOps([...ops, { op: 'add_edge', source: c.source, target: c.target }]); }}
        onNodesDelete={(del) => { if (!readOnly) onOps(del.reduce((acc, n) => removeNodeOps(acc, n.id), ops)); onSelect(null); }}
        onEdgesDelete={(del) => { if (!readOnly) onOps(del.reduce((acc, e) => removeEdgeOps(acc, e.source, e.target), ops)); }}
      >
        <Background gap={20} size={1} color="rgb(var(--border))" />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>
    </div>
  );
}

/* ---------- the panel for the selected component ---------- */
function PropControl({ row, value, onChange, regions }: { row: PropRow; value: unknown; onChange: (v: unknown) => void; regions: string[] }) {
  const unset = value === undefined || value === null;
  if (row.kind === 'number') {
    return <TextInput type="number" min={1} inputMode="numeric" aria-label={row.label} defaultValue={unset ? '' : String(value)} key={String(value)} onBlur={(e) => { const v = e.target.value.trim(); if (v === '' ? !unset : Number(v) !== value) onChange(v === '' ? null : Number(v)); }} className="!h-7" />;
  }
  const options = row.kind === 'bool' ? [{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }] : (row.options ?? regions).map((o) => ({ value: o, label: o }));
  return <Select label={row.label} className="!h-7 w-full" value={unset ? '_' : String(value)} onValueChange={(v) => onChange(v === '_' ? null : row.kind === 'bool' ? v === 'true' : v)} options={[{ value: '_', label: 'Not specified' }, ...options]} />;
}

function Inspector({ design, catalog, node, onOps, busy }: { design: Design; catalog: Catalog; node: ANode; onOps: (ops: Op[]) => void; busy: boolean }) {
  const arch = design.architecture as Architecture;
  const ops = design.ops as Op[];
  const schema = catalog.prop_schema[node.type] ?? [];
  const gaps = (design.validation?.gaps ?? []).filter((g) => g.components.includes(node.id));
  const incoming = arch.edges.filter((e) => e.target === node.id);
  const outgoing = arch.edges.filter((e) => e.source === node.id);
  const [target, setTarget] = useState('');
  const names = Object.fromEntries(arch.nodes.map((n) => [n.id, n.name]));
  const others = arch.nodes.filter((n) => n.id !== node.id && !outgoing.some((e) => e.target === n.id));
  return (
    <div className="space-y-4 text-sm" data-testid="node-inspector">
      <div>
        <p className="micro">Component</p>
        <label className="mt-1.5 block"><span className="sr-only">Name</span><TextInput defaultValue={node.name} key={node.id + node.name} aria-label="Component name" onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== node.name) onOps(updateNodeOps(ops, node.id, { name: v })); }} disabled={busy} /></label>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <Badge tone={node.origin === 'blueprint' ? 'neutral' : 'accent'}>{node.origin === 'blueprint' ? 'From the blueprint' : node.origin === 'control' ? 'Added by a control' : 'Added by you'}</Badge>
          <Badge mono>{node.type_label}</Badge>
          {!node.assessed && node.role !== 'actor' && node.role !== 'external' && <Badge tone="medium">Not assessed</Badge>}
        </div>
        {node.technology && <p className="mt-2 text-xs text-fg-2">Technology: <span className="font-mono text-fg">{node.technology}</span>{node.hosting ? <> on <span className="font-mono text-fg">{node.hosting.technology}</span></> : null}</p>}
        <p className="mt-1 text-xs text-fg-3">The type and technology follow from the role and your choices in the Customise step.</p>
        {node.notes.map((t) => <p key={t} className="mt-1 text-xs text-fg-3">{t}</p>)}
        {node.estate && <p className="mt-2 rounded border border-line bg-raised/50 px-2 py-1.5 text-xs text-fg-2">Existing {node.estate.kind}: <span className="text-fg">{node.estate.name}</span> ({node.estate.id}), {node.estate.lifecycle.replace('_', ' ')}, {node.estate.criticality}.</p>}
      </div>
      <div>
        <p className="micro mb-1.5">Role</p>
        <Select label="Role" className="w-full" value={node.role} onValueChange={(v) => onOps(updateNodeOps(ops, node.id, { role: v }))} options={Object.entries(catalog.roles).map(([v, l]) => ({ value: v, label: l }))} />
      </div>
      {schema.length > 0 && (
        <div>
          <p className="micro mb-1.5">Properties the standards check</p>
          <ul className="space-y-2.5">
            {schema.map((row) => {
              const origin = node.prop_origin[row.key];
              return (
                <li key={row.key}>
                  <div className="flex items-baseline justify-between gap-2"><span className="text-xs text-fg-2">{row.label}</span>
                    {origin ? <span className={cn('text-[10px]', origin === 'edited' ? 'text-accent' : 'text-fg-3')}>{origin}</span> : <span className="text-[10px] text-fg-3">not specified</span>}</div>
                  <PropControl row={row} value={node.props[row.key]} regions={catalog.approved_regions} onChange={(v) => onOps(updateNodeOps(ops, node.id, { props: { [row.key]: v } }))} />
                </li>
              );
            })}
          </ul>
          <p className="mt-2 text-xs text-fg-3">An edit overrides what the choices set. Pick “Not specified” to clear it; the standards then report it as not specified.</p>
        </div>
      )}
      <div>
        <p className="micro mb-1.5">Connections</p>
        <ul className="space-y-1 text-xs">
          {incoming.map((e) => <li key={e.id} className="flex items-center justify-between gap-2"><span className="truncate text-fg-2">{names[e.source]} → this{e.label ? ` (${e.label})` : ''}</span><IconButton label={`Remove connection from ${names[e.source]}`} size="sm" onClick={() => onOps(removeEdgeOps(ops, e.source, e.target))} disabled={busy}><Trash2 className="h-3.5 w-3.5" /></IconButton></li>)}
          {outgoing.map((e) => <li key={e.id} className="flex items-center justify-between gap-2"><span className="truncate text-fg-2">this → {names[e.target]}{e.label ? ` (${e.label})` : ''}</span><IconButton label={`Remove connection to ${names[e.target]}`} size="sm" onClick={() => onOps(removeEdgeOps(ops, e.source, e.target))} disabled={busy}><Trash2 className="h-3.5 w-3.5" /></IconButton></li>)}
          {!incoming.length && !outgoing.length && <li className="text-fg-3">Not connected to anything.</li>}
        </ul>
        {others.length > 0 && (
          <div className="mt-2 flex items-center gap-2">
            <Select label="Connect to" className="min-w-0 flex-1" placeholder="Connect to…" value={target} onValueChange={setTarget} options={others.map((n) => ({ value: n.id, label: n.name }))} />
            <Button size="sm" disabled={!target || busy} onClick={() => { onOps([...ops, { op: 'add_edge', source: node.id, target }]); setTarget(''); }}>Connect</Button>
          </div>
        )}
      </div>
      {gaps.length > 0 && (
        <div>
          <p className="micro mb-1.5">Findings on this component</p>
          <ul className="space-y-1 text-xs text-fg-2">{gaps.map((g) => <li key={g.id} className="flex gap-1.5"><Badge tone={g.severity}>{g.severity}</Badge><span>{g.title}</span></li>)}</ul>
        </div>
      )}
      <Button variant="danger" size="sm" leading={<Trash2 className="h-3.5 w-3.5" />} disabled={busy} onClick={() => onOps(removeNodeOps(ops, node.id))}>Remove component</Button>
    </div>
  );
}

/* ---------- the whole editor ---------- */
export function ArchitectureEditor({ design, catalog, onOps, busy, height = 560 }: { design: Design; catalog: Catalog; onOps: (ops: Op[]) => Promise<unknown>; busy: boolean; height?: number }) {
  const arch = design.architecture as Architecture;
  const [selected, setSelected] = useState<string | null>(() => { try { const id = sessionStorage.getItem('studio.select'); sessionStorage.removeItem('studio.select'); return id; } catch { return null; } });
  const past = useRef<Op[][]>([]);
  const future = useRef<Op[][]>([]);
  const [, bump] = useState(0);
  const ops = design.ops as Op[];
  const node = arch.nodes.find((n) => n.id === selected) ?? null;
  const commit = useCallback(async (next: Op[]) => {
    past.current.push(ops);
    future.current = [];
    bump((x) => x + 1);
    const r = await onOps(next);
    if (!r) { past.current.pop(); bump((x) => x + 1); }
  }, [ops, onOps]);
  const undo = async () => { const prev = past.current.pop(); if (!prev) return; future.current.push(ops); bump((x) => x + 1); if (!(await onOps(prev))) { future.current.pop(); past.current.push(prev); bump((x) => x + 1); } };
  const redo = async () => { const nxt = future.current.pop(); if (!nxt) return; past.current.push(ops); bump((x) => x + 1); if (!(await onOps(nxt))) { past.current.pop(); future.current.push(nxt); bump((x) => x + 1); } };
  useEffect(() => { if (selected && !arch.nodes.some((n) => n.id === selected)) setSelected(null); }, [arch, selected]);
  const add = (kind: Catalog['palette'][number]) => {
    const id = nextId(arch, ops);
    void commit([...ops, { op: 'add_node', id, role: kind.role, name: kind.label }]).then(() => setSelected(id));
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Diagram tools">
          <IconButton label="Undo" size="sm" disabled={busy || !past.current.length} onClick={() => void undo()}><Undo2 className="h-4 w-4" /></IconButton>
          <IconButton label="Redo" size="sm" disabled={busy || !future.current.length} onClick={() => void redo()}><Redo2 className="h-4 w-4" /></IconButton>
          <IconButton label="Reset the layout" size="sm" disabled={busy || !ops.some((o) => o.op === 'move_node')} onClick={() => void commit(ops.filter((o) => o.op !== 'move_node'))}><RotateCcw className="h-4 w-4" /></IconButton>
          <span className="mx-1 h-5 w-px bg-line" aria-hidden />
          <span className="micro">Add</span>
          {catalog.palette.map((p) => <Button key={p.kind} size="sm" variant="outline" disabled={busy} title={p.description} aria-label={`Add ${p.label}`} leading={<Plus className="h-3 w-3" aria-hidden />} onClick={() => add(p)}>{p.label}</Button>)}
        </div>
        {arch.skipped_ops.length > 0 && <p role="status" className="rounded border border-medium/30 bg-medium/10 px-3 py-2 text-xs text-fg-2">{arch.skipped_ops.length} edit(s) no longer apply to this architecture and were ignored: {arch.skipped_ops[0].reason}.</p>}
        <Canvas design={design} onOps={(o) => void commit(o)} busy={busy} readOnly={false} height={height} selected={selected} onSelect={setSelected} />
        <p className="text-xs text-fg-3">Drag components to arrange them. Drag from the dot on one component to another to connect them. Select a component to edit it, then press Delete to remove it. Everything you do here is saved as an edit and replayed over your choices, so changing the cloud or database later keeps your edits.</p>
      </div>
      <aside aria-label="Component details" className="hairline rounded-lg border border-line bg-surface p-4 lg:max-h-[640px] lg:overflow-y-auto">
        {node ? <Inspector design={design} catalog={catalog} node={node} onOps={(o) => void commit(o)} busy={busy} /> : (
          <div className="text-sm text-fg-3" data-testid="inspector-empty"><p className="font-medium text-fg-2">No component selected</p><p className="mt-1">Select a component in the diagram to rename it, change its role, set the properties the standards check, or connect it to another component.</p>
            <ul className="mt-3 space-y-1 text-xs">{arch.nodes.map((n) => <li key={n.id}><button type="button" className="w-full truncate rounded px-1.5 py-1 text-left text-fg-2 hover:bg-raised hover:text-fg" onClick={() => setSelected(n.id)}>{n.name}</button></li>)}</ul></div>
        )}
      </aside>
    </div>
  );
}

/** Read-only diagram used beside the choices, so the effect of each choice is visible straight away. */
export function ArchitecturePreview({ design, height = 380 }: { design: Design; height?: number }) {
  if (!design.architecture) return null;
  return <ReactFlowProvider><Canvas design={design} onOps={() => undefined} busy readOnly height={height} selected={null} onSelect={() => undefined} /></ReactFlowProvider>;
}

export function EditorProvider({ children }: { children: React.ReactNode }) {
  return <ReactFlowProvider>{children}</ReactFlowProvider>;
}
