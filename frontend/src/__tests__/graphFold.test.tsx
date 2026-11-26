import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { GraphData, GraphNode } from '@/api/types';
import { bubbleDomain, bubbleId, collapseGraph, isBubble } from '@/features/graph/collapse';
import { filterGraph, relationCounts, relationLabel } from '@/features/graph/filter';
import { NodeTable } from '@/features/graph/NodeTable';

const n = (id: string, name: string, over: Partial<GraphNode> = {}): GraphNode => ({ id, name, type: 'App', domain: 'Claims', lifecycle: 'supported', criticality: 'high', degree: 0, ...over });
const data: GraphData = {
  nodes: [
    n('a', 'Claims Intake Portal', { degree: 3 }),
    n('b', 'Claims DB', { type: 'Data', criticality: 'critical', degree: 2 }),
    n('c', 'Policy Core', { domain: 'Policy Admin', criticality: 'medium', degree: 3 }),
    n('d', 'Billing Engine', { domain: 'Billing', criticality: null, degree: 1 }),
    n('o', 'Claims Team', { type: 'Owner', domain: null, criticality: null, degree: 1 }),
  ],
  edges: [
    { id: '1', source: 'a', target: 'b', rel: 'stores_data_in' },
    { id: '2', source: 'a', target: 'c', rel: 'calls' },
    { id: '3', source: 'b', target: 'c', rel: 'calls' },
    { id: '4', source: 'c', target: 'd', rel: 'calls' },
    { id: '5', source: 'o', target: 'a', rel: 'owns' },
  ],
  total_nodes: 5,
  total_edges: 5,
};

describe('collapseGraph', () => {
  it('is a no-op when nothing is folded or the domain is unknown', () => {
    expect(collapseGraph(data, [])).toBe(data);
    expect(collapseGraph(data, ['Nope'])).toBe(data);
  });
  it('replaces a folded domain with one bubble that remembers its members', () => {
    const g = collapseGraph(data, ['Claims']);
    const bubble = g.nodes.find((x) => x.id === bubbleId('Claims'))!;
    expect(bubble).toMatchObject({ type: 'Domain', name: 'Claims', members: 2, criticality: 'critical' });
    expect(bubble.memberIds?.sort()).toEqual(['a', 'b']);
    expect(g.nodes.map((x) => x.id)).not.toContain('a');
    expect(g.nodes).toHaveLength(4); // c, d, o and the bubble
  });
  it('drops links inside the domain and merges the ones that leave it, counting what they stand for', () => {
    const g = collapseGraph(data, ['Claims']);
    expect(g.edges.find((e) => e.id === 'agg:domain:Claims>c')).toMatchObject({ count: 2, rels: { calls: 2 }, rel: 'calls' });
    expect(g.edges.some((e) => e.source === 'a' || e.target === 'b')).toBe(false); // the a→b link lived inside the bubble
    expect(g.edges.find((e) => e.id === 'agg:o>domain:Claims')).toMatchObject({ count: 1, rel: 'owns' }); // direction kept: owner → bubble
    expect(g.edges.map((e) => e.id).sort()).toEqual(['4', 'agg:domain:Claims>c', 'agg:o>domain:Claims']);
  });
  it('recomputes degrees from the folded links', () => {
    const g = collapseGraph(data, ['Claims']);
    const deg = Object.fromEntries(g.nodes.map((x) => [x.id, x.degree]));
    expect(deg[bubbleId('Claims')]).toBe(2); // → Policy Core, ← Claims Team
    expect(deg.c).toBe(2); // the bubble and Billing
  });
  it('folds several domains and keeps links between two bubbles', () => {
    const g = collapseGraph(data, ['Claims', 'Policy Admin']);
    expect(g.edges.find((e) => e.source === bubbleId('Claims') && e.target === bubbleId('Policy Admin'))?.count).toBe(2);
    expect(g.total_nodes).toBe(g.nodes.length);
  });
  it('recognises bubble ids', () => {
    expect(isBubble(bubbleId('Billing'))).toBe(true);
    expect(isBubble('a')).toBe(false);
    expect(bubbleDomain(bubbleId('Policy Admin'))).toBe('Policy Admin');
  });
});

describe('relationship filter', () => {
  it('keeps only the chosen kinds of link and the nodes still joined by them', () => {
    const g = filterGraph(data, { domains: [], criticality: [], relations: ['calls'] });
    expect(g.edges.map((e) => e.id).sort()).toEqual(['2', '3', '4']);
    expect(g.nodes.map((x) => x.id).sort()).toEqual(['a', 'b', 'c', 'd']); // the owner has no calls left
  });
  it('combines with the domain filter', () => {
    const g = filterGraph(data, { domains: ['Claims'], criticality: [], relations: ['stores_data_in'] });
    expect(g.nodes.map((x) => x.id).sort()).toEqual(['a', 'b']);
  });
  it('counts links per relationship, busiest first, and sums folded links', () => {
    expect(relationCounts(data)[0]).toEqual(['calls', 3]);
    expect(relationCounts(collapseGraph(data, ['Claims'])).find(([r]) => r === 'calls')?.[1]).toBe(3);
  });
  it('writes relationships for people', () => {
    expect(relationLabel('stores_data_in')).toBe('Stores data in');
    expect(relationLabel('hosted_on')).toBe('Hosted on');
  });
});

describe('NodeTable', () => {
  // jsdom has no layout, so the virtualised table would see a zero-height viewport and draw no rows
  beforeAll(() => {
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 600 });
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 900 });
    HTMLElement.prototype.getBoundingClientRect = () => ({ width: 900, height: 600, top: 0, left: 0, right: 900, bottom: 600, x: 0, y: 0, toJSON: () => ({}) });
  });
  const setup = (selectedId: string | null = null) => {
    const h = { onSelect: vi.fn(), onOpen: vi.fn(), onShowInGraph: vi.fn() };
    render(<NodeTable graph={data} selectedId={selectedId} maxHeight={400} {...h} />);
    return h;
  };
  it('lists every node in an accessibly named table', async () => {
    setup();
    await screen.findByText('Billing Engine');
    const table = screen.getByRole('table', { name: 'Graph nodes' });
    expect(within(table).getByText('Claims Intake Portal')).toBeInTheDocument();
    expect(within(table).getByText('Billing Engine')).toBeInTheDocument();
  });
  it('filters rows by name', async () => {
    setup();
    await screen.findByText('Billing Engine');
    fireEvent.change(screen.getByLabelText(/filter the table/i), { target: { value: 'billing' } });
    expect(screen.queryByText('Claims Intake Portal')).not.toBeInTheDocument();
    expect(screen.getByText('Billing Engine')).toBeInTheDocument();
  });
  it('shows the connections of the selected node and lets you jump to the graph', () => {
    const h = setup('a');
    const aside = screen.getByRole('complementary', { name: /connections of the selected node/i });
    expect(within(aside).getByText('Claims DB')).toBeInTheDocument();
    expect(within(aside).getByText('Policy Core')).toBeInTheDocument();
    fireEvent.click(within(aside).getByRole('button', { name: /show in graph/i }));
    expect(h.onShowInGraph).toHaveBeenCalledWith('a');
    fireEvent.click(within(aside).getByRole('button', { name: /open details/i }));
    expect(h.onOpen).toHaveBeenCalledWith('a');
  });
});
