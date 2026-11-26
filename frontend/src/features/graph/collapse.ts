import type { GraphData, GraphEdge, GraphNode } from '@/api/types';

export const BUBBLE_PREFIX = 'domain:';
export const bubbleId = (domain: string) => `${BUBBLE_PREFIX}${domain}`;
export const isBubble = (id: string) => id.startsWith(BUBBLE_PREFIX);
export const bubbleDomain = (id: string) => id.slice(BUBBLE_PREFIX.length);

const SEVERITY = ['critical', 'high', 'medium', 'low'];

/**
 * Folds each collapsed domain into one bubble.
 *
 * Nodes of a collapsed domain disappear into a single "Domain" node that remembers its members. Links inside the domain vanish
 * with them, and links to the outside are merged into one per pair of endpoints, carrying how many real links they stand for and
 * of what kinds, so a bubble still shows who it talks to. Everything else is left exactly as it was.
 */
export function collapseGraph(data: GraphData, collapsed: string[]): GraphData {
  const fold = new Set(collapsed);
  if (!fold.size) return data;
  const members = new Map<string, GraphNode[]>();
  for (const n of data.nodes) if (n.domain && fold.has(n.domain)) (members.get(n.domain) ?? members.set(n.domain, []).get(n.domain)!).push(n);
  if (!members.size) return data;
  const target = (n: { id: string; domain?: string | null }) => (n.domain && members.has(n.domain) ? bubbleId(n.domain) : n.id);
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  const idOf = (id: string) => { const n = byId.get(id); return n ? target(n) : id; };

  const merged = new Map<string, GraphEdge>();
  const plain: GraphEdge[] = [];
  for (const e of data.edges) {
    const s = idOf(e.source), t = idOf(e.target);
    if (s === t) continue; // inside one folded domain
    if (s === e.source && t === e.target) { plain.push(e); continue; }
    const key = `${s}>${t}`;
    const m = merged.get(key) ?? { id: `agg:${key}`, source: s, target: t, rel: e.rel, count: 0, rels: {} };
    m.count = (m.count ?? 0) + (e.count ?? 1);
    m.rels![e.rel] = (m.rels![e.rel] ?? 0) + (e.count ?? 1);
    merged.set(key, m);
  }
  const edges = [...plain, ...[...merged.values()].map((m) => ({ ...m, rel: Object.entries(m.rels!).sort((a, b) => b[1] - a[1])[0][0] }))];

  const degree = new Map<string, number>();
  for (const e of edges) { degree.set(e.source, (degree.get(e.source) ?? 0) + 1); degree.set(e.target, (degree.get(e.target) ?? 0) + 1); }
  const bubbles: GraphNode[] = [...members.entries()].map(([domain, ms]) => ({
    id: bubbleId(domain),
    name: domain,
    type: 'Domain',
    domain,
    lifecycle: '',
    criticality: SEVERITY.find((s) => ms.some((m) => m.criticality === s)) ?? null,
    degree: degree.get(bubbleId(domain)) ?? 0,
    members: ms.length,
    memberIds: ms.map((m) => m.id),
  }));
  const rest = data.nodes.filter((n) => !(n.domain && members.has(n.domain))).map((n) => ({ ...n, degree: degree.get(n.id) ?? 0 }));
  const nodes = [...rest, ...bubbles];
  return { ...data, nodes, edges, total_nodes: nodes.length, total_edges: edges.length };
}
