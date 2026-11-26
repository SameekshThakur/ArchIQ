import { create } from 'zustand';
import { streamSSE } from '@/api/client';
import type { AIMeta, CopilotCard, TraceStep } from '@/api/types';

export interface Turn {
  id: number;
  query: string;
  status: 'streaming' | 'done' | 'error';
  intent?: string;
  headline?: string;
  trace: TraceStep[];
  text: string;
  cards: CopilotCard[];
  followups: string[];
  ai?: AIMeta;
  error?: string;
}

interface CopilotState {
  turns: Turn[];
  busy: boolean;
  send: (query: string) => Promise<void>;
  stop: () => void;
  clear: () => void;
}

let seq = 1;
let controller: AbortController | null = null;

/** Single shared conversation: the full page and the ⌘J slide-over both render this. */
export const useCopilot = create<CopilotState>((set, get) => {
  const patch = (id: number, fn: (t: Turn) => Partial<Turn>) =>
    set((s) => ({ turns: s.turns.map((t) => (t.id === id ? { ...t, ...fn(t) } : t)) }));

  return {
    turns: [],
    busy: false,
    stop: () => {
      controller?.abort();
      controller = null;
      set((s) => ({ busy: false, turns: s.turns.map((t) => (t.status === 'streaming' ? { ...t, status: 'done' } : t)) }));
    },
    clear: () => {
      get().stop();
      set({ turns: [] });
    },
    send: async (raw) => {
      const query = raw.trim();
      if (!query) return;
      controller?.abort();
      const ctl = new AbortController();
      controller = ctl;
      const id = seq++;
      set((s) => ({
        busy: true,
        turns: [...s.turns.map((t) => (t.status === 'streaming' ? { ...t, status: 'done' as const } : t)), { id, query, status: 'streaming', trace: [], text: '', cards: [], followups: [] }],
      }));
      try {
        await streamSSE('/copilot/stream', { method: 'POST', body: { query }, signal: ctl.signal }, (event, data) => {
          const d = data as Record<string, unknown>;
          if (event === 'start') patch(id, () => ({ intent: d.intent as string, headline: d.headline as string }));
          else if (event === 'trace') patch(id, (t) => ({ trace: [...t.trace, d as unknown as TraceStep] }));
          else if (event === 'token') patch(id, (t) => ({ text: t.text + (d.t as string) }));
          else if (event === 'cards') patch(id, () => ({ cards: (d.cards as CopilotCard[]) ?? [], followups: (d.followups as string[]) ?? [] }));
          else if (event === 'done') patch(id, () => ({ status: 'done', ai: d.ai as AIMeta }));
        });
        patch(id, (t) => (t.status === 'streaming' ? { status: 'done' } : {}));
      } catch (e) {
        if ((e as Error).name !== 'AbortError') patch(id, () => ({ status: 'error', error: (e as Error).message || 'The Copilot could not answer' }));
      } finally {
        if (controller === ctl) {
          controller = null;
          set({ busy: false });
        }
      }
    },
  };
});
