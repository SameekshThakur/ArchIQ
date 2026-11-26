import { useId, type HTMLAttributes, type ReactNode } from 'react';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { cn } from '@/lib/cn';

export function Panel({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
  flush,
  ...rest
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  bodyClassName?: string;
  flush?: boolean;
} & Omit<HTMLAttributes<HTMLElement>, 'title'>) {
  return (
    <section className={cn('hairline flex min-w-0 flex-col rounded-lg border border-line bg-surface', className)} {...rest}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-line-subtle px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="truncate text-sm font-semibold text-fg">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-fg-3">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={cn('min-h-0 flex-1', !flush && 'p-4', bodyClassName)}>{children}</div>
    </section>
  );
}

export const Card = Panel;

/* ---------- Sparkline ---------- */
export function Sparkline({
  data,
  width = 96,
  height = 28,
  tone = 'accent',
  className,
}: {
  data: number[];
  width?: number;
  height?: number;
  tone?: 'accent' | 'healthy' | 'critical' | 'high';
  className?: string;
}) {
  const id = useId();
  if (data.length < 2) return <svg width={width} height={height} aria-hidden />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pad = 2;
  const pts = data.map((d, i) => [
    pad + (i / (data.length - 1)) * (width - pad * 2),
    height - pad - ((d - min) / span) * (height - pad * 2),
  ]);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const area = `${line} L${pts[pts.length - 1][0]},${height} L${pts[0][0]},${height} Z`;
  const color = `rgb(var(--${tone}))`;
  const last = pts[pts.length - 1];
  return (
    <svg width={width} height={height} className={className} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.28" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.25" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="2" fill={color} />
    </svg>
  );
}

