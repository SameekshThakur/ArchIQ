import { ArrowLeft, Download, Layers, Wand2 } from 'lucide-react';
import { Suspense, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import type { AIMeta } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { CodeBlock } from '@/components/ui/Code';
import { SearchInput, SegmentedControl, Tabs } from '@/components/ui/Inputs';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { EmptyState, Panel, SkeletonBlock } from '@/components/ui/Panel';
import { LazyMermaid } from '@/components/viz/LazyChart';
import { cn } from '@/lib/cn';
import { download, titleCase } from '@/lib/format';
import { Link } from 'react-router-dom';

interface Pattern { id: string; name: string; category: string; summary: string; tags: string[]; adoption_count: number; status: string }
interface Detail {
  pattern_id: string; name: string; category: string; title: string; when_to_use: string[]; diagram: string; mermaid: string;
  components: { name: string; role: string; technology: string }[]; nfr_guidance: string[]; anti_patterns: string[]; standards: { id: string; title: string }[]; markdown: string; filename: string; ai: AIMeta;
}

function List({ onOpen }: { onOpen: (id: string) => void }) {
  const [cat, setCat] = useState('all');
  const [q, setQ] = useState('');
  const { data, isLoading } = useGet<{ items: Pattern[]; total: number; categories: string[] }>('/blueprints', { category: cat === 'all' ? undefined : cat, q });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SearchInput value={q} onChange={setQ} placeholder="Search patterns" className="w-64" data-search-input />
        <SegmentedControl label="Category" size="sm" value={cat} onChange={setCat} options={[{ value: 'all', label: 'All' }, ...(data?.categories ?? []).map((c) => ({ value: c, label: titleCase(c) }))]} />
      </div>
      {isLoading ? <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <SkeletonBlock key={i} className="h-36" />)}</div>
        : data && data.items.length ? (
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.items.map((p) => (
              <li key={p.id}>
                <button type="button" onClick={() => onOpen(p.id)} className="hairline h-full w-full rounded-lg border border-line bg-surface p-4 text-left transition-colors hover:border-accent/50 hover:bg-raised/40">
                  <div className="flex items-start justify-between gap-2"><Badge tone="accent">{titleCase(p.category)}</Badge><span className="num font-mono text-[11px] text-fg-3">{p.adoption_count} adopters</span></div>
                  <p className="mt-3 text-sm font-semibold text-fg">{p.name}</p>
                  <p className="mt-1 line-clamp-3 text-xs text-fg-2">{p.summary}</p>
                  <div className="mt-3 flex flex-wrap gap-1">{p.tags.map((t) => <Badge key={t} mono>{t}</Badge>)}</div>
                </button>
              </li>
            ))}
          </ul>
        ) : <EmptyState icon={<Layers className="h-4 w-4" />} title="No patterns match" description="Try a different category or clear the search." />}
    </>
  );
}

function PatternView({ id }: { id: string }) {
  const { data, isLoading } = useGet<Detail>(`/blueprints/${id}`);
  const [tab, setTab] = useState('overview');
  if (isLoading || !data) return <div className="space-y-4"><SkeletonBlock className="h-24" /><SkeletonBlock className="h-72" /></div>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="text-lg font-semibold text-fg">{data.title}</h2><p className="mt-0.5 text-xs text-fg-3">{data.pattern_id} · {titleCase(data.category)}</p></div>
        <div className="flex gap-2">
          <Button leading={<Download className="h-4 w-4" />} onClick={() => download(`${data.filename}.md`, data.markdown, 'text/markdown')}>Markdown</Button>
          <a href={`/api/v1/blueprints/${id}/download`} className="accent-bg inline-flex h-8 items-center gap-2 rounded px-3 text-sm font-medium text-accent-fg hover:brightness-110"><Download className="h-4 w-4" aria-hidden />Starter bundle (.zip)</a>
        </div>
      </div>
      <AISummary ai={data.ai} title="When this pattern fits" />
      <Tabs value={tab} onValueChange={setTab} items={[
        { value: 'overview', label: 'Overview', content: (
          <div className="space-y-4">
            <Panel title="Reference diagram"><div className="overflow-x-auto"><Suspense fallback={<SkeletonBlock className="h-64" />}><LazyMermaid code={data.mermaid} label={`${data.name} reference diagram`} className="mx-auto min-w-[560px] max-w-[820px]" /></Suspense></div></Panel>
            <div className="grid items-start gap-4 lg:grid-cols-2">
              <Panel title="Use it when"><ul className="space-y-1.5 text-sm text-fg-2">{data.when_to_use.map((w) => <li key={w} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-healthy" aria-hidden />{w}</li>)}</ul></Panel>
              <Panel title="Avoid these anti-patterns"><ul className="space-y-1.5 text-sm text-fg-2">{data.anti_patterns.map((w) => <li key={w} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-critical" aria-hidden />{w}</li>)}</ul></Panel>
              <Panel title="Components" flush><ul className="divide-y divide-line-subtle">{data.components.map((c) => <li key={c.name} className="px-4 py-2.5"><p className="text-sm font-medium text-fg">{c.name}</p><p className="text-xs text-fg-3">{c.role}</p><p className="mt-1 font-mono text-[11px] text-fg-2">{c.technology}</p></li>)}</ul></Panel>
              <div className="space-y-4">
                <Panel title="NFR guidance"><ul className="space-y-1.5 text-sm text-fg-2">{data.nfr_guidance.map((w) => <li key={w} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" aria-hidden />{w}</li>)}</ul></Panel>
                <Panel title="Related standards"><ul className="space-y-1.5 text-sm">{data.standards.map((s) => <li key={s.id}><Link to={`/standards?id=${s.id}`} className="text-accent hover:underline"><span className="font-mono text-xs">{s.id}</span> · {s.title}</Link></li>)}</ul></Panel>
              </div>
            </div>
          </div>) },
        { value: 'source', label: 'Markdown', content: <CodeBlock code={data.markdown} language="markdown" filename={`${data.filename}.md`} maxHeight={560} /> },
        { value: 'mermaid', label: 'Diagram source', content: <CodeBlock code={data.mermaid} language="mermaid" filename={`${data.filename}.mmd`} maxHeight={560} /> },
      ]} />
    </div>
  );
}

export default function BlueprintsPage() {
  const [params, setParams] = useSearchParams();
  const id = params.get('id');
  return (
    <Page>
      <PageHeader title="Blueprints" description="Approved reference architectures with diagrams, NFR guidance, anti-patterns and a starter bundle your teams can pick up and run with." actions={<>{id && <Button variant="ghost" leading={<ArrowLeft className="h-4 w-4" />} onClick={() => setParams({})}>All patterns</Button>}<Link to="/studio" className="accent-bg inline-flex h-8 items-center gap-2 rounded px-3 text-sm font-medium text-accent-fg hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"><Wand2 className="h-4 w-4" aria-hidden />Customise in the Studio</Link></>} />
      <div className={cn(id && 'max-w-[1100px]')}>{id ? <PatternView id={id} /> : <List onOpen={(v) => setParams({ id: v })} />}</div>
    </Page>
  );
}
