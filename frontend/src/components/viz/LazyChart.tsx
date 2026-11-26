import { lazy, Suspense } from 'react';
import { Skeleton } from '@/components/ui/Panel';
import type { EChartsCoreOption } from './EChart';

const EChart = lazy(() => import('./EChart'));

/** Lazy-loaded ECharts so chart code stays out of the initial bundle. */
export function Chart({ option, height = 260, label, onClick, className }: { option: EChartsCoreOption; height?: number | string; label: string; onClick?: (p: { name?: string; data?: unknown; seriesName?: string }) => void; className?: string }) {
  return (
    <Suspense fallback={<Skeleton className="w-full" style={{ height: typeof height === 'number' ? height : 260 }} />}>
      <EChart option={option} height={height} label={label} onClick={onClick} className={className} />
    </Suspense>
  );
}

export const LazyMermaid = lazy(() => import('./MermaidView'));
export const LazyFlow = lazy(() => import('./FlowGraph'));
export const LazyForce = lazy(() => import('./ForceGraph'));
