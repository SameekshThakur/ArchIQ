import { useMemo } from 'react';
import { useUI } from '@/store/ui';

const rgb = (name: string, alpha = 1) => {
  // ECharts only understands comma-separated colours, so convert the space-separated token triplet.
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim().split(/\s+/).join(', ');
  return alpha === 1 ? `rgb(${v})` : `rgba(${v}, ${alpha})`;
};

/** Resolves design tokens to concrete colors so ECharts follows the active theme. */
export function useChartTheme() {
  const theme = useUI((s) => s.theme);
  return useMemo(() => {
    void theme;
    return {
      fg: rgb('fg'),
      fg2: rgb('fg-2'),
      fg3: rgb('fg-3'),
      line: rgb('border'),
      lineSubtle: rgb('border-subtle'),
      surface: rgb('surface'),
      raised: rgb('raised'),
      accent: rgb('accent'),
      accent2: rgb('accent-2'),
      critical: rgb('critical'),
      high: rgb('high'),
      medium: rgb('medium'),
      low: rgb('low'),
      healthy: rgb('healthy'),
      alpha: (name: string, a: number) => rgb(name, a),
      /** categorical series palette, validated for light and dark */
      series: [rgb('accent'), rgb('accent-2'), rgb('low'), rgb('healthy'), rgb('high'), rgb('critical')],
      font: 'Inter, system-ui, sans-serif',
    };
  }, [theme]);
}

export type ChartTheme = ReturnType<typeof useChartTheme>;
