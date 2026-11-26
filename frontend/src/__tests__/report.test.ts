import { describe, expect, it } from 'vitest';
import { reportFileName, reportHtml, reportMarkdown } from '@/features/start/report';
import type { Workspace } from '@/features/start/useWorkspace';

const w: Workspace = {
  status: 'ready', mode: 'custom', error: null,
  intent: { id: 'review', label: 'Get a design ready for architecture review', to: '/reviews', text: 'ARB <next> week' },
  domain: { name: 'Billing & Finance', known: true },
  documents: [{ name: 'design.md', chars: 10, role: 'design' }],
  steps: [{ id: 'read', label: 'Reading your files', status: 'done', detail: '1 design' }, { id: 'inventory', label: 'Reconciling inventory', status: 'skipped', detail: 'no inventory export supplied' }],
  result: { headline: '1 design reviewed, overall no go.', verdict: 'no_go', notes: ['A note.'], primary: { label: 'Open', to: '/reviews' }, sections: [{ id: 'standards', title: 'Standards', to: '/standards', metrics: [{ label: 'Failed', value: 8 }], bullets: ['SEC-001: <script>alert(1)</script>'] }] },
};
const day = new Date('2026-11-06T10:00:00Z');

describe('analysis report', () => {
  it('names the file after the domain and date', () => {
    expect(reportFileName(w, 'html', day)).toBe('archiq-billing-finance-analysis-2026-11-06.html');
  });
  it('writes Markdown with the verdict, files, steps and every section', () => {
    const md = reportMarkdown(w, day);
    expect(md).toContain('# ArchIQ analysis: Billing & Finance');
    expect(md).toContain('**Overall readiness: Not ready**');
    expect(md).toContain('| design.md | design |');
    expect(md).toContain('**Reconciling inventory**: skipped, no inventory export supplied');
    expect(md).toContain('## Standards');
    expect(md).toContain('**Failed:** 8');
  });
  it('writes a self-contained HTML page and escapes anything from the files', () => {
    const html = reportHtml(w, day);
    expect(html.startsWith('<!doctype html>')).toBe(true);
    expect(html).toContain('Not ready');
    expect(html).not.toContain('<script>alert(1)</script>');
    expect(html).toContain('&lt;script&gt;');
    expect(html).toContain('ARB &lt;next&gt; week');
    expect(html).not.toMatch(/<link |src=["']http/);
  });
});