/* ---------- MetricTile ---------- */
export function MetricTile({
  label,
  value,
  delta,
  deltaGoodWhen = 'down',
  unit,
  spark,
  sparkTone,
  hint,
  onClick,
  className,
}: {
  label: string;
  value: ReactNode;
  delta?: number;
  /** whether a rising number is good ("up") or bad ("down") */
  deltaGoodWhen?: 'up' | 'down';
  unit?: string;
  spark?: number[];
  sparkTone?: 'accent' | 'healthy' | 'critical' | 'high';
  hint?: string;
  onClick?: () => void;
  className?: string;
}) {
  const good = delta === undefined || delta === 0 ? null : (delta > 0) === (deltaGoodWhen === 'up');
  const Arrow = delta === undefined || delta === 0 ? Minus : delta > 0 ? ArrowUpRight : ArrowDownRight;
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className={cn(
        'hairline flex min-h-[108px] min-w-0 flex-col justify-between gap-3 rounded-lg border border-line bg-surface p-3.5 text-left transition-colors duration-150',
        onClick && 'hover:border-fg-3/40 hover:bg-raised/60',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="micro">{label}</span>
        {delta !== undefined && (
          <span
            className={cn(
              'num inline-flex items-center gap-0.5 font-mono text-[11px]',
              good === null ? 'text-fg-3' : good ? 'text-healthy' : 'text-critical',
            )}
          >
            <Arrow className="h-3 w-3" aria-hidden />
            {Math.abs(delta)}%
          </span>
        )}
      </div>
      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0">
          <div className="num whitespace-nowrap text-2xl font-semibold text-fg">
            {value}
            {unit && unit !== '%' && <span className="ml-1 text-sm font-normal text-fg-3">{unit}</span>}
            {unit === '%' && <span className="ml-0.5 text-sm font-normal text-fg-3">%</span>}
          </div>
          {hint && <div className="mt-0.5 truncate text-xs text-fg-3">{hint}</div>}
        </div>
        {spark && <Sparkline data={spark} tone={sparkTone ?? (good === false ? 'critical' : 'accent')} />}
      </div>
    </Tag>
  );
}

/* ---------- KeyValueList ---------- */
export function KeyValueList({
  items,
  className,
}: {
  items: { label: string; value: ReactNode; mono?: boolean }[];
  className?: string;
}) {
  return (
    <dl className={cn('grid grid-cols-[132px_1fr] gap-x-4 gap-y-2.5 text-sm', className)}>
      {items.map((it) => (
        <div key={it.label} className="contents">
          <dt className="micro self-center">{it.label}</dt>
          <dd className={cn('min-w-0 break-words text-fg', it.mono && 'font-mono text-xs')}>{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ---------- EmptyState ---------- */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-col items-start gap-3 rounded-lg border border-dashed border-line px-6 py-8', className)}>
      {icon && (
        <span className="flex h-9 w-9 items-center justify-center rounded-md border border-line bg-raised text-fg-2">
          {icon}
        </span>
      )}
      <div>
        <p className="text-sm font-medium text-fg">{title}</p>
        {description && <p className="mt-1 max-w-md text-xs text-fg-3">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/* ---------- Skeleton ---------- */
export function Skeleton({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={cn('skeleton h-4 w-full', className)} style={style} aria-hidden />;
}

export function SkeletonRows({ rows = 6, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('space-y-2.5', className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-3 w-4" />
          <Skeleton className="h-3" style={{ width: `${55 + ((i * 17) % 35)}%` }} />
          <Skeleton className="ml-auto h-3 w-14" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonTile({ className }: { className?: string }) {
  return (
    <div className={cn('flex min-h-[108px] flex-col justify-between rounded-lg border border-line bg-surface p-3.5', className)} role="status" aria-label="Loading">
      <Skeleton className="h-2.5 w-16" />
      <Skeleton className="h-7 w-20" />
    </div>
  );
}

export function SkeletonBlock({ className }: { className?: string }) {
  return <div className={cn('skeleton rounded-lg', className)} role="status" aria-label="Loading" />;
}

/* ---------- ProgressBar ---------- */
const barTone = {
  accent: 'accent-bg',
  healthy: 'bg-healthy',
  critical: 'bg-critical',
  high: 'bg-high',
  medium: 'bg-medium',
  low: 'bg-low',
} as const;

export function ProgressBar({
  value,
  tone = 'accent',
  className,
  label,
}: {
  value: number;
  tone?: 'accent' | 'healthy' | 'critical' | 'high' | 'medium' | 'low';
  className?: string;
  label?: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn('h-1.5 w-full overflow-hidden rounded-full bg-raised', className)}
    >
      <div
        className={cn('h-full rounded-full transition-[width] duration-220', barTone[tone])}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/* ---------- ScoreRing ---------- */
export function scoreColor(score: number, invert = false) {
  const s = invert ? 100 - score : score;
  if (s >= 80) return 'healthy';
  if (s >= 60) return 'medium';
  if (s >= 40) return 'high';
  return 'critical';
}

export function ScoreRing({
  score,
  size = 96,
  stroke = 7,
  label,
  invert,
  className,
}: {
  score: number;
  size?: number;
  stroke?: number;
  label?: string;
  /** when true, a high score is bad (e.g. debt) */
  invert?: boolean;
  className?: string;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score));
  const color = `rgb(var(--${scoreColor(score, invert)}))`;
  return (
    <div className={cn('relative inline-flex shrink-0 items-center justify-center', className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" role="img" aria-label={`${label ?? 'Score'} ${Math.round(pct)} out of 100`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--border))" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - pct / 100)}
          style={{ transition: 'stroke-dashoffset 600ms var(--ease)' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="num font-mono font-semibold text-fg" style={{ fontSize: size * 0.28 }}>
          {Math.round(pct)}
        </span>
        {label && <span className="micro !text-[9px]">{label}</span>}
      </div>
    </div>
  );
}

/* ---------- AI footer ---------- */
export function AIFooter({
  confidence,
  evidenceCount,
  onViewEvidence,
  className,
  source,
}: {
  confidence: number;
  /** Model that wrote the text, shown only when a real model did (not the built-in narrator). */
  source?: string;
  evidenceCount?: number;
  onViewEvidence?: () => void;
  className?: string;
}) {
  return (
    <div className={cn('flex items-center gap-2 text-[11px] text-fg-3', className)}>
      <span className="accent-bg inline-block h-1.5 w-1.5 rounded-full" aria-hidden />
      <span>AI-generated</span>
      {source && <span className="font-mono text-fg-2">{source}</span>}
      <span aria-hidden>·</span>
      <span>
        confidence <span className="num font-mono text-fg-2">{confidence.toFixed(2)}</span>
      </span>
      {evidenceCount !== undefined && (
        <>
          <span aria-hidden>·</span>
          <button type="button" onClick={onViewEvidence} className="text-accent hover:underline">
            view evidence ({evidenceCount})
          </button>
        </>
      )}
    </div>
  );
}
