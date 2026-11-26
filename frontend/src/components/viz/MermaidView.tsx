import { useEffect, useId, useRef, useState } from 'react';
import { useUI } from '@/store/ui';
import { Skeleton } from '@/components/ui/Panel';
import { CodeBlock } from '@/components/ui/Code';
import { cn } from '@/lib/cn';

/** Renders a Mermaid diagram (lazy-loaded) and falls back to the source if it does not parse. */
export default function MermaidView({ code, className, label = 'Architecture diagram' }: { code: string; className?: string; label?: string }) {
  const theme = useUI((s) => s.theme);
  const id = useId().replace(/:/g, '');
  const ref = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<'loading' | 'ok' | 'error'>('loading');

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    (async () => {
      try {
        const { default: mermaid } = await import('mermaid');
        const css = (n: string) => `rgb(${getComputedStyle(document.documentElement).getPropertyValue(`--${n}`).trim()})`;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: 'base',
          themeVariables: {
            fontFamily: 'Inter, system-ui, sans-serif',
            fontSize: '13px',
            background: 'transparent',
            primaryColor: css('raised'),
            primaryTextColor: css('fg'),
            primaryBorderColor: css('border'),
            lineColor: css('fg-3'),
            secondaryColor: css('surface'),
            tertiaryColor: css('surface'),
            clusterBkg: css('surface'),
            clusterBorder: css('border'),
            edgeLabelBackground: css('surface'),
            nodeTextColor: css('fg'),
          },
          flowchart: { curve: 'basis', htmlLabels: false, padding: 12 },
        });
        const { svg } = await mermaid.render(`m${id}${Date.now()}`, code);
        if (cancelled || !ref.current) return;
        ref.current.innerHTML = svg;
        const el = ref.current.querySelector('svg');
        if (el) {
          el.removeAttribute('height');
          el.style.maxWidth = '100%';
          el.style.height = 'auto';
        }
        setState('ok');
      } catch {
        if (!cancelled) setState('error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, theme, id]);

  if (state === 'error') return <CodeBlock code={code} language="text" filename="diagram.mmd" maxHeight={320} />;
  return (
    <div className={cn('relative min-h-[120px] overflow-auto', className)} role="img" aria-label={label}>
      {state === 'loading' && <Skeleton className="absolute inset-0" />}
      <div ref={ref} className="flex justify-center" />
    </div>
  );
}
