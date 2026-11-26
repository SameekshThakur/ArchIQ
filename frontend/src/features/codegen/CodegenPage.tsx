import { useMutation } from '@tanstack/react-query';
import { CheckCircle2, Download, FileCode2, FileText, Wand2, XCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { post, useGet } from '@/api/hooks';
import type { AIMeta } from '@/api/types';
import { AISummary } from '@/components/ai/AIPanel';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { CodeBlock } from '@/components/ui/Code';
import { Field, Select, Switch, TextInput } from '@/components/ui/Inputs';
import { Page, PageHeader } from '@/components/ui/PageHeader';
import { Panel, SkeletonBlock } from '@/components/ui/Panel';
import { cn } from '@/lib/cn';
import { download } from '@/lib/format';

interface GenFile { path: string; language: string; content: string; lines: number }
interface Gen { id: string; name: string; source: string; files: GenFile[]; checklist: { label: string; status: 'pass' | 'fail'; detail: string }[]; passed: number; total: number; ai: AIMeta }

const DOMAINS = ['Customer & Distribution', 'Claims', 'Policy Admin', 'Underwriting', 'Billing & Finance', 'Data & Analytics', 'Integration & Platform'];

export default function CodegenPage() {
  const tpl = useGet<{ outputs: { id: string; label: string }[]; regions: string[] }>('/codegen/templates');
  const [form, setForm] = useState({ source: 'Customer API', name: 'customer-api', resource: 'customer', region: 'westeurope', owner: 'Platform Engineering', domain: 'Customer & Distribution', include_openai: false });
  const [outputs, setOutputs] = useState<string[]>(['terraform', 'openapi', 'fastapi', 'dockerfile', 'ci']);
  const [file, setFile] = useState<string | null>(null);
  const gen = useMutation<Gen, Error, void>({ mutationFn: () => post<Gen>('/codegen/generate', { ...form, outputs }), onSuccess: (g) => setFile((cur) => (cur && g.files.some((f) => f.path === cur) ? cur : g.files[0]?.path ?? null)) });
  const { mutate } = gen;
  useEffect(() => { mutate(); }, [mutate]);

  const g = gen.data;
  const active = g?.files.find((f) => f.path === file) ?? g?.files[0];
  const valid = /^[a-z][a-z0-9-]{1,59}$/.test(form.name) && /^[a-z][a-z0-9_-]{1,39}$/.test(form.resource) && outputs.length > 0;
  const toggle = (id: string) => setOutputs((o) => (o.includes(id) ? o.filter((x) => x !== id) : [...o, id]));

  return (
    <Page>
      <PageHeader title="Architecture to code" description="Turn an approved target architecture into deployable starting points: private-by-default infrastructure, an API contract and a service skeleton that already satisfies your standards." />
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Panel title="Generate" className="lg:sticky lg:top-4">
          <div className="space-y-3.5">
            <Field label="Source architecture"><TextInput value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} aria-label="Source architecture" /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Service name" hint={/^[a-z][a-z0-9-]{1,59}$/.test(form.name) ? undefined : 'lowercase, digits, dashes'}><TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value.toLowerCase() })} aria-label="Service name" aria-invalid={!/^[a-z][a-z0-9-]{1,59}$/.test(form.name)} /></Field>
              <Field label="Resource"><TextInput value={form.resource} onChange={(e) => setForm({ ...form, resource: e.target.value.toLowerCase() })} aria-label="API resource" /></Field>
            </div>
            <Field label="Domain"><Select value={form.domain} onValueChange={(v) => setForm({ ...form, domain: v })} label="Domain" options={DOMAINS.map((d) => ({ value: d, label: d }))} /></Field>
            <div className="grid gap-3.5">
              <Field label="Region"><Select value={form.region} onValueChange={(v) => setForm({ ...form, region: v })} label="Region" options={(tpl.data?.regions ?? [form.region]).map((r) => ({ value: r, label: r }))} /></Field>
              <Field label="Owner"><TextInput value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} aria-label="Owner" /></Field>
            </div>
            <Field label="Outputs">
              <ul className="space-y-1">
                {(tpl.data?.outputs ?? []).map((o) => (
                  <li key={o.id}><label className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm text-fg-2 hover:bg-raised"><input type="checkbox" checked={outputs.includes(o.id)} onChange={() => toggle(o.id)} className="h-3.5 w-3.5 accent-[rgb(var(--accent))]" />{o.label}</label></li>
                ))}
              </ul>
            </Field>
            <div className="flex items-center gap-2.5"><Switch checked={form.include_openai} onCheckedChange={(v) => setForm({ ...form, include_openai: v })} label="Include Azure OpenAI" /><span className="text-sm text-fg-2">Include Azure OpenAI behind a private endpoint</span></div>
            <Button variant="primary" className="w-full" loading={gen.isPending} disabled={!valid} leading={<Wand2 className="h-4 w-4" />} onClick={() => mutate()}>Generate code</Button>
            {gen.isError && <p role="alert" className="text-xs text-critical">{gen.error.message}</p>}
          </div>
        </Panel>

        <div className="min-w-0 space-y-4">
          <AISummary ai={g?.ai} loading={gen.isPending && !g} title="AI summary" thinking={['Rendering templates', 'Applying standards', 'Validating output']} />
          {g ? (
            <>
              <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 xl:grid-cols-[240px_minmax(0,1fr)]">
                <Panel title={`${g.files.length} files`} description={g.name} flush actions={<a href={`/api/v1/codegen/${g.id}/download`} className="inline-flex h-7 items-center gap-1.5 rounded border border-line bg-raised px-2.5 text-xs font-medium text-fg hover:bg-overlay"><Download className="h-3.5 w-3.5" aria-hidden />.zip</a>}>
                  <ul className="max-h-[560px] overflow-y-auto py-1" aria-label="Generated files">
                    {g.files.map((f) => (
                      <li key={f.path}>
                        <button type="button" onClick={() => setFile(f.path)} aria-current={f.path === active?.path} className={cn('flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-raised', f.path === active?.path && 'bg-raised text-fg')}>
                          {f.language === 'markdown' ? <FileText className="h-3.5 w-3.5 shrink-0 text-fg-3" aria-hidden /> : <FileCode2 className="h-3.5 w-3.5 shrink-0 text-fg-3" aria-hidden />}
                          <span className="min-w-0 flex-1 truncate font-mono text-fg-2" title={f.path}>{f.path}</span>
                          <span className="num font-mono text-[10px] text-fg-3">{f.lines}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </Panel>
                {active && <CodeBlock code={active.content} language={active.language} filename={active.path} maxHeight={560} onDownload={() => download(active.path.split('/').pop() ?? 'file.txt', active.content)} />}
              </div>
              <Panel title="Deployability checks" description={`${g.passed} of ${g.total} passed`} actions={<Badge tone={g.passed === g.total ? 'healthy' : 'high'} dot>{g.passed === g.total ? 'All passing' : 'Needs attention'}</Badge>}>
                <ul className="grid gap-x-6 gap-y-2 md:grid-cols-2">
                  {g.checklist.map((c) => (
                    <li key={c.label} className="flex items-start gap-2 text-xs">
                      {c.status === 'pass' ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-healthy" aria-label="passed" /> : <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-critical" aria-label="failed" />}
                      <span><span className="text-fg">{c.label}</span><span className="block text-fg-3">{c.detail}</span></span>
                    </li>
                  ))}
                </ul>
              </Panel>
            </>
          ) : <SkeletonBlock className="h-96" />}
        </div>
      </div>
    </Page>
  );
}
