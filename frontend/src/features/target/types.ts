import type { AIMeta, Evidence } from '@/api/types';

export interface Option {
  id: string;
  key: string;
  name: string;
  short: string;
  summary: string;
  fit_score: number;
  scores: Record<string, number>;
  diagram: string;
  components: { name: string; role: string; technology: string }[];
  pros: string[];
  cons: string[];
  estimated_cost_k: number;
  estimated_months: number;
  pattern_id?: string;
}
export interface Evaluation {
  weights: Record<string, number>;
  criteria: { key: string; label: string }[];
  matrix: { option: string; name: string; scores: Record<string, number>; weighted: number; rank: number; contribution: Record<string, number> }[];
  ranking: { option: string; score: number }[];
  radar: { option: string; name: string; values: number[] }[];
  recommendation: { option: string; name: string; headline: string; reasons: string[]; margin: number; runner_up: string };
  sensitivity: { criterion: string; label: string; flips: { factor: number; winner: string; changed: boolean }[]; robust: boolean }[];
  evidence: Evidence[];
  confidence: number;
  ai: AIMeta;
}
export interface OptionsResult {
  domain: string;
  goals: string;
  options: Option[];
  systems: string[];
  evaluation: Evaluation;
  ai: AIMeta;
}
export interface AdrResult {
  number: string;
  title: string;
  markdown: string;
  filename: string;
  recommendation: Evaluation['recommendation'];
  confidence: number;
  evidence: Evidence[];
  ai: AIMeta;
}
