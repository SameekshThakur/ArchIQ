import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FileDrop, SampleFiles, validateFile } from '@/components/ui/FileDrop';

afterEach(() => vi.restoreAllMocks());

describe('validateFile', () => {
  it('accepts supported types and rejects others', () => {
    expect(validateFile(new File(['x'], 'plan.docx'))).toBeNull();
    expect(validateFile(new File(['x'], 'main.tf'))).toBeNull();
    expect(validateFile(new File(['x'], 'run.exe'))).toMatch(/not supported/);
  });
  it('rejects empty files', () => {
    expect(validateFile(new File([], 'a.txt'))).toMatch(/empty/);
  });
});

describe('FileDrop', () => {
  it('sends the file to the extractor and returns the text', async () => {
    const body = { filename: 'a.md', kind: 'md', text: 'Status: Current', chars: 15, size: 15, meta: {} };
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }));
    const onFiles = vi.fn();
    const { container } = render(<FileDrop onFiles={onFiles} />);
    const input = container.querySelector('input[type=file]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['Status: Current'], 'a.md')] } });
    await waitFor(() => expect(onFiles).toHaveBeenCalledTimes(1));
    expect(onFiles.mock.calls[0][0][0].extracted.text).toBe('Status: Current');
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/files/extract');
    expect((init as RequestInit).body).toBeInstanceOf(FormData);
    expect((init as RequestInit).headers).toBeUndefined();
  });

  it('shows the server error and does not call back', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ error: { code: 'unsupported_file', message: 'Scanned PDF has no text' } }), { status: 415 }));
    const onFiles = vi.fn();
    const { container } = render(<FileDrop onFiles={onFiles} />);
    fireEvent.change(container.querySelector('input[type=file]') as HTMLInputElement, { target: { files: [new File(['x'], 'scan.pdf')] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Scanned PDF has no text');
    expect(onFiles).not.toHaveBeenCalled();
  });

  it('blocks unsupported files before any request', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    const { container } = render(<FileDrop onFiles={vi.fn()} />);
    fireEvent.change(container.querySelector('input[type=file]') as HTMLInputElement, { target: { files: [new File(['x'], 'virus.exe')] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('not supported');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('SampleFiles', () => {
  const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);
  const defs = [{ file: 'a.pdf', label: 'Runbook', note: 'n' }, { file: 'missing.docx', label: 'Gone', note: 'n' }];

  it('offers only the samples the server has, and fetches them from the API', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      const u = String(url);
      if (u.endsWith('/files/samples')) return new Response(JSON.stringify({ items: [{ name: 'a.pdf' }], total: 1 }));
      if (u.includes('/files/samples/a.pdf')) return new Response('%PDF-1.4');
      return new Response(JSON.stringify({ filename: 'a.pdf', kind: 'pdf', text: 'hello', chars: 5, size: 8, meta: {} }));
    });
    const onFiles = vi.fn();
    wrap(<SampleFiles samples={defs} onFiles={onFiles} />);
    expect(await screen.findByText('Runbook')).toBeInTheDocument();
    expect(screen.queryByText('Gone')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /use this sample/i }));
    await waitFor(() => expect(onFiles).toHaveBeenCalled());
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/api/v1/files/samples/a.pdf'))).toBe(true);
  });

  it('renders nothing when the server has no samples', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 })));
    const { container } = wrap(<SampleFiles samples={defs} onFiles={vi.fn()} />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
