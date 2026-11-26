import type { GraphData, GraphNode } from '@/api/types';

export interface GraphFilter {
  domains: string[];
  criticality: string[];
  /** Relationship types to keep (calls, owned_by, ...). Empty keeps them all. */
  relations: string[];
}

export const NO_FILTER: GraphFilter = { domains: [], criticality: [], relations: [] };

/** 'hosted_on' → 'Hosted on'. */
export const relationLabel = (rel: string) => { const t = rel.replace(/_/g, ' '); return t.charAt(0).toUpperCase() + t.slice(1); };
export const UNRATED = 'unrated';
export const CRITICALITY_ORDER = ['critical', 'high', 'medium', 'low', UNRATED];

export const isFiltered = (f: GraphFilter) => f.domains.length > 0 || f.criticality.length > 0 || f.relations.length > 0;

/**
 * Narrows a graph to the chosen business domains and criticality levels.
 *
 * Applications, APIs and data stores carry a domain and a criticality, so they must match. Capabilities, owners and cloud
 * resources have neither; they are kept only while they still connect to something that survived, so a filtered view never
 * leaves a scatter of orphans. Degrees are recomputed so node size and hub labels describe the view being looked at.
 */
export function filterGraph(data: GraphData, f: GraphFilter): GraphData {
  if (!isFiltered(f)) return data;
  const domains = new Set(f.domains);
  const crits = new Set(f.criticality);
  const keeps = (n: GraphNode) => {
    if (domains.size && n.domain && !domains.has(n.domain)) return false;
    if (crits.size && n.criticality && !crits.has(n.criticality)) return false;
    // a node that has a domain/criticality field but is empty can only satisfy "unrated"
    if (crits.size && !n.criticality && n.domain && !crits.has(UNRATED)) return false;
    return true;
  };
  const kept = new Map(data.nodes.filter(keeps).map((n) => [n.id, n]));
  const rels = new Set(f.relations);
  const edges = data.edges.filter((e) => kept.has(e.source) && kept.has(e.target) && (!rels.size || rels.has(e.rel)));
  const degree = new Map<string, number>();
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  // domain-less nodes (owners, capabilities, cloud) survive only when connected to something that did; when filtering by
  // relationship, so does everything else, because a node with none of those relationships has no place in that picture
  const nodes = [...kept.values()]
    .filter((n) => (n.domain && !rels.size) || (degree.get(n.id) ?? 0) > 0)
    .map((n) => ({ ...n, degree: degree.get(n.id) ?? 0 }));
  return { ...data, nodes, edges, total_nodes: nodes.length, total_edges: edges.length };
}

/** Distinct domains present in the data, with how many nodes each holds. */
export function domainCounts(data: GraphData): [string, number][] {
  const m = new Map<string, number>();
  for (const n of data.nodes) if (n.domain) m.set(n.domain, (m.get(n.domain) ?? 0) + 1);
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

/** Relationship types present in the data, most common first. */
export function relationCounts(data: GraphData): [string, number][] {
  const m = new Map<string, number>();
  for (const e of data.edges) m.set(e.rel, (m.get(e.rel) ?? 0) + (e.count ?? 1));
  return [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

export function criticalityCounts(data: GraphData): [string, number][] {
  const m = new Map<string, number>();
  for (const n of data.nodes) {
    if (!n.domain && !n.criticality) continue; // only rateable nodes
    const k = n.criticality ?? UNRATED;
    m.set(k, (m.get(k) ?? 0) + 1);
  }
  return CRITICALITY_ORDER.filter((k) => m.has(k)).map((k) => [k, m.get(k)!]);
}

/** Case-insensitive search over the nodes in view: names that start with the query rank first. */
export function searchNodes(nodes: GraphNode[], q: string, limit = 8): GraphNode[] {
  const s = q.trim().toLowerCase();
  if (s.length < 1) return [];
  const scored: [number, GraphNode][] = [];
  for (const n of nodes) {
    const name = n.name.toLowerCase();
    const i = name.indexOf(s);
    if (i < 0 && n.id.toLowerCase() !== s) continue;
    scored.push([i === 0 ? 0 : i < 0 ? 1 : /[\s\-_/]/.test(name[i - 1] ?? '') ? 2 : 3, n]);
  }
  return scored.sort((a, b) => a[0] - b[0] || b[1].degree - a[1].degree || a[1].name.localeCompare(b[1].name)).slice(0, limit).map(([, n]) => n);
}
