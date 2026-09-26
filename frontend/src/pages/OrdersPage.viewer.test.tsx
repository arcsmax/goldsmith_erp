// LV-07: a VIEWER on /orders saw "+ Neuer Auftrag" (it opened the create
// dialog although VIEWER lacks ORDER_CREATE), the price column with
// "Wird berechnet" for every row and "Gesamtwert: 0,00 €". Gate them in
// code with the lib/roles.ts helpers (CLAUDE.md: never hide by CSS).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithQuery } from '../test/queryWrapper';

const mockGetAll = vi.fn();
// W3-03: the page reads GET /orders/?offset=… through pagedApi; tests hand
// back plain arrays, wrapped here in the Page envelope.
vi.mock('../api/paged', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/paged')>()),
  pagedApi: {
    orders: async (...a: unknown[]) => {
      const items = (await mockGetAll(...a)) as unknown[];
      return { items, total: items.length, limit: 25, offset: 0, next_offset: null };
    },
  },
}));

let mockRole = 'VIEWER';
vi.mock('../contexts', () => ({
  useAuth: () => ({ user: { id: 3, role: mockRole } }),
  useToast: () => ({ showToast: vi.fn() }),
  useConfirm: () => ({ showConfirm: vi.fn() }),
}));

vi.mock('../components/orders/OrderFormModal', () => ({
  OrderFormModal: () => null,
}));
vi.mock('../components/AuthenticatedImage', () => ({ default: () => null }));

import { OrdersPage } from './OrdersPage';

function order(id: number, price: number | null) {
  return {
    id,
    title: `Auftrag ${id}`,
    description: 'Ring',
    status: 'confirmed',
    customer_id: 1,
    price,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    first_photo_id: null,
  };
}

function renderPage() {
  return renderWithQuery(<OrdersPage />);
}

afterEach(() => {
  vi.clearAllMocks();
  mockGetAll.mockReset();
});

describe('OrdersPage role gating (LV-07)', () => {
  it('hides create, edit, delete, price column and total from a VIEWER', async () => {
    mockRole = 'VIEWER';
    mockGetAll.mockResolvedValue([order(1, null)]);
    renderPage();

    expect(await screen.findByText('Auftrag 1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Neuer Auftrag/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Preis' })).not.toBeInTheDocument();
    expect(screen.queryByText('Wird berechnet')).not.toBeInTheDocument();
    expect(screen.queryByText(/Gesamtwert/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Auftrag bearbeiten' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Auftrag löschen' })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Preis' })).not.toBeInTheDocument();
    // The count stays: it is not financial data.
    expect(screen.getByText(/1 Aufträge/)).toBeInTheDocument();
  });

  it('shows create, price and total to a GOLDSMITH, but not delete', async () => {
    mockRole = 'GOLDSMITH';
    mockGetAll.mockResolvedValue([order(1, 2100)]);
    renderPage();

    expect(await screen.findByText('Auftrag 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Neuer Auftrag/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Preis' })).toBeInTheDocument();
    expect(screen.getByText(/Gesamtwert/)).toBeInTheDocument();
    expect(screen.getAllByText(/2\.100,00\s€/).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Auftrag bearbeiten' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Auftrag löschen' })).not.toBeInTheDocument();
  });

  it('gives an ADMIN the delete action as well', async () => {
    mockRole = 'ADMIN';
    mockGetAll.mockResolvedValue([order(1, 2100)]);
    renderPage();

    expect(await screen.findByText('Auftrag 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Auftrag löschen' })).toBeInTheDocument();
  });
});
