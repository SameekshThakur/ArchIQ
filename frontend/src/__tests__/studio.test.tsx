import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { moveOps, removeEdgeOps, removeNodeOps, updateNodeOps } from '@/features/studio/ArchitectureEditor';
import { RequirementForm } from '@/features/studio/RequirementSteps';
import type { Catalog } from '@/features/studio/types';

type Op = Record<string, unknown>;

describe('diagram edits are kept as a list of operations', () => {
  it('removing a component you added removes it and its connections instead of recording a removal', () => {
    const ops: Op[] = [{ op: 'add_node', id: 'N1', role: 'compute', name: 'X' }, { op: 'add_edge', source: 'N1', target: 'A' }, { op: 'add_edge', source: 'B', target: 'N1' }, { op: 'move_node', id: 'N1', x: 1, y: 2 }];
    expect(removeNodeOps(ops, 'N1')).toEqual([]);
  });
  it('removing a blueprint component records a removal and drops edits that would point at it', () => {
    const ops: Op[] = [{ op: 'move_node', id: 'A', x: 1, y: 2 }, { op: 'add_edge', source: 'A', target: 'B' }, { op: 'add_edge', source: 'C', target: 'D' }];
    expect(removeNodeOps(ops, 'A')).toEqual([{ op: 'add_edge', source: 'C', target: 'D' }, { op: 'remove_node', id: 'A' }]);
  });
  it('removing a connection you added just forgets it; removing a blueprint connection records it', () => {
    expect(removeEdgeOps([{ op: 'add_edge', source: 'A', target: 'B' }], 'A', 'B')).toEqual([]);
    expect(removeEdgeOps([], 'A', 'B')).toEqual([{ op: 'remove_edge', source: 'A', target: 'B' }]);
  });
  it('moving a component keeps only its latest position', () => {
    const ops = moveOps(moveOps([], 'A', 10.4, 20.6), 'A', 30, 40);
    expect(ops).toEqual([{ op: 'move_node', id: 'A', x: 30, y: 40 }]);
  });
  it('property edits merge into one update per component, and clearing one is recorded as null', () => {
    const one = updateNodeOps([], 'A', { props: { tls: 'tls12' } });
    const two = updateNodeOps(one, 'A', { name: 'Renamed', props: { logging: true } });
    expect(two).toEqual([{ op: 'update_node', id: 'A', name: 'Renamed', props: { tls: 'tls12', logging: true } }]);
    expect(updateNodeOps(two, 'A', { props: { tls: null } })[0].props).toEqual({ tls: null, logging: true });
  });
  it('editing a component you added changes the addition itself, and a cleared property is dropped', () => {
    const ops: Op[] = [{ op: 'add_node', id: 'N1', role: 'compute', name: 'X', props: { tls: 'tls12', logging: true } }];
    expect(updateNodeOps(ops, 'N1', { name: 'Y', props: { tls: null } })).toEqual([{ op: 'add_node', id: 'N1', role: 'compute', name: 'Y', props: { logging: true } }]);
  });
});

const catalog = { domains: ['Claims', 'Finance'] } as unknown as Catalog;

describe('the requirements form', () => {
  it('refuses text that is too short without sending anything', () => {
    const onSubmit = vi.fn();
    render(<RequirementForm catalog={catalog} onSubmit={onSubmit} busy={false} error={null} submitLabel="Analyse" />);
    fireEvent.change(screen.getByLabelText(/Business or technical requirements/), { target: { value: 'too short' } });
    fireEvent.click(screen.getByRole('button', { name: 'Analyse' }));
    expect(screen.getByRole('alert')).toHaveTextContent(/at least a sentence/i);
    expect(onSubmit).not.toHaveBeenCalled();
  });
  it('submits trimmed text once it is long enough, and shows a server error', () => {
    const onSubmit = vi.fn();
    const { rerender } = render(<RequirementForm catalog={catalog} onSubmit={onSubmit} busy={false} error={null} submitLabel="Analyse" />);
    fireEvent.change(screen.getByLabelText(/Business or technical requirements/), { target: { value: '  A claims portal with 99.9% availability.  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Analyse' }));
    expect(onSubmit).toHaveBeenCalledWith({ text: 'A claims portal with 99.9% availability.', title: '', domain: '' });
    rerender(<RequirementForm catalog={catalog} onSubmit={onSubmit} busy={false} error="The API is unreachable." submitLabel="Analyse" />);
    expect(screen.getByRole('alert')).toHaveTextContent('The API is unreachable.');
  });
  it('inserts an example without sending it', () => {
    const onSubmit = vi.fn();
    render(<RequirementForm catalog={catalog} onSubmit={onSubmit} busy={false} error={null} submitLabel="Analyse" />);
    fireEvent.click(screen.getByRole('button', { name: 'Partner APIs' }));
    expect((screen.getByLabelText(/Business or technical requirements/) as HTMLTextAreaElement).value).toMatch(/broker partners/);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
