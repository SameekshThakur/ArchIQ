import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { GraphData, GraphNode } from '@/api/types';
import { buildSvg, exportFileName, type ExportStyle } from '@/components/viz/graphExport';
import { criticalityCounts, domainCounts, filterGraph, searchNodes, UNRATED } from '@/features/graph/filter';
import { FindInView, InlineMenu } from '@/features/graph/GraphToolbar';

const n = (id: string, name: string, over: Partial<GraphNode> = {}): GraphNode => ({ id, name, type: 'App', domain: 'Claims', lifecycle: 'supported', criticality: 'high', degree: 0, ...over });
const data: GraphData = {
  nodes: [
    n('a', 'Claims Intake Portal', { degree: 3 }),
    n('b', 'Claims DB', { type: 'Data', criticality: 'critical', degree: 1 }),
    n('c', 'Policy Core', { domain: 'Policy Admin', criticality: 'critical', degree: 2 }),
    n('d', 'Billing Engine', { domain: 'Billing', criticality: null, degree: 1 }),
    n('o', 'Claims Team', { type: 'Owner', domain: null, criticality: null, degree: 1 }),
    n('x', 'Nobody Owns Me', { type: 'Owner', domain: null, criticality: null, degree: 1 }),
  ],
  edges: [
    { id: '1', source: 'a', target: 'b', rel: 'uses' },
    { id: '2', source: 'a', target: 'c', rel: 'calls' },
    { id: '3', source: 'c', target: 'd', rel: 'calls' },
    { id: '4', source: 'o', target: 'a', rel: 'owns' },
    { id: '5', source: 'x', target: 'd', rel: 'owns' },
  ],
  total_nodes: 6,
  total_edges: 5,
};

describe('filterGraph', () => {
  it('is a no-op without filters', () => {
    expect(filterGraph(data, { domains: [], criticality: [], relations: [] })).toBe(data);
  });
  it('keeps only the chosen domains and drops edges that lose an end', () => {
    const g = filterGraph(data, { domains: ['Claims'], criticality: [], relations: [] });
    expect(g.nodes.map((x) => x.id).sort()).toEqual(['a', 'b', 'o']);
    expect(g.edges.map((e) => e.id).sort()).toEqual(['1', '4']);
  });
  it('filters by criticality and treats missing ratings as "unrated"', () => {
    expect(filterGraph(data, { domains: [], criticality: ['critical'], relations: [] }).nodes.map((x) => x.id).sort()).toEqual(['b', 'c']);
    expect(filterGraph(data, { domains: [], criticality: [UNRATED], relations: [] }).nodes.map((x) => x.id)).toContain('d');
  });
  it('keeps domain-less nodes only while they still connect to something', () => {
    const g = filterGraph(data, { domains: ['Policy Admin'], criticality: [], relations: [] });
    expect(g.nodes.map((x) => x.id)).toEqual(['c']);
    const g2 = filterGraph(data, { domains: ['Billing'], criticality: [], relations: [] });
    expect(g2.nodes.map((x) => x.id).sort()).toEqual(['d', 'x']);
  });
  it('recomputes degree for the view', () => {
    const g = filterGraph(data, { domains: ['Claims'], criticality: [], relations: [] });
    expect(g.nodes.find((x) => x.id === 'a')!.degree).toBe(2);
    expect(g.total_nodes).toBe(3);
  });
  it('counts facets from the unfiltered data', () => {
    expect(domainCounts(data)).toEqual([['Billing', 1], ['Claims', 2], ['Policy Admin', 1]]);
    expect(criticalityCounts(data)).toEqual([['critical', 2], ['high', 1], [UNRATED, 1]]);
  });
});

describe('searchNodes', () => {
  it('ranks prefix matches first, then word starts, then substrings', () => {
    const r = searchNodes(data.nodes, 'claims').map((x) => x.name);
    expect(r[0]).toBe('Claims Intake Portal'); // prefix, higher degree
    expect(r).toContain('Claims DB');
    expect(searchNodes(data.nodes, 'db').map((x) => x.id)).toEqual(['b']);
    expect(searchNodes(data.nodes, '   ')).toEqual([]);
    expect(searchNodes(data.nodes, 'zzz')).toEqual([]);
  });
});

