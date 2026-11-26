import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, get } from '@/api/client';

export interface FieldSpec { key: string; label: string; kind: 'text' | 'url' | 'secret' | 'textarea'; required: boolean; placeholder: string; help: string; default: string }
export interface Metric { label: string; value: number | string }
export interface Effect { label: string; detail: string; to: string | null }
export interface SyncSummary { id: number; at: string; mode: 'live' | 'demo'; ok: boolean; error: string | null; headline: string; metrics: Metric[]; duration_ms: number }
export interface SyncRun extends SyncSummary {
  effects: Effect[];
  records: Record<string, unknown>[];
  record_count?: number;
  standards?: { score: number; checked: number; failed: number; top: { standard_id: string; title: string; severity: string; count: number }[] };
  work?: { app_id: string; app: string; open: number; done: number; keys: string[] }[];
  import_id?: number;
  doc_ids: string[];
}
export type Status = 'not_connected' | 'configured' | 'connected' | 'demo' | 'error';
export interface Connection {
  id: string; name: string; vendor: string; category: 'cmdb' | 'work' | 'cloud' | 'code' | 'docs'; description: string; provides: string[]; fields: FieldSpec[]; setup: string[];
  configured: boolean; mode: 'live' | 'demo'; status: Status; config: Record<string, string>; secrets_set: Record<string, boolean>; secret_refs: Record<string, string>;
  last_test: { ok: boolean; detail: string; at: string } | null; last_sync: SyncSummary | null; syncing: boolean;
}
export interface LiveDrift { compared: number; drifted: number; deployed_total: number; approved_total: number; at: string; mode: 'live' | 'demo'; items: { name: string; type: string; changes: { attribute: string; approved: unknown; deployed: unknown }[] }[] }
export interface Overview { items: Connection[]; drift: LiveDrift | null; summary: { total: number; connected: number; errors: number } }

export const KEY = ['connections'] as const;

export function useConnections() {
  return useQuery<Overview>({ queryKey: KEY, queryFn: () => get<Overview>('/connections') });
}

export function useConnection(id: string | null) {
  return useQuery<{ connection: Connection; sync: SyncRun | null }>({
    queryKey: [...KEY, id],
    queryFn: () => get(`/connections/${id}`),
    enabled: !!id,
  });
}

export function useConnectionActions() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: KEY });
  return {
    save: async (id: string, body: { mode: 'live' | 'demo'; config: Record<string, string>; secrets: Record<string, string | null> }) => {
      const r = await api<Connection>(`/connections/${id}`, { method: 'PUT', body });
      await refresh();
      return r;
    },
    test: async (id: string) => {
      const r = await api<{ ok: boolean; detail: string }>(`/connections/${id}/test`, { method: 'POST', body: {} });
      await refresh();
      return r;
    },
    sync: async (id: string) => {
      const r = await api<SyncRun>(`/connections/${id}/sync`, { method: 'POST', body: {} });
      // a sync can add documents, imports and drift, so every page's data may have changed
      await qc.invalidateQueries();
      return r;
    },
    remove: async (id: string) => {
      await api(`/connections/${id}`, { method: 'DELETE' });
      await qc.invalidateQueries();
    },
  };
}
