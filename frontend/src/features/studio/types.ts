import type { AIMeta } from '@/api/types';

export interface Opt { id: string; label: string; note?: string }
export interface Notice { technology: string; standard_id: string | null; status: string | null; lifecycle: string | null; support_end: string | null; estate_apps: number }
export interface Posture { id: string; label: string; description: string; standards: string[] }
export interface PropRow { key: string; label: string; kind: 'bool' | 'choice' | 'number'; options?: string[] | null }

export interface Catalog {
  blueprints: { id: string; name: string; category: string; summary: string; status: string; adoption_count: number; tags: string[]; roles: string[]; nodes: number; edges: number; defaults: Record<string, unknown>; standards: string[] }[];
  clouds: (Opt & { covered: boolean })[];
  deployments: Record<string, (Opt & { type: string; technology: string })[]>;
  llms: (Opt & { type: string | null; technology: string | null; notice: Notice | null })[];
  databases: (Opt & { notice: Notice | null })[];
  backends: (Opt & { technology: string; framework: string; notice: Notice | null })[];
  messaging: Opt[];
  iac: Opt[];
  regions: Opt[];
  approved_regions: string[];
  tiers: Opt[];
  classifications: Opt[];
  exposure: Opt[];
  posture: Posture[];
  palette: { kind: string; role: string; label: string; description: string }[];
  roles: Record<string, string>;
  prop_schema: Record<string, PropRow[]>;
  type_labels: Record<string, string>;
  coverage_floor: number;
  coverage_note: string;
  domains: string[];
  apps: { id: string; name: string; domain: string; lifecycle: string }[];
  nfr_fields: { key: string; label: string; kind: 'number' | 'text' }[];
}

export type Selections = {
  cloud: string; region: string; deployment: string; llm: string; databases: string[]; backend: string; messaging: string; iac: string; exposure: string; tier: string;
  classification: string | null; posture: string[]; instances: number | null; retention_days: number | null; personal_data?: boolean;
};

export interface Fix {
  label: string;
  selections_set?: Record<string, unknown>;
  posture_add?: string[];
  databases_replace?: Record<string, string>;
  nfr?: Record<string, unknown>;
  ops?: Record<string, unknown>[];
  ops_drop?: Record<string, unknown>[];
  input?: { field: string; kind: 'choice' | 'number' | 'text'; label: string; options?: string[]; min?: number; max?: number };
  alternatives?: Fix[];
}

export interface Evidence { kind: string; id: string; label: string }
export interface Gap {
  id: string; source: string; severity: 'critical' | 'high' | 'medium' | 'low'; title: string; detail: string; evidence: Evidence[]; components: string[]; component_names: string[]; recommendation: string;
  fix: Fix | null; standard_id: string | null; category: string; state: 'open' | 'accepted' | 'modified' | 'risk_accepted';
  decision: { status: string; note?: string; at: string; fix_label?: string } | null;
}

export interface Node {
  id: string; name: string; label: string; role: string; role_label: string; type: string; type_label: string; technology: string | null; hosting: { label: string; technology: string } | null;
  group: string | null; origin: 'blueprint' | 'added' | 'control'; props: Record<string, unknown>; prop_origin: Record<string, string>; assessed: boolean; notes: string[];
  pos: { x: number; y: number }; auto_pos: { x: number; y: number }; estate?: { id: string; kind: string; name: string; lifecycle: string; criticality: string; technology: string; domain: string } | null;
}
export interface Edge { id: string; source: string; target: string; label: string; dashed: boolean; blocked: boolean; origin: string }
export interface Architecture { blueprint_id: string; direction: 'LR' | 'TB'; nodes: Node[]; edges: Edge[]; notes: string[]; skipped_ops: { reason: string }[]; node_size: { w: number; h: number } }

