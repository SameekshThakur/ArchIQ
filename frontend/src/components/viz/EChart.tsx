import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, GaugeChart, HeatmapChart, LineChart, RadarChart, ScatterChart, TreemapChart } from 'echarts/charts';
import { GridComponent, LegendComponent, MarkLineComponent, RadarComponent, TooltipComponent, VisualMapComponent, TitleComponent, MarkAreaComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption } from 'echarts/core';
import { cn } from '@/lib/cn';

echarts.use([BarChart, LineChart, HeatmapChart, RadarChart, ScatterChart, GaugeChart, TreemapChart, GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, RadarComponent, MarkLineComponent, MarkAreaComponent, TitleComponent, CanvasRenderer]);

export type { EChartsCoreOption };

/** Thin wrapper: canvas renderer, no animation jank on resize, accessible label. */
export default function EChart({ option, height = 260, className, label, onClick }: { option: EChartsCoreOption; height?: number | string; className?: string; label: string; onClick?: (p: { name?: string; data?: unknown; seriesName?: string }) => void }) {
  return (
    <div role="img" aria-label={label} className={cn('w-full', className)}>
      <ReactEChartsCore
        echarts={echarts}
        option={{ backgroundColor: 'transparent', animation: !new URLSearchParams(location.search).has('noanim'), animationDuration: typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 350, animationEasing: 'cubicOut', ...option }}
        style={{ height, width: '100%' }}
        notMerge
        lazyUpdate
        onEvents={onClick ? { click: onClick } : undefined}
      />
    </div>
  );
}
