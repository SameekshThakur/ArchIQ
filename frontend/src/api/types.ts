/* Hand-written response types for the ArchIQ API (see http://localhost:8000/docs for the OpenAPI schema). */

export interface Evidence {
  kind: string;
  id: string;
  label: string;
}
export interface TraceStep {
  label: string;
  detail?: string | null;
  duration_ms: number;
}
export interface AIMeta {
  confidence: number;
  evidence: Evidence[];
  reasoning_steps: TraceStep[];
  generated_at: string;
  provider: string;
  model?: string | null;
  summary?: string | null;
  task?: string | null;
}
export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  facets?: Record<string, Record<string, number>>;
}
export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';
export interface OwnerRef {
  id: string;
  name: string;
  team: string;
}
export interface Asset {
  id: string;
  type: string;
  name: string;
  domain?: string | null;
  lifecycle: string;
  criticality: string;
  owner?: OwnerRef;
  tech: string[];
  cloud: string;
  [k: string]: unknown;
}
export interface Ref {
  id: string;
  type: string;
  name: string;
}

/* overview */
export interface Kpi {
  key: string;
  label: string;
  value: number;
  unit?: string;
  delta: number | null;
  tone: string;
  href: string;
  spark?: number[];
}
export interface ChainNode {
  id: string;
  name: string;
  type: string;
  integration?: string | null;
  style?: string | null;
  payload?: string | null;
}
export interface Overview {
  enterprise: string;
  reference_date: string;
  kpis: Kpi[];
  nav_badges: Record<string, number>;
  ai: AIMeta;
  domains: { domain: string; debt: number; apps: number }[];
  top_risks: { id: string; title: string; severity: Severity; category: string; domain: string; affected: number }[];
  top_debt: { app_id: string; name: string; domain: string; overall: number }[];
  chain: ChainNode[];
  waves: { id: string; name: string; items: number; start_week: number; end_week: number; risk: string }[];
  activity: { kind: string; title: string; at: string; ref: { type: string; id: string } }[];
  counts: Record<string, number>;
}

/* graph */
export interface GraphNode {
  id: string;
  name: string;
  type: string;
  domain?: string | null;
  lifecycle: string;
  criticality?: string | null;
  degree: number;
  /** Only on a collapsed domain: how many nodes it stands for, and which. */
  members?: number;
  memberIds?: string[];
}
export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  rel: string;
  style?: string | null;
  /** Only on links between collapsed domains: how many real links they stand for, by relationship type. */
  count?: number;
  rels?: Record<string, number>;
}
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
}
export interface PathNode {
  id: string;
  name: string;
  type: string;
  rel?: string | null;
  payload?: string | null;
}

/* copilot */
export interface CopilotCard {
  type: 'table' | 'paths' | 'metrics' | 'graph' | 'bullets' | 'kv' | 'compare';
  title?: string;
  [k: string]: unknown;
}
export interface CopilotResult {
  query: string;
  intent: string;
  headline: string;
  answer: string;
  cards: CopilotCard[];
  followups: string[];
  entities: { kind: string; id: string | null; name: string }[];
  ai: AIMeta;
}

export interface GraphView {
  id: number;
  name: string;
  layers: string[];
  hops: number;
  color_by: 'type' | 'criticality' | 'lifecycle';
  focus?: string | null;
  domains: string[];
  criticality: string[];
  relations?: string[];
  collapsed?: string[];
  created_at?: string;
}
