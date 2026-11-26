import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, get } from '@/api/client';

export interface WStep { id: string; label: string; status: 'pending' | 'running' | 'done' | 'skipped' | 'failed'; detail: string; link?: string }
export interface WSection { id: string; title: string; to: string; metrics: { label: string; value: string | number }[]; bullets: string[] }
export interface WResult { headline: string; verdict: 'go' | 'conditional' | 'no_go' | null; sections: WSection[]; notes: string[]; primary: { label: string; to: string } }
export interface Workspace {
  status: 'empty' | 'running' | 'ready' | 'failed';
  mode: 'demo' | 'custom' | null;
  intent: { id: string; label: string; text?: string; to: string } | null;
  domain: { name: string; known: boolean; all?: boolean } | null;
  documents: { name: string; chars: number; role?: string }[];
  sources?: { id: string; name: string; mode: 'live' | 'demo' }[];
  steps: WStep[];
  result: WResult | null;
  error: string | null;
}
export interface WorkspaceOptions { intents: { id: string; label: string; hint: string; to: string }[]; domains: { name: string; assets: number }[]; max_files: number }

export const WORKSPACE_KEY = ['workspace'] as const;

/** The one analysis the app is showing. While it runs, the query polls so the page shows real progress. */
export function useWorkspace() {
  return useQuery<Workspace>({
    queryKey: WORKSPACE_KEY,
    queryFn: () => get<Workspace>('/workspace'),
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 400 : false),
    staleTime: 5_000,
    retry: false,
  });
}

/** After the workspace changes every page's data changes too, so cached answers are dropped. */
export function useWorkspaceActions() {
  const qc = useQueryClient();
  const refresh = async () => { await qc.invalidateQueries(); };
  return {
    loadDemo: async () => { const w = await api<Workspace>('/workspace/demo', { method: 'POST', body: {} }); qc.setQueryData(WORKSPACE_KEY, w); await refresh(); return w; },
    reset: async () => { const w = await api<Workspace>('/workspace', { method: 'DELETE' }); qc.setQueryData(WORKSPACE_KEY, w); await refresh(); return w; },
  };
}
