import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamSSE } from '@/api/client';

function sseResponse(chunks: string[]): Response {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      chunks.forEach((x) => c.enqueue(enc.encode(x)));
      c.close();
    },
  });
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

afterEach(() => vi.restoreAllMocks());

describe('streamSSE', () => {
  it('reassembles events that are split across network chunks', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(sseResponse(['event: token\ndata: {"t":"Hel', 'lo "}\n\nevent: done\ndata: {"ok":true}\n\n']));
    const seen: [string, unknown][] = [];
    await streamSSE('/copilot/stream', { method: 'POST', body: { query: 'x' } }, (e, d) => seen.push([e, d]));
    expect(seen).toEqual([['token', { t: 'Hello ' }], ['done', { ok: true }]]);
  });
  it('rejects when the stream cannot be opened', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('nope', { status: 500 }));
    await expect(streamSSE('/copilot/stream', {}, () => undefined)).rejects.toThrow();
  });
});
