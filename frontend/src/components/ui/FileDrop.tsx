import { FileText, Loader2, UploadCloud, X } from 'lucide-react';
import { useCallback, useId, useRef, useState } from 'react';
import { extractFile, type Extracted } from '@/api/client';
import { useGet } from '@/api/hooks';
import { cn } from '@/lib/cn';

export const ACCEPT = '.txt,.md,.markdown,.csv,.tsv,.json,.yaml,.yml,.tf,.tfvars,.bicep,.docx,.pdf,.xlsx,.html,.htm,.log,.xml,.rst,.png,.jpg,.jpeg,.tif,.tiff,.bmp';
export const DESIGN_ACCEPT = '.json,.yaml,.yml,.tf,.tfvars,.bicep,.md,.txt,.docx,.pdf';
export const MAX_MB = 8;

export interface DroppedFile { file: File; extracted: Extracted }

/** Client-side checks that mirror the server limits, so the user gets feedback without a round trip. */
export function validateFile(file: File, accept = ACCEPT): string | null {
  const ext = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
  if (!accept.split(',').includes(ext)) return `${file.name}: ${ext} files are not supported`;
  if (file.size === 0) return `${file.name} is empty`;
  if (file.size > MAX_MB * 1024 * 1024) return `${file.name} is larger than ${MAX_MB} MB`;
  return null;
}

interface Props {
  onFiles: (files: DroppedFile[]) => void | Promise<void>;
  multiple?: boolean;
  accept?: string;
  label?: string;
  hint?: string;
  compact?: boolean;
  disabled?: boolean;
}

/** Drag-and-drop or browse. Files are sent to the API for text extraction; the caller receives the extracted text. */
export function FileDrop({ onFiles, multiple = false, accept = ACCEPT, label, hint, compact, disabled }: Props) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handle = useCallback(async (list: FileList | File[]) => {
    const files = Array.from(list).slice(0, multiple ? 10 : 1);
    if (!files.length) return;
    setError(null);
    const bad = files.map((f) => validateFile(f, accept)).find(Boolean);
    if (bad) { setError(bad); return; }
    try {
      const out: DroppedFile[] = [];
      for (const f of files) {
        setBusy(f.name);
        out.push({ file: f, extracted: await extractFile(f) });
      }
      setBusy(null);
      await onFiles(out);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
      if (input.current) input.current.value = '';
    }
  }, [accept, multiple, onFiles]);

  return (
    <div>
      <label
        htmlFor={id}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) void handle(e.dataTransfer.files); }}
        className={cn(
          'flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-line-strong bg-bg px-4 text-sm transition-colors focus-within:ring-2 focus-within:ring-accent/50 hover:border-accent/60',
          compact ? 'py-2.5' : 'flex-col justify-center py-6 text-center',
          over && 'border-accent bg-accent/5',
          (disabled || busy) && 'pointer-events-none opacity-60',
        )}
      >
        {busy ? <Loader2 className="h-5 w-5 animate-spin text-accent" aria-hidden /> : <UploadCloud className="h-5 w-5 shrink-0 text-accent" aria-hidden />}
        <span className={cn('min-w-0', !compact && 'space-y-0.5')}>
          <span className="block font-medium text-fg">{busy ? `Reading ${busy}…` : (label ?? (multiple ? 'Drop files here or browse' : 'Drop a file here or browse'))}</span>
          <span className="block text-xs text-fg-3">{hint ?? `Word, PDF (scans too, if OCR is installed), Excel, CSV, Markdown, JSON, YAML, Terraform or Bicep · up to ${MAX_MB} MB`}</span>
        </span>
        <input id={id} ref={input} type="file" accept={accept} multiple={multiple} className="sr-only" disabled={disabled || !!busy} onChange={(e) => e.target.files && void handle(e.target.files)} />
      </label>
      {error && <p role="alert" className="mt-1.5 flex items-center gap-1.5 text-xs text-critical"><X className="h-3.5 w-3.5" aria-hidden />{error}</p>}
    </div>
  );
}

export interface SampleDef { file: string; label: string; note: string }

const SAMPLE_URL = (file: string) => `/api/v1/files/samples/${encodeURIComponent(file)}`;

/** One-click demo inputs served by the API (so they work with any way of hosting the web app). Each goes through the same path as a real upload. */
export function SampleFiles({ samples, onFiles, collapsible }: { samples: SampleDef[]; onFiles: (files: DroppedFile[]) => void | Promise<void>; collapsible?: boolean }) {
  const available = useGet<{ items: { name: string }[] }>('/files/samples', undefined, { staleTime: 60_000 });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // only offer samples the server actually has; if the folder is missing the panel simply does not appear
  const have = new Set(available.data?.items.map((i) => i.name));
  const shown = samples.filter((s) => have.has(s.file));
  // hold the space while the list loads so the form below does not jump when the panel appears
  if (available.isLoading) return <div aria-hidden style={{ minHeight: collapsible ? 40 : 34 + samples.length * 58 }} />;
  if (!shown.length) return null;
  const use = async (s: SampleDef) => {
    setBusy(s.file);
    setError(null);
    try {
      const res = await fetch(SAMPLE_URL(s.file));
      if (!res.ok) throw new Error(`Sample ${s.file} is not available`);
      const file = new File([await res.blob()], s.file);
      await onFiles([{ file, extracted: await extractFile(file) }]);
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(null); }
  };
  const body = (
    <>
      <ul className="divide-y divide-line-subtle">
        {shown.map((s) => (
          <li key={s.file} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-2">
            <FileText className="h-4 w-4 shrink-0 text-fg-3" aria-hidden />
            <div className="min-w-0 flex-1 basis-44"><p className="text-sm text-fg">{s.label}</p><p className="text-xs text-fg-3">{s.note}</p></div>
            <div className="ml-auto flex shrink-0 items-center gap-2">
              <a href={SAMPLE_URL(s.file)} download={s.file} className="rounded px-1.5 py-1 text-xs text-fg-3 hover:text-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Download</a>
              <button type="button" disabled={!!busy} onClick={() => void use(s)} className="inline-flex min-h-6 items-center gap-1 rounded-md border border-line px-2 py-1 text-xs font-medium text-fg hover:bg-raised disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
                {busy === s.file && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}Use reference file
              </button>
            </div>
          </li>))}
      </ul>
      {error && <p role="alert" className="px-3 pb-2 text-xs text-critical">{error}</p>}
    </>
  );
  if (collapsible) {
    return (
      <details className="group rounded-lg border border-line bg-surface">
        <summary className="flex h-10 cursor-pointer list-none items-center justify-between px-3 text-xs font-medium uppercase tracking-wide text-fg-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden">
          <span>Reference files ({shown.length})</span><span className="normal-case tracking-normal text-fg-3 group-open:hidden">Show</span><span className="hidden normal-case tracking-normal text-fg-3 group-open:inline">Hide</span>
        </summary>
        <div className="border-t border-line-subtle">{body}</div>
      </details>
    );
  }
  return (
    <div className="rounded-lg border border-line bg-surface">
      <p className="border-b border-line-subtle px-3 py-2 text-xs font-medium uppercase tracking-wide text-fg-3">Reference files</p>
      {body}
    </div>
  );
}
