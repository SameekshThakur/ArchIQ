import { Check, Copy, Download } from 'lucide-react';
import { useMemo, useState } from 'react';
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import hcl from 'react-syntax-highlighter/dist/esm/languages/prism/hcl';
import yaml from 'react-syntax-highlighter/dist/esm/languages/prism/yaml';
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import java from 'react-syntax-highlighter/dist/esm/languages/prism/java';
import markdown from 'react-syntax-highlighter/dist/esm/languages/prism/markdown';
import docker from 'react-syntax-highlighter/dist/esm/languages/prism/docker';
import { cn } from '@/lib/cn';
import { IconButton } from './Button';

SyntaxHighlighter.registerLanguage('hcl', hcl);
SyntaxHighlighter.registerLanguage('terraform', hcl);
SyntaxHighlighter.registerLanguage('bicep', hcl);
SyntaxHighlighter.registerLanguage('yaml', yaml);
SyntaxHighlighter.registerLanguage('json', json);
SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('typescript', typescript);
SyntaxHighlighter.registerLanguage('bash', bash);
SyntaxHighlighter.registerLanguage('java', java);
SyntaxHighlighter.registerLanguage('markdown', markdown);
SyntaxHighlighter.registerLanguage('dockerfile', docker);

/** Token theme driven by CSS variables so it follows the active theme. */
const theme: Record<string, React.CSSProperties> = {
  'code[class*="language-"]': { color: 'rgb(var(--fg))', background: 'none', fontFamily: 'inherit', fontSize: 'inherit' },
  'pre[class*="language-"]': { color: 'rgb(var(--fg))', background: 'none', margin: 0, padding: 0, overflow: 'visible' },
  comment: { color: 'rgb(var(--fg-3))', fontStyle: 'italic' },
  prolog: { color: 'rgb(var(--fg-3))' },
  punctuation: { color: 'rgb(var(--fg-2))' },
  property: { color: 'rgb(var(--low))' },
  tag: { color: 'rgb(var(--critical))' },
  boolean: { color: 'rgb(var(--high))' },
  number: { color: 'rgb(var(--high))' },
  constant: { color: 'rgb(var(--high))' },
  string: { color: 'rgb(var(--healthy))' },
  'attr-value': { color: 'rgb(var(--healthy))' },
  selector: { color: 'rgb(var(--healthy))' },
  operator: { color: 'rgb(var(--fg-2))' },
  keyword: { color: 'rgb(var(--accent-2))' },
  function: { color: 'rgb(var(--accent))' },
  'class-name': { color: 'rgb(var(--medium))' },
  'attr-name': { color: 'rgb(var(--medium))' },
  variable: { color: 'rgb(var(--fg))' },
  builtin: { color: 'rgb(var(--accent))' },
  important: { color: 'rgb(var(--critical))', fontWeight: 'bold' },
};

export function CodeBlock({
  code,
  language = 'text',
  filename,
  maxHeight,
  lineNumbers = true,
  onDownload,
  className,
}: {
  code: string;
  language?: string;
  filename?: string;
  maxHeight?: number | string;
  lineNumbers?: boolean;
  onDownload?: () => void;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <div className={cn('flex min-h-0 flex-col overflow-hidden rounded-lg border border-line bg-bg', className)}>
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-line-subtle bg-surface px-3">
        <span className="truncate font-mono text-xs text-fg-2">{filename ?? language}</span>
        <div className="flex items-center gap-0.5">
          {onDownload && (
            <IconButton label="Download file" size="sm" onClick={onDownload}>
              <Download className="h-3.5 w-3.5" />
            </IconButton>
          )}
          <IconButton label={copied ? 'Copied' : 'Copy to clipboard'} size="sm" onClick={copy}>
            {copied ? <Check className="h-3.5 w-3.5 text-healthy" /> : <Copy className="h-3.5 w-3.5" />}
          </IconButton>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3 font-mono text-xs leading-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent" style={{ maxHeight }} tabIndex={0} role="region" aria-label={`${filename ?? language} contents`}>
        <SyntaxHighlighter
          language={language}
          style={theme}
          showLineNumbers={lineNumbers}
          lineNumberStyle={{ minWidth: '2.6em', paddingRight: '1.2em', color: 'rgb(var(--fg-3) / 0.6)', userSelect: 'none', textAlign: 'right' }}
          codeTagProps={{ style: { fontFamily: 'inherit' } }}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}

/* ---------- Diff (side by side) ---------- */
type DiffRow = { left?: string; right?: string; kind: 'same' | 'del' | 'add' | 'mod' };

function diffLines(a: string[], b: string[]): DiffRow[] {
  // LCS based line diff, adequate for config-sized inputs
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) out.push({ left: a[i++], right: b[j++], kind: 'same' });
    else if (dp[i + 1][j] >= dp[i][j + 1]) out.push({ left: a[i++], kind: 'del' });
    else out.push({ right: b[j++], kind: 'add' });
  }
  while (i < n) out.push({ left: a[i++], kind: 'del' });
  while (j < m) out.push({ right: b[j++], kind: 'add' });
  // pair adjacent del/add into modifications
  const merged: DiffRow[] = [];
  for (let k = 0; k < out.length; k++) {
    const cur = out[k];
    const nxt = out[k + 1];
    if (cur.kind === 'del' && nxt?.kind === 'add') {
      merged.push({ left: cur.left, right: nxt.right, kind: 'mod' });
      k++;
    } else merged.push(cur);
  }
  return merged;
}

export function Diff({
  left,
  right,
  leftTitle = 'Approved',
  rightTitle = 'Deployed',
  className,
}: {
  left: string;
  right: string;
  leftTitle?: string;
  rightTitle?: string;
  className?: string;
}) {
  const rows = useMemo(() => diffLines(left.split('\n'), right.split('\n')), [left, right]);
  let ln = 0;
  let rn = 0;
  return (
    <div className={cn('overflow-hidden rounded-lg border border-line bg-bg', className)}>
      <div className="grid grid-cols-2 border-b border-line bg-surface">
        <div className="micro border-r border-line px-3 py-2">{leftTitle}</div>
        <div className="micro px-3 py-2">{rightTitle}</div>
      </div>
      <div className="max-h-[420px] overflow-auto font-mono text-xs leading-5">
        {rows.map((r, idx) => {
          const l = r.left !== undefined ? ++ln : undefined;
          const rr = r.right !== undefined ? ++rn : undefined;
          const lBad = r.kind === 'del' || r.kind === 'mod';
          const rBad = r.kind === 'add' || r.kind === 'mod';
          return (
            <div key={idx} className="grid grid-cols-2">
              <div className={cn('flex min-w-0 overflow-x-auto border-r border-line-subtle', lBad && 'bg-critical/10')}>
                <span className="num w-9 shrink-0 select-none pr-2 text-right text-fg-3/70">{l}</span>
                <span className={cn('w-3 shrink-0 select-none', lBad && 'text-critical')}>{lBad ? '−' : ''}</span>
                <pre className="min-w-0 flex-1 whitespace-pre pr-3">{r.left ?? ' '}</pre>
              </div>
              <div className={cn('flex min-w-0 overflow-x-auto', rBad && 'bg-healthy/10')}>
                <span className="num w-9 shrink-0 select-none pr-2 text-right text-fg-3/70">{rr}</span>
                <span className={cn('w-3 shrink-0 select-none', rBad && 'text-healthy')}>{rBad ? '+' : ''}</span>
                <pre className="min-w-0 flex-1 whitespace-pre pr-3">{r.right ?? ' '}</pre>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
