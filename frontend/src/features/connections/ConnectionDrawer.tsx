import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, RefreshCw, Trash2, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Drawer } from '@/components/ui/Overlay';
import { Field, SegmentedControl, TextArea, TextInput } from '@/components/ui/Inputs';
import { useUI } from '@/store/ui';
import { ApiError } from '@/api/client';
import { useConnection, useConnectionActions, type SyncRun } from './api';

function when(at?: string | null) {
  if (!at) return '';
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? at : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function message(e: unknown) {
  return e instanceof ApiError ? e.message : (e as Error).message;
}

/**
 * The setup form for one platform. On the Connections page it can also sync. Inside a new analysis (`onSaved` given) it saves the settings and hands the
 * platform back to the caller, because the analysis reads it itself when it starts.
 */
export function ConnectionDrawer({ id, onClose, onSaved }: { id: string | null; onClose: () => void; onSaved?: (id: string) => void }) {
  const { data } = useConnection(id);
  const c = data?.connection;
  const { save, test, sync, remove } = useConnectionActions();
  const toast = useUI((s) => s.toast);
  const [mode, setMode] = useState<'live' | 'demo'>('live');
  const [values, setValues] = useState<Record<string, string>>({});
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<'' | 'save' | 'test' | 'sync' | 'remove'>('');
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);

  useEffect(() => {
    if (!c) return;
    setMode(c.configured ? c.mode : 'live');
    setValues(Object.fromEntries(c.fields.filter((f) => f.kind !== 'secret').map((f) => [f.key, c.config[f.key] ?? f.default ?? ''])));
    setSecrets({});
    setResult(c.last_test ? { ok: c.last_test.ok, detail: c.last_test.detail } : null);
  }, [c?.id, c?.configured]); // eslint-disable-line react-hooks/exhaustive-deps

  const missing = useMemo(() => {
    if (!c || mode === 'demo') return [];
    return c.fields.filter((f) => f.required && (f.kind === 'secret' ? !(secrets[f.key] || c.secrets_set[f.key]) : !values[f.key]?.trim())).map((f) => f.label);
  }, [c, mode, values, secrets]);

  if (!id) return null;

  const doSave = async () => {
    if (!c) return false;
    setBusy('save');
    try {
      await save(c.id, { mode, config: mode === 'demo' ? (c.configured ? c.config : {}) : values, secrets: mode === 'demo' ? {} : secrets });
      setSecrets({});
      return true;
    } catch (e) {
      toast({ title: 'Could not save', description: message(e), tone: 'error' });
      return false;
    } finally {
      setBusy('');
    }
  };

  const run = async (kind: 'test' | 'sync') => {
    if (!c || !(await doSave())) return;
    setBusy(kind);
    try {
      if (kind === 'test') {
        const r = await test(c.id);
        setResult(r);
      } else {
        const r = await sync(c.id);
        toast(r.ok ? { title: `${c.name} synced`, description: r.headline, tone: 'success' } : { title: 'Sync failed', description: r.error ?? undefined, tone: 'error' });
      }
    } catch (e) {
      toast({ title: kind === 'test' ? 'Test failed' : 'Sync failed', description: message(e), tone: 'error' });
    } finally {
      setBusy('');
    }
  };

  return (
    <Drawer open={!!id} onOpenChange={(o) => !o && onClose()} title={c?.name ?? 'Connection'} subtitle={c ? `${c.vendor} · read-only` : undefined} width={560}>
      {!c ? (
        <p className="text-sm text-fg-3">Loading…</p>
      ) : (
        <div className="space-y-5">
          <SegmentedControl label="Connection mode" value={mode} onChange={setMode} options={[{ value: 'live', label: 'Live platform' }, { value: 'demo', label: 'Not live' }]} />
          {mode === 'demo' ? (
            <p className="rounded-md border border-line bg-raised p-3 text-sm text-fg-2">
              Not live mode makes no external network calls. A sync reads from the local estate snapshot and feeds it through the exact same pipeline as a live sync.
            </p>
          ) : (
            <>
              <div className="space-y-3">
                {c.fields.map((f) => {
                  const fid = `f-${c.id}-${f.key}`;
                  if (f.kind === 'secret') {
                    const ref = c.secret_refs[f.key];
                    return (
                      <Field key={f.key} label={`${f.label}${f.required ? '' : ' (optional)'}`} hint={[f.help, ref ? `Read from ${ref}.` : 'Stored on the server, never shown again. You can also enter env:VARIABLE_NAME.'].filter(Boolean).join(' ')}>
                        <TextInput id={fid} type="password" autoComplete="off" value={secrets[f.key] ?? ''} placeholder={c.secrets_set[f.key] ? 'Saved. Leave empty to keep it.' : f.placeholder}
                          onChange={(e) => setSecrets((s) => ({ ...s, [f.key]: e.target.value }))} />
                      </Field>
                    );
                  }
                  const Input = f.kind === 'textarea' ? TextArea : TextInput;
                  return (
                    <Field key={f.key} label={`${f.label}${f.required ? '' : ' (optional)'}`} hint={f.help || undefined}>
                      <Input id={fid} value={values[f.key] ?? ''} placeholder={f.placeholder} rows={f.kind === 'textarea' ? 2 : undefined}
                        onChange={(e: { target: { value: string } }) => setValues((v) => ({ ...v, [f.key]: e.target.value }))} />
                    </Field>
                  );
                })}
              </div>
              <div className="rounded-md border border-line p-3">
                <p className="micro mb-1.5">What the platform admin needs to set up</p>
                <ul className="list-disc space-y-1 pl-4 text-xs text-fg-2">{c.setup.map((s) => <li key={s}>{s}</li>)}</ul>
              </div>
            </>
          )}

          {result && (
            <p role="status" className={`flex items-start gap-2 rounded-md border p-3 text-sm ${result.ok ? 'border-healthy/40 text-fg' : 'border-critical/40 text-critical'}`}>
              {result.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-healthy" aria-hidden /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />}
              <span>{result.ok ? 'Connection works. ' : 'Connection failed. '}{result.detail}</span>
            </p>
          )}
          {missing.length > 0 && <p className="text-xs text-fg-3">Still needed: {missing.join(', ')}.</p>}

          <div className="flex flex-wrap gap-2">
            {onSaved ? (
              <>
                <Button variant="primary" loading={busy === 'save'} disabled={!!busy || missing.length > 0} onClick={async () => { if (await doSave()) { onSaved(c.id); onClose(); } }}>Save and use in this analysis</Button>
                <Button variant="secondary" loading={busy === 'test'} disabled={!!busy || missing.length > 0} onClick={() => run('test')}>Test connection</Button>
              </>
            ) : (
              <>
                <Button variant="secondary" loading={busy === 'save'} disabled={!!busy} onClick={doSave}>Save</Button>
                <Button variant="secondary" loading={busy === 'test'} disabled={!!busy || missing.length > 0} onClick={() => run('test')}>Test connection</Button>
                <Button variant="primary" loading={busy === 'sync'} disabled={!!busy || missing.length > 0} leading={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => run('sync')}>Save and sync</Button>
              </>
            )}
            {c.configured && (
              <Button variant="outline" className="ml-auto" loading={busy === 'remove'} disabled={!!busy} leading={<Trash2 className="h-3.5 w-3.5" />}
                onClick={async () => { setBusy('remove'); try { await remove(c.id); toast({ title: `${c.name} disconnected`, tone: 'success' }); onClose(); } finally { setBusy(''); } }}>
                Disconnect
              </Button>
            )}
          </div>

          {data?.sync && !onSaved && <SyncResult run={data.sync} />}
        </div>
      )}
    </Drawer>
  );
}

function SyncResult({ run }: { run: SyncRun }) {
  const cols = run.records.length ? Object.keys(run.records[0]).filter((k) => !['url', 'labels', 'components'].includes(k)).slice(0, 4) : [];
  return (
    <section aria-labelledby="sync-result" className="space-y-4 border-t border-line pt-4">
      <div>
        <h3 id="sync-result" className="text-sm font-semibold">Last sync</h3>
        <p className="text-xs text-fg-3">{when(run.at)} · {run.mode === 'demo' ? 'not live' : 'live'} · {(run.duration_ms / 1000).toFixed(1)} s</p>
      </div>
      {!run.ok && <p className="rounded-md border border-critical/40 p-3 text-sm text-critical">{run.error}</p>}
      {run.metrics.length > 0 && (
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {run.metrics.map((m) => (
            <div key={m.label} className="rounded-md border border-line p-2.5"><dt className="text-xs text-fg-3">{m.label}</dt><dd className="num text-lg font-semibold">{m.value}</dd></div>
          ))}
        </dl>
      )}
      {run.effects.length > 0 && (
        <div>
          <p className="micro mb-1.5">What changed in ArchIQ</p>
          <ul className="space-y-1.5 text-sm">
            {run.effects.map((e) => (
              <li key={e.label} className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-healthy" aria-hidden />
                <span><b className="font-medium">{e.label}</b>: {e.detail}{e.to && <> · <Link className="text-accent underline" to={e.to}>Open</Link></>}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {run.standards && run.standards.top.length > 0 && (
        <div>
          <p className="micro mb-1.5">Failing standards</p>
          <ul className="space-y-1 text-sm">
            {run.standards.top.map((s) => (
              <li key={s.standard_id} className="flex items-center gap-2">
                <Badge tone={s.severity === 'critical' ? 'critical' : s.severity === 'high' ? 'high' : s.severity === 'medium' ? 'medium' : 'low'}>{s.severity}</Badge>
                <span className="font-mono text-xs text-fg-3">{s.standard_id}</span><span className="min-w-0 flex-1 truncate">{s.title}</span><span className="num text-xs text-fg-3">{s.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {run.work && run.work.length > 0 && (
        <div>
          <p className="micro mb-1.5">Open work by application</p>
          <ul className="space-y-1 text-sm">
            {run.work.slice(0, 8).map((w) => (
              <li key={w.app_id} className="flex justify-between gap-2"><span>{w.app}</span><span className="text-xs text-fg-3">{w.open} open · {w.done} done</span></li>
            ))}
          </ul>
        </div>
      )}
      {cols.length > 0 && (
        <div className="overflow-x-auto">
          <p className="micro mb-1.5">Records read{run.record_count && run.record_count > run.records.length ? ` (first ${run.records.length} of ${run.record_count})` : ''}</p>
          <table className="w-full text-left text-xs">
            <caption className="sr-only">Sample of the records read in the last sync</caption>
            <thead className="text-fg-3"><tr>{cols.map((k) => <th key={k} className="py-1 pr-3 font-medium">{k.replace(/_/g, ' ')}</th>)}</tr></thead>
            <tbody className="divide-y divide-line-subtle">
              {run.records.slice(0, 10).map((r, i) => (
                <tr key={i}>{cols.map((k) => <td key={k} className="max-w-[180px] truncate py-1 pr-3">{String(r[k] ?? '')}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
