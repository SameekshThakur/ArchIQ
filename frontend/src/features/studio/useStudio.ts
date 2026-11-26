import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { api, get } from '@/api/client';
import { useUI } from '@/store/ui';
import type { Catalog, Design, DesignRow, Selections } from './types';

const key = (n: number) => ['studio', 'design', n] as const;

export function useCatalog() {
  return useQuery<Catalog>({ queryKey: ['studio', 'catalog'], queryFn: () => get<Catalog>('/studio/catalog'), staleTime: 5 * 60_000 });
}

export function useDesigns() {
  return useQuery<{ items: DesignRow[]; total: number }>({ queryKey: ['studio', 'designs'], queryFn: () => get('/studio/designs'), staleTime: 0 });
}

export function useDesignQuery(n: number | null) {
  return useQuery<Design>({ queryKey: key(n ?? 0), queryFn: () => get<Design>(`/studio/designs/${n}`), enabled: n !== null, staleTime: 10_000, retry: false });
}

export interface Patch { title?: string; domain?: string; owner?: string; selections?: Partial<Selections>; nfr?: Record<string, unknown>; linked_apps?: string[] }

/**
 * Every change goes to the server, which recomputes the architecture and the validation and sends the whole design back.
 * The screen only ever shows what the server returned, so what is on screen is what was validated.
 */
export function useDesignActions(n: number) {
  const qc = useQueryClient();
  const toast = useUI((s) => s.toast);
  const [error, setError] = useState<string | null>(null);
  const put = useCallback((d: Design) => { qc.setQueryData(key(n), d); void qc.invalidateQueries({ queryKey: ['studio', 'designs'] }); return d; }, [qc, n]);

  const run = useMutation<Design, Error, () => Promise<Design>>({
    mutationFn: (fn) => fn(),
    onMutate: () => setError(null),
    onSuccess: (d) => { put(d); },
    onError: (e) => setError(e.message),
  });
  const call = useCallback(async (fn: () => Promise<Design>): Promise<Design | null> => {
    try { return await run.mutateAsync(fn); } catch { return null; }
  }, [run]);

  return {
    busy: run.isPending,
    error,
    clearError: () => setError(null),
    patch: (p: Patch) => call(() => api<Design>(`/studio/designs/${n}`, { method: 'PATCH', body: p })),
    suggestNfr: () => call(() => api<Design>(`/studio/designs/${n}/nfr/suggest`, { method: 'POST', body: {} })),
    setOps: (ops: Record<string, unknown>[]) => call(() => api<Design>(`/studio/designs/${n}/ops`, { method: 'PUT', body: { ops } })),
    chooseBlueprint: (blueprint_id: string, reason: string) => call(() => api<Design>(`/studio/designs/${n}/blueprint`, { method: 'PUT', body: { blueprint_id, reason } })),
    reanalyse: (text: string, domain?: string) => call(() => api<Design>(`/studio/designs/${n}/requirements`, { method: 'POST', body: { text, domain: domain || null } })),
    validate: () => call(() => api<Design>(`/studio/designs/${n}/validate`, { method: 'POST', body: {} })),
    decide: (gap_id: string, action: 'accept' | 'modify' | 'risk_accept' | 'reopen', extra: { value?: unknown; note?: string; alternative?: number } = {}) =>
      call(() => api<Design>(`/studio/designs/${n}/decisions`, { method: 'POST', body: { gap_id, action, ...extra } })),
    saveVersion: async (label: string) => { const d = await call(() => api<Design>(`/studio/designs/${n}/versions`, { method: 'POST', body: { label } })); if (d) toast({ title: 'Version saved', description: label || `Version ${d.versions.at(-1)?.n}` }); return d; },
    restoreVersion: async (vn: number) => { const d = await call(() => api<Design>(`/studio/designs/${n}/versions/${vn}/restore`, { method: 'POST', body: {} })); if (d) toast({ title: `Version ${vn} restored` }); return d; },
    submit: (notes: string, submitter: string) => call(() => api<Design>(`/studio/designs/${n}/submit`, { method: 'POST', body: { notes, submitter: submitter || null } })),
  };
}

export async function createDesign(body: { text: string; title?: string; domain?: string; owner?: string }): Promise<Design> {
  return api<Design>('/studio/designs', { method: 'POST', body });
}

export async function deleteDesign(n: number): Promise<void> {
  await api(`/studio/designs/${n}`, { method: 'DELETE' });
}
