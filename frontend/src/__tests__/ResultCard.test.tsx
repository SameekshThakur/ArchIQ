import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { CopilotCard } from '@/api/types';
import { ResultCard } from '@/features/copilot/ResultCard';

const wrap = (card: CopilotCard) => render(<MemoryRouter><ResultCard card={card} /></MemoryRouter>);

describe('Copilot result cards', () => {
  it('renders a table with entity links and severity badges', () => {
    wrap({ type: 'table', columns: [{ key: 'name', label: 'Application', kind: 'ref' }, { key: 'criticality', label: 'Criticality', kind: 'severity' }], rows: [{ name: { id: 'APP-005', type: 'application', name: 'Claims Payments Hub' }, criticality: 'critical' }] });
    expect(screen.getByRole('button', { name: 'Claims Payments Hub' })).toBeInTheDocument();
    expect(screen.getByText('critical')).toBeInTheDocument();
  });
  it('renders dependency paths with the relationship on each hop', () => {
    wrap({ type: 'paths', title: 'Dependency paths', paths: [{ label: 'x', nodes: [{ id: 'APP-005', name: 'Claims Payments Hub', type: 'application', rel: null }, { id: 'DB-001', name: 'Policy Master DB', type: 'database', rel: 'direct_db' }] }] });
    expect(screen.getByText('direct db')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Policy Master DB' })).toBeInTheDocument();
  });
  it('renders metrics with grouped numbers', () => {
    wrap({ type: 'metrics', items: [{ label: 'Direct applications', value: 14, tone: 'danger' }] });
    expect(screen.getByText('Direct applications')).toBeInTheDocument();
    expect(screen.getByText('14')).toBeInTheDocument();
  });
  it('ignores unknown card types instead of crashing', () => {
    const { container } = wrap({ type: 'mystery' as CopilotCard['type'] });
    expect(container).toBeEmptyDOMElement();
  });
});
