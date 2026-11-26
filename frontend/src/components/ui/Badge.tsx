import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export type Tone = 'neutral' | 'accent' | 'critical' | 'high' | 'medium' | 'low' | 'healthy';

const toneClass: Record<Tone, string> = {
  neutral: 'bg-raised text-fg-2 border-line',
  accent: 'bg-accent/10 text-accent border-accent/25',
  critical: 'bg-critical/10 text-critical border-critical/25',
  high: 'bg-high/10 text-high border-high/25',
  medium: 'bg-medium/10 text-medium border-medium/25',
  low: 'bg-low/10 text-low border-low/25',
  healthy: 'bg-healthy/10 text-healthy border-healthy/25',
};

const dotClass: Record<Tone, string> = {
  neutral: 'bg-fg-3',
  accent: 'bg-accent',
  critical: 'bg-critical',
  high: 'bg-high',
  medium: 'bg-medium',
  low: 'bg-low',
  healthy: 'bg-healthy',
};

export function Badge({
  tone = 'neutral',
  children,
  mono,
  dot,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  mono?: boolean;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex h-5 items-center gap-1.5 whitespace-nowrap rounded border px-1.5 text-[11px] font-medium leading-none',
        mono && 'font-mono',
        toneClass[tone],
        className,
      )}
    >
      {dot && <span className={cn('h-1.5 w-1.5 rounded-full', dotClass[tone])} aria-hidden />}
      {children}
    </span>
  );
}

export const Pill = Badge;

export function StatusDot({ tone = 'healthy', pulse, label }: { tone?: Tone; pulse?: boolean; label?: string }) {
  return (
    <span
      role={label ? 'img' : undefined}
      aria-label={label}
      className={cn('inline-block h-2 w-2 shrink-0 rounded-full', dotClass[tone], pulse && 'animate-pulseDot')}
    />
  );
}

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  const tone: Tone = severity === 'info' ? 'neutral' : severity;
  return (
    <Badge tone={tone} dot className={cn('capitalize', className)}>
      {severity}
    </Badge>
  );
}

export function severityTone(s: string): Tone {
  return s === 'critical' || s === 'high' || s === 'medium' || s === 'low' ? s : 'neutral';
}

const avatarHues = [250, 190, 28, 330, 150, 210, 280, 45];

export function Avatar({ name, size = 24, className }: { name: string; size?: number; className?: string }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('');
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const hue = avatarHues[h % avatarHues.length];
  return (
    <span
      aria-label={name}
      title={name}
      className={cn('inline-flex shrink-0 select-none items-center justify-center rounded-full font-medium text-white', className)}
      style={{
        width: size,
        height: size,
        fontSize: Math.max(9, size * 0.4),
        background: `linear-gradient(135deg, hsl(${hue} 55% 46%), hsl(${(hue + 40) % 360} 55% 38%))`,
      }}
    >
      {initials}
    </span>
  );
}
