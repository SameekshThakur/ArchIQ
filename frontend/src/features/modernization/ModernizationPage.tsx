import { useMutation } from '@tanstack/react-query';
import { Minus, Plus, RotateCcw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { post, useGet } from '@/api/hooks';
import type { AIMeta } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { RefLink } from '@/components/Ref';
import { Badge, type Tone } from '@/components/ui/Badge';
import { Button, IconButton } from '@/components/ui/Button';
import { SegmentedControl } from '@/components/ui/Inputs';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { KeyValueList, MetricTile, Panel, SkeletonBlock, SkeletonTile } from '@/components/ui/Panel';
import { Chart } from '@/components/viz/LazyChart';
import { useChartTheme } from '@/components/viz/useChartTheme';
import { cn } from '@/lib/cn';
import { fmtMoneyK, titleCase } from '@/lib/format';

interface Item { id: string; wave: string; name: string; description: string; asset_ids: string[]; asset_count: number; effort_pd: number; cost_k: number; risk: string; value_k: number; duration_weeks: number; depends_on: string[]; findings: string[]; start_week: number; end_week: number; critical: boolean }
interface Wave { id: string; name: string; theme: string; color: string; items: string[]; start_week: number; end_week: number; cost_k: number; value_k: number; effort_pd: number; asset_count: number; risk: string }
interface Plan { scenario: string; scenario_label: string; blurb: string; waves: Wave[]; items: Item[]; milestones: { id: string; name: string; week: number; wave: string }[]; critical_path: string[]; adjusted: string[]; totals: { duration_weeks: number; cost_k: number; value_k: number; effort_pd: number; assets: number; break_even_month: number }; value_curve: { month: number; cumulative_cost_k: number; cumulative_value_k: number }[]; ai: AIMeta }
interface Scenario { id: string; label: string; blurb: string }

const RISK_TONE: Record<string, Tone> = { low: 'low', medium: 'medium', high: 'high', critical: 'critical' };
const WAVE_BAR: Record<string, string> = { accent: 'bg-accent', low: 'bg-low', healthy: 'bg-healthy', high: 'bg-high' };

function Gantt({ plan, selected, onSelect }: { plan: Plan; selected: string | null; onSelect: (id: string) => void }) {
  const horizon = Math.max(...plan.items.map((i) => i.end_week)) + 2;
  const ticks = Array.from({ length: Math.floor(horizon / 4) + 1 }, (_, i) => i * 4);
  const pct = (w: number) => `${(w / horizon) * 100}%`;
  return (
    <div className="overflow-x-auto" role="figure" aria-label="Modernization roadmap Gantt chart">
      <div className="min-w-[600px]">
        <div className="relative ml-[210px] h-6 border-b border-line text-[10px] text-fg-3">
          {ticks.map((w) => <span key={w} className="num absolute -translate-x-1/2 font-mono" style={{ left: pct(w) }}>W{w}</span>)}
        </div>
        {plan.waves.map((w) => (
          <div key={w.id} className="mt-3">
            <div className="flex items-center gap-2 px-1 py-1"><span className={cn('h-2 w-2 rounded-sm', WAVE_BAR[w.color] ?? 'bg-accent')} aria-hidden /><h4 className="text-xs font-semibold text-fg">{w.name}</h4><span className="text-[11px] text-fg-3">weeks {w.start_week}–{w.end_week} · {fmtMoneyK(w.cost_k)}</span></div>
            {plan.items.filter((i) => i.wave === w.id).map((i) => (
              <button key={i.id} type="button" onClick={() => onSelect(i.id)} aria-pressed={selected === i.id} className={cn('group flex w-full items-center rounded text-left hover:bg-raised/60', selected === i.id && 'bg-raised')}>
                <span className="w-[210px] shrink-0 truncate px-2 py-1.5 text-xs text-fg-2 group-hover:text-fg" title={i.name}>{i.name}</span>
                <span className="relative h-7 flex-1">
                  {ticks.map((t) => <span key={t} className="absolute inset-y-0 border-l border-line-subtle" style={{ left: pct(t) }} aria-hidden />)}
                  <span className={cn('absolute top-1.5 h-4 rounded-sm opacity-90', WAVE_BAR[w.color] ?? 'bg-accent', i.critical && 'ring-2 ring-fg/60')} style={{ left: pct(i.start_week), width: pct(i.duration_weeks) }} title={`${i.name}: week ${i.start_week} to ${i.end_week}`} />
                </span>
              </button>
            ))}
          </div>
        ))}
        <p className="mt-3 pl-1 text-[11px] text-fg-3"><span className="mr-1 inline-block h-2.5 w-4 rounded-sm bg-accent ring-2 ring-fg/60 align-middle" aria-hidden />Outlined bars are on the critical path. Select an initiative to move it.</p>
      </div>
    </div>
  );
}

export default function ModernizationPage() {
  const t = useChartTheme();
  const scenarios = useGet<{ scenarios: Scenario[] }>('/modernization/scenarios');
  const [scenario, setScenario] = useState('balanced');
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [sel, setSel] = useState<string | null>(null);
  const planM = useMutation<Plan, Error, void>({ mutationFn: () => post<Plan>('/modernization/plan', { scenario, overrides }) });
  const { mutate } = planM;
  useEffect(() => { mutate(); }, [scenario, overrides, mutate]);
  const [plan, setPlan] = useState<Plan | null>(null);
  useEffect(() => { if (planM.data) setPlan(planM.data); }, [planM.data]);

  const item = plan?.items.find((i) => i.id === sel);
  const nameOf = useMemo(() => Object.fromEntries((plan?.items ?? []).map((i) => [i.id, i.name])), [plan]);
  const shift = (id: string, to: number) => setOverrides((o) => ({ ...o, [id]: Math.max(0, to) }));

  const curve = plan && {
    grid: { left: 8, right: 16, top: 28, bottom: 4, containLabel: true },
    legend: { top: 0, left: 0, textStyle: { color: t.fg2, fontSize: 11 }, icon: 'roundRect', itemWidth: 10, itemHeight: 3 },
    tooltip: { trigger: 'axis', backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.fg, fontSize: 12 }, valueFormatter: (v: number) => fmtMoneyK(v) },
    xAxis: { type: 'category', data: plan.value_curve.map((p) => `M${p.month}`), axisLabel: { color: t.fg3, fontSize: 10 }, axisLine: { lineStyle: { color: t.line } } },
    yAxis: { type: 'value', axisLabel: { color: t.fg3, fontSize: 10, formatter: (v: number) => fmtMoneyK(v) }, splitLine: { lineStyle: { color: t.lineSubtle } } },
    series: [
      { name: 'Cumulative cost', type: 'line', smooth: true, symbol: 'none', data: plan.value_curve.map((p) => p.cumulative_cost_k), lineStyle: { width: 2, color: t.high } },
      { name: 'Cumulative value', type: 'line', smooth: true, symbol: 'none', data: plan.value_curve.map((p) => p.cumulative_value_k), lineStyle: { width: 2.5, color: t.healthy }, areaStyle: { color: t.alpha('healthy', 0.1) }, markLine: { symbol: 'none', lineStyle: { color: t.fg3, type: 'dashed' }, label: { color: t.fg2, formatter: 'Break-even', fontSize: 10 }, data: [{ xAxis: `M${plan.totals.break_even_month}` }] } },
    ],
  };
  const tot = plan?.totals;

  return (
    <Page>
      <PageHeader title="Modernization roadmap" description="A dependency-aware plan in three waves: expose APIs, decouple data, then agentify. Switch scenario or move an initiative to see the schedule, critical path and value respond." actions={Object.keys(overrides).length > 0 ? <Button variant="ghost" leading={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => setOverrides({})}>Reset moves</Button> : undefined} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SegmentedControl label="Scenario" value={scenario} onChange={(v) => { setScenario(v); setOverrides({}); }} options={(scenarios.data?.scenarios ?? [{ id: 'balanced', label: 'Balanced', blurb: '' }]).map((s) => ({ value: s.id, label: s.label }))} />
        <p className="text-xs text-fg-3">{plan?.blurb}</p>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {!tot ? Array.from({ length: 5 }).map((_, i) => <SkeletonTile key={i} />) : (<>
          <MetricTile label="Duration" value={`${tot.duration_weeks}`} unit="weeks" />
          <MetricTile label="Investment" value={fmtMoneyK(tot.cost_k)} />
          <MetricTile label="Projected value" value={fmtMoneyK(tot.value_k)} />
          <MetricTile label="Break-even" value={`M${tot.break_even_month}`} />
          <MetricTile label="Assets modernised" value={tot.assets} />
        </>)}
      </div>
      {plan?.adjusted.length ? <p role="status" className="mt-3 rounded border border-high/30 bg-high/10 px-3 py-2 text-xs text-high">{plan.adjusted.length} initiative{plan.adjusted.length > 1 ? 's were' : ' was'} moved later than requested because {plan.adjusted.length > 1 ? 'their' : 'its'} dependencies finish after that date.</p> : null}

      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] items-start gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel title="Roadmap" description="Bars are initiatives, grouped by wave">{plan ? <Gantt plan={plan} selected={sel} onSelect={setSel} /> : <SkeletonBlock className="h-96" />}</Panel>
        <div className="space-y-4">
          <AISummary ai={plan?.ai} loading={!plan} title="AI roadmap summary" thinking={['Scheduling initiatives', 'Resolving the critical path', 'Projecting value']} />
          {item ? (
            <Panel title={item.name} description={`${item.id} · ${titleCase(item.wave)}`} actions={<Button size="sm" variant="ghost" onClick={() => setSel(null)}>Close</Button>}>
              <p className="text-sm text-fg-2">{item.description}</p>
              <div className="mt-3 flex items-center gap-2" role="group" aria-label="Move start week">
                <span className="micro">Start week</span>
                <IconButton label="Start one week earlier" size="sm" onClick={() => shift(item.id, item.start_week - 1)}><Minus className="h-3.5 w-3.5" /></IconButton>
                <span className="num w-8 text-center font-mono text-sm text-fg">{item.start_week}</span>
                <IconButton label="Start one week later" size="sm" onClick={() => shift(item.id, item.start_week + 1)}><Plus className="h-3.5 w-3.5" /></IconButton>
                <span className="text-xs text-fg-3">ends week {item.end_week}</span>
              </div>
              <KeyValueList className="mt-4" items={[
                { label: 'Risk', value: <Badge tone={RISK_TONE[item.risk] ?? 'neutral'} dot>{titleCase(item.risk)}</Badge> },
                { label: 'Cost', value: fmtMoneyK(item.cost_k) }, { label: 'Value', value: fmtMoneyK(item.value_k) }, { label: 'Effort', value: `${item.effort_pd} person-days` },
                { label: 'Depends on', value: item.depends_on.length ? item.depends_on.map((d) => nameOf[d] ?? d).join(', ') : 'Nothing' },
                { label: 'Addresses', value: item.findings.length ? <span className="flex flex-wrap gap-x-2">{item.findings.map((f) => <RefLink key={f} type="finding" id={f} mono />)}</span> : '—' },
                { label: 'Assets', value: <span className="flex flex-wrap gap-x-2 gap-y-0.5">{item.asset_ids.slice(0, 6).map((a) => <RefLink key={a} type="asset" id={a} mono />)}{item.asset_ids.length > 6 && <span className="text-xs text-fg-3">+{item.asset_ids.length - 6}</span>}</span> },
              ]} />
            </Panel>
          ) : (
            <Panel title="Critical path" description="The chain that sets the end date">
              <ol className="space-y-2">{plan?.critical_path.map((id, i) => <li key={id} className="flex items-center gap-2 text-sm"><span className="num flex h-5 w-5 items-center justify-center rounded-full bg-raised font-mono text-[10px] text-fg-2">{i + 1}</span><button type="button" onClick={() => setSel(id)} className="text-left text-fg hover:text-accent">{nameOf[id] ?? id}</button></li>)}</ol>
            </Panel>
          )}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Panel title="Cost and value over time" description="Cumulative, by month">{curve ? <Chart option={curve} height={280} label="Cumulative cost and value by month" /> : <SkeletonBlock className="h-64" />}</Panel>
        <Panel title="Waves" flush>
          <ul className="divide-y divide-line-subtle">
            {plan?.waves.map((w) => (
              <li key={w.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-2"><p className="text-sm font-semibold text-fg">{w.name}</p><Badge tone={RISK_TONE[w.risk] ?? 'neutral'} dot>{titleCase(w.risk)} risk</Badge></div>
                <p className="mt-0.5 text-xs text-fg-3">{w.theme}</p>
                <p className="mt-1.5 text-xs text-fg-2"><span className="num font-mono">{w.items.length}</span> initiatives · <span className="num font-mono">{w.asset_count}</span> assets · weeks {w.start_week}–{w.end_week} · {fmtMoneyK(w.cost_k)} → {fmtMoneyK(w.value_k)}</p>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </Page>
  );
}