const style: ExportStyle = {
  fg: '#fff', muted: '#999', bg: '#000', line: '#333', accent: '#66f', territory: '#111', territoryLine: '#222',
  colorOf: () => '#66f', legend: [['Application', '#66f', false], ['Data store', '#fb0', true]], title: 'A & B <graph>', subtitle: 'sub', hubCut: 2,
};
describe('buildSvg', () => {
  const nodes = [
    { id: 'a', name: 'Alpha "A"', type: 'App', domain: 'D', degree: 3, x: 0, y: 0 },
    { id: 'b', name: 'Beta', type: 'Data', domain: 'D', degree: 1, x: 100, y: 50 },
    { id: 'c', name: 'Gamma', type: 'App', domain: 'D', degree: 1, x: 40, y: 120 },
    { id: 'z', name: 'Unplaced', type: 'App', degree: 0 },
  ];
  it('writes a valid, escaped, self-contained SVG', () => {
    const svg = buildSvg(nodes, [{ source: 'a', target: 'b' }, { source: 'a', target: 'missing' }], style);
    const doc = new DOMParser().parseFromString(svg, 'image/svg+xml');
    expect(doc.querySelector('parsererror')).toBeNull();
    expect(doc.documentElement.getAttribute('xmlns')).toBe('http://www.w3.org/2000/svg');
    expect(doc.querySelectorAll('path').length).toBe(1); // the dangling link is skipped
    expect(doc.querySelectorAll('circle,rect').length).toBeGreaterThanOrEqual(5);
    expect(svg).toContain('A &amp; B &lt;graph&gt;');
    expect(svg).toContain('Alpha &quot;A&quot;'); // hub label is escaped
    expect(svg).not.toContain('Unplaced');
  });
  it('copes with an empty graph', () => {
    expect(() => new DOMParser().parseFromString(buildSvg([], [], style), 'image/svg+xml')).not.toThrow();
  });
  it('names files by date', () => {
    expect(exportFileName('png', new Date('2026-11-05T10:00:00Z'))).toBe('archiq-knowledge-graph-2026-11-05.png');
  });
});

describe('FindInView', () => {
  it('picks a result with the keyboard', () => {
    const onPick = vi.fn();
    render(<FindInView nodes={data.nodes} onPick={onPick} />);
    const box = screen.getByRole('combobox', { name: /find a node/i });
    fireEvent.change(box, { target: { value: 'claims' } });
    expect(screen.getAllByRole('option').length).toBeGreaterThan(1);
    fireEvent.keyDown(box, { key: 'ArrowDown' });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick.mock.calls[0][0].id).toBe('b');
    expect((box as HTMLInputElement).value).toBe('');
  });
  it('says so when nothing matches', () => {
    render(<FindInView nodes={data.nodes} onPick={() => undefined} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'qqq' } });
    expect(screen.getByText(/nothing in this view matches/i)).toBeTruthy();
  });
});

describe('InlineMenu', () => {
  it('opens, closes on Escape and on an outside press, without a portal', () => {
    const { container } = render(<div><InlineMenu label="Domains" icon={null} count={2}>{() => <p>panel body</p>}</InlineMenu><button>outside</button></div>);
    const btn = screen.getByRole('button', { name: /domains/i });
    expect(btn.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(btn);
    expect(screen.getByText('panel body')).toBeTruthy();
    expect(container.contains(screen.getByText('panel body'))).toBe(true); // stays inside its own subtree so full screen can show it
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByText('panel body')).toBeNull();
    fireEvent.click(btn);
    fireEvent.pointerDown(screen.getByText('outside'));
    expect(screen.queryByText('panel body')).toBeNull();
  });
});
