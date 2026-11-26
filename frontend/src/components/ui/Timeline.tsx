import { Check, Loader2 } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Badge, type Tone } from './Badge';

/* ---------- Timeline (vertical activity feed) ---------- */
export interface TimelineItem {
  id: string;
  title: ReactNode;
  meta?: ReactNode;
  body?: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
}

const dot: Record<Tone, string> = {
  neutral: 'border-fg-3 text-fg-3',
  accent: 'border-accent text-accent',
  critical: 'border-critical text-critical',
  high: 'border-high text-high',
  medium: 'border-medium text-medium',
  low: 'border-low text-low',
  healthy: 'border-healthy text-healthy',
};

export function Timeline({ items, className }: { items: TimelineItem[]; className?: string }) {
  return (
    <ol className={cn('relative space-y-4', className)}>
      {items.map((it, i) => (
        <li key={it.id} className="relative flex gap-3">
          {i < items.length - 1 && <span className="absolute bottom-[-16px] left-[9px] top-5 w-px bg-line" aria-hidden />}
          <span
            className={cn(
              'z-[1] mt-0.5 flex h-[19px] w-[19px] shrink-0 items-center justify-center rounded-full border bg-surface',
              dot[it.tone ?? 'neutral'],
            )}
          >
            {it.icon ?? <span className="h-1.5 w-1.5 rounded-full bg-current" />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-3">
              <div className="min-w-0 text-sm text-fg">{it.title}</div>
              {it.meta && <div className="shrink-0 text-[11px] text-fg-3">{it.meta}</div>}
            </div>
            {it.body && <div className="mt-0.5 text-xs text-fg-2">{it.body}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

/* ---------- Stepper (progress trace for AI runs) ---------- */
export type StepState = 'pending' | 'active' | 'done' | 'error';

export interface StepItem {
  id: string;
  label: string;
  detail?: ReactNode;
  state: StepState;
  durationMs?: number;
}

export function Stepper({ steps, className }: { steps: StepItem[]; className?: string }) {
  return (
    <ol className={cn('space-y-0', className)} aria-label="Progress">
      {steps.map((s, i) => (
        <li key={s.id} className="relative flex gap-3 pb-3.5 last:pb-0">
          {i < steps.length - 1 && (
            <span
              aria-hidden
              className={cn('absolute bottom-0 left-[9px] top-5 w-px', s.state === 'done' ? 'bg-accent/50' : 'bg-line')}
            />
          )}
          <span
            className={cn(
              'z-[1] flex h-[19px] w-[19px] shrink-0 items-center justify-center rounded-full border text-[10px]',
              s.state === 'done' && 'border-accent bg-accent text-accent-fg',
              s.state === 'active' && 'border-accent bg-surface text-accent',
              s.state === 'pending' && 'border-line bg-surface text-fg-3',
              s.state === 'error' && 'border-critical bg-critical/10 text-critical',
            )}
          >
            {s.state === 'done' ? (
              <Check className="h-3 w-3" strokeWidth={3} />
            ) : s.state === 'active' ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : s.state === 'error' ? (
              '!'
            ) : (
              <span className="num font-mono">{i + 1}</span>
            )}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-3">
              <span className={cn('text-sm', s.state === 'pending' ? 'text-fg-3' : 'text-fg')}>{s.label}</span>
              {s.durationMs !== undefined && s.state === 'done' && (
                <span className="num font-mono text-[11px] text-fg-3">{(s.durationMs / 1000).toFixed(1)}s</span>
              )}
            </div>
            {s.detail && s.state !== 'pending' && <div className="mt-0.5 text-xs text-fg-3">{s.detail}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function EvidenceChip({ label, onClick, kind }: { label: string; onClick?: () => void; kind?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-5 max-w-[220px] items-center gap-1 rounded border border-line bg-raised px-1.5 font-mono text-[10.5px] text-fg-2 transition-colors duration-150 hover:border-accent/50 hover:text-accent"
    >
      {kind && <span className="text-fg-3">{kind}</span>}
      <span className="truncate">{label}</span>
    </button>
  );
}

export function TagList({ tags, tone = 'neutral' }: { tags: string[]; tone?: Tone }) {
  return (
    <div className="flex flex-wrap gap-1">
      {tags.map((t) => (
        <Badge key={t} tone={tone}>
          {t}
        </Badge>
      ))}
    </div>
  );
}
