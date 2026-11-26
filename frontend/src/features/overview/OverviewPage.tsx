import { ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import type { Overview } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { Chart } from '@/components/viz/LazyChart';
import { useChartTheme } from '@/components/viz/useChartTheme';
import { Badge, SeverityBadge } from '@/components/ui/Badge';
import { MetricTile, Panel, ProgressBar, SkeletonBlock, SkeletonTile, scoreColor } from '@/components/ui/Panel';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { RefLink, useOpenRef } from '@/components/Ref';
import { fmtDate } from '@/lib/format';

function StoryChain({ chain }: { chain: Overview['chain'] }) {
  const open = useOpenRef();
  return (
    <ol className="flex flex-wrap items-stretch gap-2" aria-label="Finance to analytics data flow">
      {chain.map((n, i) => (
        <li key={n.id} className="flex items-center gap-2">
          {i > 0 && (
            <span className="flex flex-col items-center text-[10px] text-fg-3">
              <ArrowRight className="h-4 w-4" aria-hidden />
              <span className="font-mono">{n.style}</span>
            </span>
          )}
          <button type="button" onClick={() => open({ type: 'application', id: n.id })} className="hairline min-w-[150px] rounded-md border border-line bg-raised px-3 py-2 text-left hover:border-accent/50">
            <span className="block text-sm font-medium text-fg">{n.name}</span>
            <span className="block text-[11px] text-fg-3">{i === 0 ? 'Source of record' : n.payload}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}

export default function OverviewPage() {
  const { data, isLoading } = useGet<Overview>('/overview/summary');
  const nav = useNavigate();
  const t = useChartTheme();
  const domainOption = data && {
    grid: { left: 8, right: 36, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', max: 60, axisLabel: { color: t.fg3, fontSize: 10 }, splitLine: { lineStyle: { color: t.lineSubtle } } },
    yAxis: { type: 'category', inverse: true, data: data.domains.map((d) => d.domain), axisLabel: { color: t.fg2, fontSize: 11 }, axisLine: { show: false }, axisTick: { show: false } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'none' }, backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.fg, fontSize: 12 } },
    series: [{ type: 'bar', barWidth: 10, data: data.domains.map((d) => ({ value: d.debt, itemStyle: { color: d.debt >= 35 ? t.critical : d.debt >= 28 ? t.high : t.accent, borderRadius: 3 } })), label: { show: true, position: 'right', color: t.fg2, fontSize: 11 } }],
  };
  const maxWeek = data ? Math.max(...data.waves.map((w) => w.end_week)) : 1;
  return (
    <Page>
      <PageHeader title="Executive overview" description={`Estate health, the risks that matter and what the AI recommends next.`} freshness={data ? `Data as of ${fmtDate(data.reference_date)}` : undefined} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {isLoading || !data
          ? Array.from({ length: 6 }).map((_, i) => <SkeletonTile key={i} />)
          : data.kpis.map((k) => (
              <MetricTile key={k.key} label={k.label} value={k.value} unit={k.unit === '%' ? '%' : undefined} hint={k.unit === '/100' ? 'of 100' : undefined} delta={k.delta ?? undefined} deltaGoodWhen="down" spark={k.spark} sparkTone={k.tone === 'danger' ? 'critical' : k.tone === 'warning' ? 'high' : 'accent'} onClick={() => nav(k.href)} />
            ))}
      </div>

      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <AISummary ai={data?.ai} loading={isLoading} title="AI briefing" thinking={['Aggregating module outputs', 'Ranking risks', 'Drafting the briefing']} />
          <Panel title="Finance to analytics data flow" description="SAP → MuleSoft → Salesforce → Snowflake. A failure at any hop stops billing data reaching the warehouse.">
            {data ? <StoryChain chain={data.chain} /> : <SkeletonBlock className="h-16" />}
          </Panel>
          <Panel title="Top risks" description="Critical assessment findings" actions={<button type="button" className="text-xs text-accent hover:underline" onClick={() => nav('/assessment')}>All findings</button>}>
            <ul className="divide-y divide-line-subtle">
              {data?.top_risks.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="min-w-0"><RefLink type="finding" id={r.id} name={r.title} /><span className="ml-2 text-xs text-fg-3">{r.domain} · {r.affected} affected</span></span>
                  <SeverityBadge severity={r.severity} />
                </li>
              ))}
              {isLoading && <SkeletonBlock className="h-32" />}
            </ul>
          </Panel>
        </div>
        <div className="space-y-4">
          <Panel title="Technical debt by domain" description="Criticality-weighted, 0–100">
            {domainOption ? <Chart option={domainOption} height={270} label="Technical debt by domain" onClick={() => nav('/debt-radar')} /> : <SkeletonBlock className="h-64" />}
          </Panel>
          <Panel title="Modernization roadmap" actions={<button type="button" className="text-xs text-accent hover:underline" onClick={() => nav('/modernization')}>Open plan</button>}>
            <ul className="space-y-3">
              {data?.waves.map((w) => (
                <li key={w.id}>
                  <div className="mb-1 flex items-center justify-between text-xs"><span className="text-fg">{w.name}</span><span className="text-fg-3">{w.items} initiatives · weeks {w.start_week}–{w.end_week}</span></div>
                  <div className="relative h-2 rounded-full bg-raised">
                    <div className="accent-bg absolute h-2 rounded-full" style={{ left: `${(w.start_week / maxWeek) * 100}%`, width: `${((w.end_week - w.start_week) / maxWeek) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Highest-debt applications">
            <ul className="space-y-2.5">
              {data?.top_debt.map((a) => (
                <li key={a.app_id} className="text-xs">
                  <div className="mb-1 flex justify-between"><RefLink type="application" id={a.app_id} name={a.name} /><span className="num font-mono text-fg-2">{a.overall}</span></div>
                  <ProgressBar value={a.overall} tone={scoreColor(a.overall, true) as 'critical'} label={`${a.name} debt`} />
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Recent activity">
            <ul className="space-y-2 text-xs">
              {data?.activity.map((a, i) => (
                <li key={i} className="flex items-start gap-2"><Badge tone={a.kind === 'drift' ? 'critical' : a.kind === 'finding' ? 'high' : 'accent'}>{a.kind}</Badge><span className="min-w-0 text-fg-2"><RefLink type={a.ref.type} id={a.ref.id} name={a.title} /></span></li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </Page>
  );
}