export interface StdResult { standard_id: string; title: string; category: string; severity: string; status: 'pass' | 'warn' | 'fail'; rationale: string; remediation: string }
export interface Validation {
  readiness: number; verdict: 'go' | 'conditional' | 'no_go'; engine_verdict: string; counts: Record<string, number>; open_counts: Record<string, number>; gaps: Gap[];
  coverage: { assessed: number; total: number; percent: number; not_assessed: { id: string; name: string; type: string; reason: string }[] };
  standards: { results: StdResult[]; passed: number; warned: number; failed: number; score: number };
  nfr_coverage: { percent: number; present: string[]; missing: string[]; values: Record<string, unknown> };
  estate_risks: { finding_id: string; title: string; severity: string; linked: string[] }[];
  patterns: { pattern: string; aligned: boolean }[];
  conditions: string[]; basis: string; notices: { id: string; text: string }[];
  checks_run: { id: string; label: string; detail: string; engine: string }[];
  resolved: { id: string; status: string; fix_label?: string; at: string }[];
}

export interface Fact { key: string; label: string; value: string | number; evidence: string }
export interface Signal { label: string; weight: number; term: string; evidence: string }
export interface Recommendation {
  recommended: { id: string; name: string; title: string; confidence: number; score: number; margin: number; rationale: Signal[]; when_overlap: string[]; watch_outs: string[]; when_to_use: string[] } | null;
  alternatives: { id: string; name: string; category?: string; score: number; matched?: string[]; why_not: string; choose_when: string }[];
  combine: { id: string; name: string; reason: string }[];
  needs_more_detail: boolean; threshold: number; message: string;
}
export interface Extraction {
  text: string; words: number; nfr: Record<string, unknown>; tier: string | null; exposure: string | null; classification: string | null; residency: { evidence: string } | null; domain: { value: string | null; basis: string };
  facts: Fact[]; systems: { id: string; name: string; lifecycle: string; criticality: string; evidence: string }[]; nfr_missing: string[]; nfr_present: string[]; hints: Record<string, { value: unknown; evidence: string; assumed: boolean }>;
}

export interface Check { id: string; label: string; ok: boolean; blocking: boolean; detail: string }
export interface ExportPreview {
  root: string; manifest: { path: string; bytes: number; what: string; checked_by: string }[]; checks: { label: string; status: 'pass' | 'fail'; detail: string }[]; passed: number; failed: number; not_run: string[]; notes: string[];
}
export interface VersionRow { n: number; at: string; label: string; hash: string; changes: string[]; summary: { readiness: number; verdict: string; open: Record<string, number>; coverage: number; components: number } }

export type DesignStatus = 'draft' | 'validated' | 'submitted' | 'changed_after_submission';
export interface Design {
  n: number; ref: string; title: string; domain: string; owner: string; status: DesignStatus; created_at: string; updated_at?: string;
  requirement: { text: string }; extraction: Extraction; recommendation: Recommendation; ranking: { id: string; name: string; score: number }[];
  ai: { requirements: AIMeta; recommendation: AIMeta };
  blueprint_id: string | null; blueprint_choice: { overridden: boolean; reason: string } | null;
  selections: Selections; selection_sources: Record<string, string>; nfr: Record<string, unknown>; nfr_origin: Record<string, string>; ops: Record<string, unknown>[]; linked_apps: string[];
  decisions: Record<string, { status: string; note?: string; at: string; fix_label?: string; title?: string }>;
  versions: VersionRow[]; workflow: { at: string; event: string; note: string }[];
  submission: { arb_id: string; submitted_at: string; version: number; stage: string; readiness: number; verdict: string; conditions: number; notes: string } | null;
  architecture: Architecture | null; validation: Validation | null; recorded_validation: { at: string; hash: string; readiness: number; verdict: string } | null; checks: Check[]; export: ExportPreview | null;
  narration?: AIMeta;
}

export interface DesignRow { n: number; ref: string; title: string; domain: string | null; blueprint_id: string | null; status: DesignStatus; created_at: string; updated_at?: string; versions: number; arb_id: string | null; readiness: number | null; verdict: string | null }
