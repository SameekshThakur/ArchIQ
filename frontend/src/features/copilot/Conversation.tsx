import { motion } from 'framer-motion';
import { ArrowUp, ChevronRight, Loader2, Sparkles, Square, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useGet } from '@/api/hooks';
import { useOpenRef } from '@/components/Ref';
import { Button, IconButton } from '@/components/ui/Button';
import { EvidenceChip } from '@/components/ui/Timeline';
import { AIFooter } from '@/components/ui/Panel';
import { cn } from '@/lib/cn';
import { useCopilot, type Turn } from '@/store/copilot';
import { ResultCard } from './ResultCard';

function Trace({ turn }: { turn: Turn }) {
  const [open, setOpen] = useState(false);
  const streaming = turn.status === 'streaming';
  const shown = open || streaming;
  if (!turn.trace.length && !streaming) return null;
  return (
    <div className="text-xs">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={shown} className="flex items-center gap-1 text-fg-3 hover:text-fg-2" disabled={streaming}>
        {streaming ? <Loader2 className="h-3 w-3 animate-spin text-accent" aria-hidden /> : <ChevronRight className={cn('h-3 w-3 transition-transform', shown && 'rotate-90')} aria-hidden />}
        {streaming ? 'Working…' : `Reasoned in ${turn.trace.length} steps`}
      </button>
      {shown && (
        <ol className="mt-1.5 space-y-1 border-l border-line pl-3">
          {turn.trace.map((s, i) => (
            <motion.li key={i} initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} className="text-fg-2">
              <span className="text-fg">{s.label}</span>
              {s.detail && <span className="text-fg-3"> · {s.detail}</span>}
            </motion.li>
          ))}
        </ol>
      )}
    </div>
  );
}

function TurnView({ turn, compact, onAsk }: { turn: Turn; compact?: boolean; onAsk: (q: string) => void }) {
  const open = useOpenRef();
  const [showEv, setShowEv] = useState(false);
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-lg rounded-br-sm bg-accent/15 px-3 py-2 text-sm text-fg">{turn.query}</p>
      </div>
      <div className="space-y-3" aria-live="polite" aria-busy={turn.status === 'streaming'}>
        <div className="flex items-start gap-2.5">
          <span className="accent-bg mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-accent-fg"><Sparkles className="h-3.5 w-3.5" aria-hidden /></span>
          <div className="min-w-0 flex-1 space-y-3">
            <Trace turn={turn} />
            {turn.headline && <p className="text-sm font-semibold text-fg">{turn.headline}</p>}
            {turn.text && <p className="text-sm leading-relaxed text-fg-2">{turn.text}{turn.status === 'streaming' && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-accent align-middle" aria-hidden />}</p>}
            {turn.status === 'error' && <p role="alert" className="rounded border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical">{turn.error}</p>}
            {turn.cards.map((c, i) => (
              <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
                <ResultCard card={c} flat={compact} />
              </motion.div>
            ))}
            {turn.ai && (
              <div>
                <AIFooter source={turn.ai.provider === 'azure_openai' ? turn.ai.model ?? 'Azure OpenAI' : undefined} confidence={turn.ai.confidence} evidenceCount={turn.ai.evidence.length} onViewEvidence={() => setShowEv((v) => !v)} />
                {showEv && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {turn.ai.evidence.map((e) => <EvidenceChip key={`${e.kind}:${e.id}`} label={e.label} kind={e.kind} onClick={() => open({ type: e.kind, id: e.id })} />)}
                  </div>
                )}
              </div>
            )}
            {turn.status === 'done' && turn.followups.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {turn.followups.map((f) => (
                  <button key={f} type="button" onClick={() => onAsk(f)} className="rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-fg-2 transition-colors hover:border-accent/50 hover:text-fg">{f}</button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function Conversation({ compact, autoQuery }: { compact?: boolean; autoQuery?: string | null }) {
  const { turns, busy, send, stop, clear } = useCopilot();
  const suggestions = useGet<{ items: string[] }>('/copilot/suggestions');
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const started = useRef<string | null>(null);

  useEffect(() => {
    if (autoQuery && started.current !== autoQuery) {
      started.current = autoQuery;
      void send(autoQuery);
    }
  }, [autoQuery, send]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns]);

  const submit = (q: string) => {
    if (!q.trim()) return;
    setDraft('');
    void send(q);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4" role="log" aria-label="Copilot conversation">
        {turns.length === 0 ? (
          <div className="mx-auto max-w-2xl pt-6">
            <span className="accent-bg flex h-10 w-10 items-center justify-center rounded-lg text-accent-fg"><Sparkles className="h-5 w-5" aria-hidden /></span>
            <h2 className="mt-4 text-lg font-semibold text-fg">Ask anything about the estate</h2>
            <p className="mt-1 text-sm text-fg-2">Answers are grounded in the knowledge graph, assessments, drift register and documents, and always show the evidence they used.</p>
            <ul className="mt-5 grid gap-2 sm:grid-cols-2">
              {(suggestions.data?.items ?? []).slice(0, compact ? 8 : 12).map((s) => (
                <li key={s}>
                  <button type="button" onClick={() => submit(s)} className="h-full w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-left text-sm text-fg-2 transition-colors hover:border-accent/50 hover:bg-raised hover:text-fg">{s}</button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className={cn('mx-auto space-y-6', compact ? 'max-w-none' : 'max-w-3xl')}>
            {turns.map((t) => <TurnView key={t.id} turn={t} compact={compact} onAsk={submit} />)}
            <div ref={endRef} />
          </div>
        )}
      </div>
      <form
        className="border-t border-line bg-surface/80 p-3"
        onSubmit={(e) => { e.preventDefault(); submit(draft); }}
      >
        <div className={cn('mx-auto flex items-end gap-2', !compact && 'max-w-3xl')}>
          {turns.length > 0 && (
            <IconButton label="Clear conversation" size="sm" onClick={clear} type="button"><Trash2 className="h-4 w-4" /></IconButton>
          )}
          <textarea
            ref={taRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(draft); } }}
            rows={1}
            placeholder="Ask about applications, risks, dependencies, standards…"
            aria-label="Ask the Copilot"
            className="max-h-32 min-h-9 flex-1 resize-none rounded-md border border-line bg-bg px-3 py-2 text-sm text-fg placeholder:text-fg-3 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
            data-search-input
          />
          {busy ? (
            <Button type="button" variant="secondary" onClick={stop} leading={<Square className="h-3 w-3 fill-current" />}>Stop</Button>
          ) : (
            <Button type="submit" variant="primary" disabled={!draft.trim()} aria-label="Send" leading={<ArrowUp className="h-4 w-4" />}>Ask</Button>
          )}
        </div>
      </form>
    </div>
  );
}
