// CustomerDetailPage — VIEWER role-projection regression (SEC-09/GDPR-04).
//
// The Auftragshistorie tab fetches a thumbnail per order via
// photosApi.getForOrder — GET /orders/{id}/photos 403s for a caller without
// DESIGN_VIEW (VIEWER). The previous code called it for every order
// regardless of role and swallowed the resulting 403 in a catch block, so
// it never crashed but did fire a doomed request per order. This pins that
// the call is skipped outright for VIEWER and still made for GOLDSMITH.
//
// Note: /customers/:id is currently ADMIN/GOLDSMITH-only at the router
// level (App.tsx ProtectedRoute) and in the sidebar nav (MainLayout.tsx) —
// both out of scope here — so this guard is defense-in-depth against a
// direct render (as this test does) or a future routing change, not a
// presently reachable path for VIEWER.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import type { Customer, OrderType } from '../types';

const mockGetById = vi.fn();
const mockOrdersGetAll = vi.fn();
vi.mock('../api', () => ({
  customersApi: { getById: (...a: unknown[]) => mockGetById(...a) },
  ordersApi: { getAll: (...a: unknown[]) => mockOrdersGetAll(...a) },
}));

const mockGetForOrder = vi.fn();
vi.mock('../api/photos', () => ({
  photosApi: { getForOrder: (...a: unknown[]) => mockGetForOrder(...a) },
}));

const mockUseAuth = vi.fn();
vi.mock('../contexts', () => ({
  useAuth: () => {
    const value = mockUseAuth() as { user?: { role?: string } };
    const role = value?.user?.role ?? '';
    return {
      hasRole: (roles: string | string[]) =>
        (Array.isArray(roles) ? roles : [roles]).includes(role),
      ...value,
    };
  },
  useToast: () => ({ showToast: vi.fn() }),
  useConfirm: () => ({ showConfirm: vi.fn().mockResolvedValue(false) }),
}));

// The consent panel mounted on this page lists consents on render; keep it inert here.
vi.mock('../api/consents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/consents')>()),
  consentsApi: {
    list: vi.fn().mockResolvedValue([]),
    grant: vi.fn(),
    revoke: vi.fn(),
  },
}));

import { CustomerDetailPage } from './CustomerDetailPage';

function makeCustomer(): Customer {
  return {
    id: 1,
    first_name: 'Anna',
    last_name: 'Beispiel',
    email: 'anna@example.com',
    country: 'DE',
    customer_type: 'private',
    tags: [],
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function makeOrder(id: number): OrderType {
  return {
    id,
    title: `Auftrag ${id}`,
    description: 'x',
    price: null,
    status: 'new',
    customer_id: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  } as OrderType;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/customers/1']}>
      <Routes>
        <Route path="/customers/:id" element={<CustomerDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('CustomerDetailPage — VIEWER role projection (Auftragshistorie tab)', () => {
  it('never calls photosApi.getForOrder for VIEWER', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'VIEWER' } });
    mockGetById.mockResolvedValue(makeCustomer());
    mockOrdersGetAll.mockResolvedValue([makeOrder(1), makeOrder(2)]);

    renderPage();
    await screen.findByText('anna@example.com');

    await userEvent.click(screen.getByRole('tab', { name: 'Auftragshistorie' }));

    expect(await screen.findByText('Auftrag 1')).toBeInTheDocument();
    expect(mockGetForOrder).not.toHaveBeenCalled();
  });

  it('calls photosApi.getForOrder per order for GOLDSMITH', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    mockGetById.mockResolvedValue(makeCustomer());
    mockOrdersGetAll.mockResolvedValue([makeOrder(1)]);
    mockGetForOrder.mockResolvedValue({ data: [] });

    renderPage();
    await screen.findByText('anna@example.com');

    await userEvent.click(screen.getByRole('tab', { name: 'Auftragshistorie' }));

    expect(await screen.findByText('Auftrag 1')).toBeInTheDocument();
    expect(mockGetForOrder).toHaveBeenCalledWith(1);
  });
});
