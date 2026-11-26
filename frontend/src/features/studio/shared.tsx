import { AlertTriangle } from 'lucide-react';
import type { ReactNode } from 'react';
import type { useDesignActions } from './useStudio';
import type { Catalog, Design } from './types';

export type Actions = ReturnType<typeof useDesignActions>;
export interface StepProps { design: Design; catalog: Catalog; actions: Actions; go: (step: string) => void }

export function ErrorNote({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <p id={id} role="alert" className="flex items-start gap-2 rounded border border-critical/30 bg-critical/10 px-3 py-2 text-sm text-fg">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-critical" aria-hidden />
      <span>{children}</span>
    </p>
  );
}

export const VERDICT: Record<string, { label: string; tone: 'healthy' | 'medium' | 'critical' }> = {
  go: { label: 'Ready for review', tone: 'healthy' },
  conditional: { label: 'Ready with conditions', tone: 'medium' },
  no_go: { label: 'Not ready', tone: 'critical' },
};

export const STATUS: Record<string, { label: string; tone: 'neutral' | 'accent' | 'healthy' | 'medium' }> = {
  draft: { label: 'Draft', tone: 'neutral' },
  validated: { label: 'Validated', tone: 'accent' },
  submitted: { label: 'Submitted', tone: 'healthy' },
  changed_after_submission: { label: 'Changed since submission', tone: 'medium' },
};

export const STEPS = [
  { id: 'requirements', label: 'Requirements' },
  { id: 'recommendation', label: 'Recommendation' },
  { id: 'customise', label: 'Customise' },
  { id: 'diagram', label: 'Diagram' },
  { id: 'validation', label: 'Validation' },
  { id: 'gaps', label: 'Gaps' },
  { id: 'export', label: 'Export' },
  { id: 'governance', label: 'Governance' },
] as const;
export type StepId = (typeof STEPS)[number]['id'];

export const EXAMPLES = [
  { label: 'Claims intake on Azure', text: 'We need to modernise claims intake for our motor and home lines. Customers and brokers submit claims through a web portal and a mobile app, and claims handlers work them in a case system. Availability must be 99.9% with an RTO of 4 hours and an RPO of 15 minutes. It handles personal data and customer financial records, so data must stay in the UK. Around 300 requests per second at peak, p95 latency under 500 ms. It integrates with the policy administration system and publishes events when a claim changes status.' },
  { label: 'AI assistant for underwriters', text: 'Underwriters want an AI assistant that answers questions over our underwriting guidelines and policy documents, with citations. Retrieval-augmented generation over internal documents, a human must approve any recommendation before it is used, and prompts and responses must be logged. Internal users only, confidential data, 99.5% availability.' },
  { label: 'Partner APIs', text: 'Expose policy quotes and claim status to broker partners through public APIs with OAuth2, rate limiting and a developer portal. 99.95% availability, p95 under 300 ms, RTO 1 hour, RPO 5 minutes. Contains personal data. Needs an audit trail of every call.' },
];
