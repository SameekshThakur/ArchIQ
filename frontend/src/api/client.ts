import type { ZodType } from 'zod';
import { useUI } from '@/store/ui';

const BASE = '/api/v1';

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;
  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

interface Options<T> {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  schema?: ZodType<T>;
  signal?: AbortSignal;
}

function qs(query?: Options<unknown>['query']): string {
  if (!query) return '';
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : '';
}

export async function api<T = unknown>(path: string, opts: Options<T> = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}${qs(opts.query)}`, {
      method: opts.method ?? 'GET',
      headers: opts.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e;
    useUI.getState().setApiDown(true);
    throw new ApiError(0, 'network_error', 'Cannot reach the ArchIQ API');
  }
  if (useUI.getState().apiDown) useUI.getState().setApiDown(false);
  if (!res.ok) {
    let code = 'http_error';
    let message = res.statusText;
    let requestId: string | undefined;
    try {
      const j = await res.json();
      code = j?.error?.code ?? code;
      message = j?.error?.message ?? message;
      requestId = j?.error?.request_id;
    } catch {
      /* non-JSON error body */
    }
    if (res.status >= 502) useUI.getState().setApiDown(true);
    throw new ApiError(res.status, code, message, requestId);
  }
  const json = (await res.json()) as unknown;
  return opts.schema ? opts.schema.parse(json) : (json as T);
}

export const get = <T>(path: string, query?: Options<T>['query'], schema?: ZodType<T>) =>
  api<T>(path, { query, schema });
export const post = <T>(path: string, body?: unknown, schema?: ZodType<T>) =>
  api<T>(path, { method: 'POST', body: body ?? {}, schema });

export interface Extracted { filename: string; kind: string; text: string; chars: number; size: number; meta: Record<string, unknown> }

/** Multipart upload to the text extractor. The browser sets the multipart boundary, so no Content-Type header is sent. */
export async function extractFile(file: File, signal?: AbortSignal): Promise<Extracted> {
  const form = new FormData();
  form.append('file', file, file.name);
  let res: Response;
  try {
    res = await fetch(`${BASE}/files/extract`, { method: 'POST', body: form, signal });
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e;
    throw new ApiError(0, 'network_error', 'Cannot reach the ArchIQ API');
  }
  if (!res.ok) {
    let code = 'http_error';
    let message = res.statusText;
    try {
      const j = await res.json();
      code = j?.error?.code ?? code;
      message = j?.error?.message ?? message;
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as Extracted;
}

/** Minimal SSE-over-fetch reader (EventSource cannot POST). */
export async function streamSSE(
  path: string,
  opts: { method?: 'GET' | 'POST'; body?: unknown; query?: Options<unknown>['query']; signal?: AbortSignal },
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  const res = await fetch(`${BASE}${path}${qs(opts.query)}`, {
    method: opts.method ?? 'GET',
    headers: {
      Accept: 'text/event-stream',
      ...(opts.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, 'stream_error', 'Stream failed');
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split(/\r?\n\r?\n/);
    buf = frames.pop() ?? '';
    for (const frame of frames) {
      let event = 'message';
      const dataLines: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));
      }
      if (!dataLines.length) continue;
      const raw = dataLines.join('\n');
      try {
        onEvent(event, JSON.parse(raw));
      } catch {
        onEvent(event, raw);
      }
    }
  }
}
