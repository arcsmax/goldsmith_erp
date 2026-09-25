import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('renders the page title as the only h1 with meta and actions', () => {
    render(
      <MemoryRouter>
        <PageHeader
          title="Aufträge"
          meta="12 von 40"
          back={{ to: '/dashboard', label: 'Heute' }}
          primaryAction={<button type="button">Neuer Auftrag</button>}
          secondaryActions={<button type="button">Exportieren</button>}
        />
      </MemoryRouter>,
    );
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1, name: 'Aufträge' })).toBeInTheDocument();
    expect(screen.getByText('12 von 40')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Heute/ })).toHaveAttribute('href', '/dashboard');
    expect(screen.getByRole('button', { name: 'Neuer Auftrag' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Exportieren' })).toBeInTheDocument();
  });

  it('works without optional parts', () => {
    render(<PageHeader title="Kunden" />);
    expect(screen.getByRole('heading', { level: 1, name: 'Kunden' })).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
