import dagre from '@dagrejs/dagre';
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Box, Cloud, Database, Network, Plug, User } from 'lucide-react';
import { memo, useMemo } from 'react';
import { cn } from '@/lib/cn';

export interface FlowNodeIn {
  id: string;
  name: string;
  type: string;
  criticality?: string | null;
  focus?: boolean;
  hop?: number;
  sub?: string;
}
export interface FlowEdgeIn {
  source: string;
  target: string;
  label?: string;
  dashed?: boolean;
  danger?: boolean;
}

const ICON: Record<string, typeof Box> = { application: Box, api: Plug, database: Database, cloud: Cloud, owner: User, capability: Network, App: Box, API: Plug, Data: Database, Cloud: Cloud };
const W = 188;
const H = 52;

type Data = FlowNodeIn & Record<string, unknown>;

const FlowNode = memo(function FlowNode({ data, selected }: NodeProps<Node<Data>>) {
  const Icon = ICON[data.type] ?? Box;
  const crit = data.criticality === 'critical' ? 'border-critical/50' : data.criticality === 'high' ? 'border-high/40' : 'border-line';
  return (
    <div
      className={cn(
        'hairline flex items-center gap-2 rounded-md border bg-surface px-2.5 py-2 text-left shadow-sm transition-colors',
        crit,
        data.focus && 'border-accent ring-2 ring-accent/40',
        selected && 'ring-2 ring-accent/60',
      )}
      style={{ width: W, minHeight: H }}
    >
      <Handle type="target" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-fg-3" />
      <span className={cn('flex h-6 w-6 shrink-0 items-center justify-center rounded bg-raised', data.focus ? 'text-accent' : 'text-fg-2')}>
        <Icon className="h-3.5 w-3.5" aria-hidden />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-xs font-medium text-fg">{data.name}</span>
        <span className="block truncate text-[10px] text-fg-3">{data.sub ?? data.type}</span>
      </span>
      <Handle type="source" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-fg-3" />
    </div>
  );
});

const nodeTypes = { arch: FlowNode };

export function layout(nodes: FlowNodeIn[], edges: FlowEdgeIn[], dir: 'LR' | 'TB' = 'LR') {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: dir, nodesep: 18, ranksep: 70, marginx: 12, marginy: 12 });
  g.setDefaultEdgeLabel(() => ({}));
  const ids = new Set(nodes.map((n) => n.id));
  nodes.forEach((n) => g.setNode(n.id, { width: W, height: H }));
  edges.filter((e) => ids.has(e.source) && ids.has(e.target)).forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return { id: n.id, type: 'arch', position: { x: p.x - W / 2, y: p.y - H / 2 }, data: n as Data } satisfies Node<Data>;
  });
}

/** Layered (dagre) architecture diagram used for impact analysis, dependency chains and blueprints. */
export default function FlowGraph({
  nodes,
  edges,
  direction = 'LR',
  height = 420,
  onNodeClick,
  label,
}: {
  nodes: FlowNodeIn[];
  edges: FlowEdgeIn[];
  direction?: 'LR' | 'TB';
  height?: number;
  onNodeClick?: (id: string) => void;
  label: string;
}) {
  const { rfNodes, rfEdges } = useMemo(() => {
    const ids = new Set(nodes.map((n) => n.id));
    const rfEdges: Edge[] = edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e, i) => ({
        id: `${e.source}-${e.target}-${i}`,
        source: e.source,
        target: e.target,
        label: e.label,
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: e.danger ? 'rgb(var(--critical))' : 'rgb(var(--fg-3))' },
        style: { stroke: e.danger ? 'rgb(var(--critical))' : 'rgb(var(--fg-3))', strokeWidth: 1.2, strokeDasharray: e.dashed ? '5 4' : undefined },
        labelStyle: { fontSize: 10, fill: 'rgb(var(--fg-2))' },
        labelBgStyle: { fill: 'rgb(var(--surface))' },
      }));
    return { rfNodes: layout(nodes, edges, direction), rfEdges };
  }, [nodes, edges, direction]);

  return (
    <div style={{ height }} className="w-full overflow-hidden rounded-md border border-line bg-bg" role="img" aria-label={label}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.15}
        maxZoom={1.6}
        nodesDraggable={false}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, n) => onNodeClick?.(n.id)}
      >
        <Background gap={20} size={1} color="rgb(var(--border-subtle))" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}
