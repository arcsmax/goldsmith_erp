import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { DataTable, type Column } from './DataTable';
import { ListCard } from './ListCard';

interface Row {
  id: number;
  title: string;
  customer: string;
  price: number;
}

const ROWS: Row[] = [
  { id: 1, title: 'Trauringe', customer: 'Meier', price: 1200 },
  { id: 2, title: 'Kette kürzen', customer: 'Schulz', price: 45.5 },
];

const COLUMNS: Column<Row>[] = [
  { key: 'title', header: 'Titel', render: (r) => r.title, sortable: true },
  { key: 'customer', header: 'Kunde', render: (r) => r.customer, hideBelow: 'desktop' },
  { key: 'price', header: 'Preis', render: (r) => `${r.price} €`, numeric: true, sortable: true },
];

function renderTable(props: Partial<React.ComponentProps<typeof DataTable<Row>>> = {}) {
  return render(
    <MemoryRouter>
      <DataTable<Row>
        rows={ROWS}
        columns={COLUMNS}
        getRowKey={(r) => r.id}
        rowHref={(r) => `/orders/${r.id}`}
        caption="Aufträge"
        {...props}
      />
    </MemoryRouter>,
  );
}

describe('DataTable', () => {
  it('renders a semantic table with a caption', () => {
    renderTable();
    const table = screen.getByRole('table', { name: 'Aufträge' });
    expect(within(table).getAllByRole('columnheader')).toHaveLength(3);
    expect(within(table).getAllByRole('row')).toHaveLength(3);
  });

  it('makes rows navigable through a link, never a clickable row', () => {
    renderTable();
    const table = screen.getByRole('table');
    const link = within(table).getByRole('link', { name: 'Trauringe' });
    expect(link).toHaveAttribute('href', '/orders/1');
    for (const row of within(table).getAllByRole('row')) {
      expect(row).not.toHaveAttribute('onclick');
    }
  });

  it('right-aligns numeric columns with tabular numerals', () => {
    renderTable();
    const cell = within(screen.getByRole('table')).getByText('1200 €').closest('td');
    expect(cell).toHaveClass('ui-num', 'ui-align-end');
  });

  it('adds responsive hide classes from hideBelow', () => {
    renderTable();
    const header = within(screen.getByRole('table')).getByRole('columnheader', { name: 'Kunde' });
    expect(header).toHaveClass('ui-hide-below-desktop');
  });

  it('exposes aria-sort on sortable headers and toggles via a button', async () => {
    const onSortChange = vi.fn();
    const user = userEvent.setup();
    renderTable({ sort: { key: 'title', direction: 'asc' }, onSortChange });
    const table = screen.getByRole('table');
    const titleHeader = within(table).getByRole('columnheader', { name: /Titel/ });
    const priceHeader = within(table).getByRole('columnheader', { name: /Preis/ });
    const customerHeader = within(table).getByRole('columnheader', { name: 'Kunde' });
    expect(titleHeader).toHaveAttribute('aria-sort', 'ascending');
    expect(priceHeader).toHaveAttribute('aria-sort', 'none');
    expect(customerHeader).not.toHaveAttribute('aria-sort');

    await user.click(within(titleHeader).getByRole('button'));
    expect(onSortChange).toHaveBeenLastCalledWith({ key: 'title', direction: 'desc' });
    await user.click(within(priceHeader).getByRole('button'));
    expect(onSortChange).toHaveBeenLastCalledWith({ key: 'price', direction: 'asc' });
  });

  it('renders descending aria-sort', () => {
    renderTable({ sort: { key: 'price', direction: 'desc' }, onSortChange: vi.fn() });
    const header = within(screen.getByRole('table')).getByRole('columnheader', { name: /Preis/ });
    expect(header).toHaveAttribute('aria-sort', 'descending');
  });

  it('renders a card list for phones with one link per card', () => {
    renderTable();
    const list = screen.getByRole('list', { name: 'Aufträge' });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByRole('link')).toHaveAttribute('href', '/orders/1');
  });

  it('shows the EmptyState when there are no rows', () => {
    renderTable({
      rows: [],
      empty: { title: 'Noch keine Aufträge', action: <button type="button">Ersten Auftrag anlegen</button> },
    });
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByText('Noch keine Aufträge')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ersten Auftrag anlegen' })).toBeInTheDocument();
  });

  it('delegates loading and error to PageState', async () => {
    const retry = vi.fn();
    const { rerender } = renderTable({ state: { status: 'loading' } });
    expect(screen.getByRole('status')).toHaveTextContent('Wird geladen…');
    rerender(
      <MemoryRouter>
        <DataTable<Row>
          rows={ROWS}
          columns={COLUMNS}
          getRowKey={(r) => r.id}
          caption="Aufträge"
          state={{ status: 'error', error: 'Aufträge konnten nicht geladen werden.', retry }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Aufträge konnten nicht geladen werden.');
    await userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});

describe('ListCard', () => {
  it('is a single link containing title and meta', () => {
    render(
      <MemoryRouter>
        <ListCard href="/orders/1" title="Trauringe" meta="Meier" />
      </MemoryRouter>,
    );
    const link = screen.getByRole('link', { name: /Trauringe/ });
    expect(link).toHaveAttribute('href', '/orders/1');
    expect(link).toHaveTextContent('Meier');
    expect(link).toHaveClass('ui-list-card');
  });

  it('renders as plain content without href', () => {
    render(<ListCard title="Ohne Link" />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByText('Ohne Link')).toBeInTheDocument();
  });
});
