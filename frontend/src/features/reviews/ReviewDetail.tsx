import { CheckCircle2, CircleAlert, CircleX } from 'lucide-react';
import type { AIMeta, Evidence, Severity } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { Badge, SeverityBadge, type Tone } from '@/components/ui/Badge';
import { Panel, ProgressBar, ScoreRing } from '@/components/ui/Panel';
import { EvidenceChip } from '@/components/ui/Timeline';
import { cn } from '@/lib/cn';
import { titleCase } from '@/lib/format';
import { CheckResults, type CheckData } from '../standards/CheckResults';

export interface Finding { id: string; source: string; severity: Severity; title: string; recommendation: string; evidence: Evidence[] }
export interface ReviewData {
  review: {
    submission_id: string; title: string; domain: string; findings: Finding[]; standards: CheckData;
    nfr_coverage: { percent: number; present: string[]; missing: string[]; values: Record<string, unknown> };
    risks: { title: string; severity: Severity; detail?: string }[]; patterns: { pattern: string; aligned: boolean }[];
    readiness: number; verdict: 'go' | 'conditional' | 'no_go'; conditions: string[]; counts: Record<string, number>;
  };
  submission: { id: string; title: string; domain: string; submitter?: string; stage: string; submitted_at?: string; arb_date?: string; tier: string; summary: string };
  ai: AIMeta;
}

const NFR_LABEL: Record<string, string> = { availability: 'Availability %', rto_hours: 'RTO (hours)', rpo_minutes: 'RPO (minutes)', latency_ms: 'p95 latency (ms)', throughput_tps: 'Throughput (tps)', compliance: 'Compliance' };

export const VERDICT: Record<string, { label: string; tone: Tone; Icon: typeof CheckCircle2 }> = {
  go: { label: 'Go', tone: 'healthy', Icon: CheckCircle2 },
  conditional: { label: 'Conditional', tone: 'high', Icon: CircleAlert },
  no_go: { label: 'No go', tone: 'critical', Icon: CircleX },
};

export function VerdictBadge({ verdict }: { verdict: string }) {
  const v = VERDICT[verdict] ?? VERDICT.conditional;
  return <Badge tone={v.tone} dot>{v.label}</Badge>;
}

export function ReviewDetail({ data, loading }: { data?: ReviewData; loading?: boolean }) {
  const r = data?.review;
  const v = r ? VERDICT[r.verdict] : null;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <Panel>
          <div className="flex items-center gap-5">
            <ScoreRing score={r?.readiness ?? 0} size={104} />
            <div className="min-w-0">
              <p className="micro">ARB readiness</p>
              {v && <p className={cn('mt-1 flex items-center gap-1.5 text-xl font-semibold', v.tone === 'healthy' ? 'text-healthy' : v.tone === 'high' ? 'text-high' : 'text-critical')}><v.Icon className="h-5 w-5" aria-hidden />{v.label}</p>}
              {r && <div className="mt-2 flex flex-wrap gap-1.5">{(['critical', 'high', 'medium', 'low'] as const).map((s) => r.counts[s] > 0 && <Badge key={s} tone={s} dot>{r.counts[s]} {s}</Badge>)}</div>}
              {data && <p className="mt-2 text-xs text-fg-3">{data.submission.tier.replace('tier', 'Tier ')} · {data.submission.domain}</p>}
            </div>
          </div>
        </Panel>
        <AISummary ai={data?.ai} loading={loading} title="AI review" thinking={['Checking standards', 'Assessing NFR coverage', 'Aligning to patterns', 'Forming a verdict']} />
      </div>

      {r && (
        <>
          <div className="grid items-start gap-4 lg:grid-cols-3">
            <Panel title="Non-functional requirements" description={`${r.nfr_coverage.percent}% stated`}>
              <ProgressBar value={r.nfr_coverage.percent} tone={r.nfr_coverage.percent >= 80 ? 'healthy' : 'high'} label="NFR coverage" />
              <ul className="mt-3 space-y-1 text-xs">
                {r.nfr_coverage.present.map((k) => <li key={k} className="flex justify-between gap-2"><span className="text-fg-2">{NFR_LABEL[k] ?? titleCase(k)}</span><span className="num font-mono text-fg">{Array.isArray(r.nfr_coverage.values[k]) ? (r.nfr_coverage.values[k] as string[]).join(', ') : String(r.nfr_coverage.values[k])}</span></li>)}
                {r.nfr_coverage.missing.map((k) => <li key={k} className="flex justify-between gap-2"><span className="text-fg-2">{NFR_LABEL[k] ?? titleCase(k)}</span><Badge tone="high">Missing</Badge></li>)}
              </ul>
            </Panel>
            <Panel title="Pattern alignment" description="Approved reference patterns">
              <ul className="space-y-2 text-sm">
                {r.patterns.map((p) => <li key={p.pattern} className="flex items-center justify-between gap-2"><span className="text-fg-2">{p.pattern}</span>{p.aligned ? <Badge tone="healthy" dot>Aligned</Badge> : <Badge dot>Not used</Badge>}</li>)}
              </ul>
            </Panel>
            <Panel title="Conditions to approve" description={r.conditions.length ? `${r.conditions.length} must be met` : 'None'}>
              {r.conditions.length ? (
                <ol className="max-h-56 space-y-2 overflow-y-auto text-xs text-fg-2">
                  {r.conditions.map((c, i) => <li key={i} className="flex gap-2"><span className="num font-mono text-fg-3">{i + 1}.</span>{c}</li>)}
                </ol>
              ) : <p className="text-sm text-fg-2">Ready to proceed to the ARB without conditions.</p>}
            </Panel>
          </div>

          <Panel title="Findings" description={`${r.findings.length} items, most severe first`} flush>
            <ul className="divide-y divide-line-subtle">
              {r.findings.map((f) => (
                <li key={f.id} className="grid gap-x-4 gap-y-1 px-4 py-3 md:grid-cols-[88px_minmax(0,1fr)]">
                  <div><SeverityBadge severity={f.severity} /></div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-fg">{f.title}</p>
                    <p className="mt-0.5 text-xs text-fg-2">{f.recommendation}</p>
                    {f.evidence.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1.5">{f.evidence.map((e, i) => <EvidenceChip key={i} label={e.label} kind={e.kind} />)}</div>}
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
          <CheckResults data={r.standards} />
        </>
      )}
    </div>
  );
}
