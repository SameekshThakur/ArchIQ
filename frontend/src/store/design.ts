import { create } from 'zustand';

export interface Nfr {
  availability: number;
  rto_hours: number;
  rpo_minutes: number;
  latency_ms: number;
  throughput_tps: number;
  compliance: string[];
  budget_k: number;
  timeline_months: number;
}

export const DEFAULT_NFR: Nfr = { availability: 99.95, rto_hours: 2, rpo_minutes: 5, latency_ms: 800, throughput_tps: 900, compliance: ['GDPR', 'SOX'], budget_k: 2500, timeline_months: 12 };
export const DEFAULT_WEIGHTS: Record<string, number> = { cost: 20, security: 25, scalability: 25, complexity: 15, time_to_market: 15 };

interface DesignState {
  goals: string;
  domain: string;
  nfr: Nfr;
  weights: Record<string, number>;
  set: (p: Partial<Pick<DesignState, 'goals' | 'domain' | 'nfr' | 'weights'>>) => void;
}

/** The design brief is shared by Target Architecture and the Decision agent, so a decision is always made on the same requirements. */
export const useDesign = create<DesignState>((set) => ({
  goals: 'Modernise claims intake so it survives storm-season peaks without sizing every system of record for burst load.',
  domain: 'Claims',
  nfr: DEFAULT_NFR,
  weights: DEFAULT_WEIGHTS,
  set: (p) => set(p),
}));
