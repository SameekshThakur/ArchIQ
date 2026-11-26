import { ChevronDown, Sparkles } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { AIMeta } from '@/api/types';
import { EvidenceChip } from '@/components/ui/Timeline';
import { AIFooter, Skeleton } from '@/components/ui/Panel';
import { cn } from '@/lib/cn';
import { useOpenRef } from '@/components/Ref';

/** Animated "AI is thinking" placeholder: cycles through the labels the module would run. */
export function AIThinking({ steps = ['Reading the estate graph', 'Applying rules', 'Drafting the summary'], className }: { steps?: string[]; className?: string }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((x) => Math.min(x + 1, steps.length - 1)), 700);
    return () => clearInterval(t);
  }, [steps.length]);
  return (
    <div className={cn('rounded-lg border border-line bg-surface p-4', className)} role="status" aria-live="polite" aria-label="AI is working">
      <div className="flex items-center gap-2 text-xs text-fg-2">
        <Sparkles className="h-3.5 w-3.5 animate-pulse text-accent" aria-hidden />
        <AnimatePresence mode="wait">
          <motion.span key={i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.18 }}>
            {steps[i]}…
          </motion.span>
        </AnimatePresence>
      </div>
      <div className="mt-3 space-y-2">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-11/12" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    </div>
  );
}

/** AI-generated summary with a collapsible reasoning trace, evidence chips and the confidence footer. */
export function AISummary({
  ai,
  loading,
  title = 'AI summary',
  className,
  thinking,
  children,
}: {
  ai?: AIMeta;
  loading?: boolean;
  title?: string;
  className?: string;
  thinking?: string[];
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [showEv, setShowEv] = useState(false);
  const openRef = useOpenRef();
  if (loading || !ai) return <AIThinking steps={thinking} className={className} />;
  const paragraphs = (ai.summary ?? '').split('\n').filter(Boolean);
  return (
    <section className={cn('hairline rounded-lg border border-line bg-surface', className)} aria-label={title}>
      <div className="flex items-center justify-between gap-2 px-4 pt-3">
        <h2 className="flex items-center gap-1.5 text-xs font-semibold text-fg">
          <Sparkles className="h-3.5 w-3.5 text-accent" aria-hidden />
          {title}
        </h2>
        {ai.reasoning_steps.length > 0 && (
          <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex items-center gap-1 text-[11px] text-fg-3 hover:text-fg-2">
            Reasoning
            <ChevronDown className={cn('h-3 w-3 transition-transform', open && 'rotate-180')} aria-hidden />
          </button>
        )}
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.ol initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="mx-4 mt-2 space-y-1 overflow-hidden border-l border-line pl-3 text-xs text-fg-2">
            {ai.reasoning_steps.map((s, i) => (
              <li key={i}>
                <span className="text-fg">{s.label}</span>
                {s.detail && <span className="text-fg-3"> · {s.detail}</span>}
                <span className="num ml-2 font-mono text-[10px] text-fg-3">{s.duration_ms}ms</span>
              </li>
            ))}
          </motion.ol>
        )}
      </AnimatePresence>
      <div className="prose-ai space-y-2 px-4 py-3 text-sm leading-relaxed text-fg-2">
        {paragraphs.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
        {children}
      </div>
      {showEv && ai.evidence.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-4 pb-2">
          {ai.evidence.map((e) => (
            <EvidenceChip key={`${e.kind}:${e.id}`} label={e.label} kind={e.kind} onClick={() => openRef({ type: e.kind, id: e.id })} />
          ))}
        </div>
      )}
      <div className="border-t border-line-subtle px-4 py-2">
        <AIFooter source={ai.provider === 'azure_openai' ? ai.model ?? 'Azure OpenAI' : undefined} confidence={ai.confidence} evidenceCount={ai.evidence.length} onViewEvidence={() => setShowEv((v) => !v)} />
      </div>
    </section>
  );
}
