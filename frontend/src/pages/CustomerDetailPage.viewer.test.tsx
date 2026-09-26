// CustomerDetailPage — VIEWER role-projection regression (SEC-09/GDPR-04)
// and the W2-01 first_photo_id fix for the Auftragshistorie tab.
//
// The Auftragshistorie tab used to fetch a thumbnail per order via
// photosApi.getForOrder — GET /orders/{id}/photos 403s for a caller without
// DESIGN_VIEW (VIEWER), and even for a caller who CAN view it, that was one
// extra request per order. The fix reads `first_photo_id` straight off the
// orders-list response (added in W2-01) and renders it through the
// authenticated `/photos/{id}/thumbnail` route, so photosApi.getForOrder is
// never called from this tab any more — for VIEWER or for GOLDSMITH.
//
// Note: /customers/:id is currently ADMIN/GOLDSMITH-only at the router
// level (App.tsx ProtectedRoute) and in the sidebar nav (MainLayout.tsx) —
// both out of scope here — so the VIEWER case below is defense-in-depth
// against a direct render (as this test does) or a future routing change,
// not a presently reachable path for VIEWER.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import type { Customer } from '../types';
import type { OrderListItem } from '../api/orders';

const mockGetById = vi.fn();
const mockOrdersGetAll = vi.fn();
vi.mock('../api', () => ({
  customersApi: { getById: (...a: unknown[]) => mockGetById(...a) },
  ordersApi: { getAll: (...a: unknown[]) => mockOrdersGetAll(...a) },
}));

const mockGetForOrder = vi.fn();
vi.mock('../api/photos', () => ({
  photosApi: { getForOrder: (...a: unknown[]) => mockGetForOrder(...a) },
  photoThumbnailPath: (photoId: string) => `/photos/${photoId}/thumbnail`,
}));

// Thumbnails go through an authenticated fetch; render the requested src
// so the test can assert the URL without an HTTP mock (same pattern as
// OrderDetailPage.photos.test.tsx).
vi.mock('../components/AuthenticatedImage', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    <img data-testid="auth-img" data-src={src} alt={alt} />
  ),
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

function makeOrder(id: number, firstPhotoId: string | null = null): OrderListItem {
  return {
    id,
    title: `Auftrag ${id}`,
    description: 'x',
    price: null,
    status: 'new',
    customer_id: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    first_photo_id: firstPhotoId,
  } as OrderListItem;
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
    mockOrdersGetAll.mockResolvedValue([makeOrder(1), makeOrder(2, 'photo-2')]);

    renderPage();
    await screen.findByText('anna@example.com');

    await userEvent.click(screen.getByRole('tab', { name: 'Auftragshistorie' }));

    expect(await screen.findByText('Auftrag 1')).toBeInTheDocument();
    expect(mockGetForOrder).not.toHaveBeenCalled();
    // VIEWER never gets a thumbnail rendered, even when the (hypothetical)
    // list response carried a first_photo_id — canDesign gates it client-side too.
    expect(screen.queryByTestId('auth-img')).not.toBeInTheDocument();
  });

  it('never calls photosApi.getForOrder for GOLDSMITH and renders thumbnails from first_photo_id', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    mockGetById.mockResolvedValue(makeCustomer());
    mockOrdersGetAll.mockResolvedValue([
      makeOrder(1, 'photo-abc'),
      makeOrder(2, null),
    ]);

    renderPage();
    await screen.findByText('anna@example.com');

    await userEvent.click(screen.getByRole('tab', { name: 'Auftragshistorie' }));

    expect(await screen.findByText('Auftrag 1')).toBeInTheDocument();
    expect(screen.getByText('Auftrag 2')).toBeInTheDocument();

    // No per-order photo list request — the thumbnail comes straight off
    // the orders-list response (W2-01's `first_photo_id`).
    expect(mockGetForOrder).not.toHaveBeenCalled();

    // Order 1 has a photo: rendered via AuthenticatedImage against the
    // authenticated thumbnail route, not the old `/orders/{id}/photos/{id}/file` URL.
    const thumb = screen.getByTestId('auth-img');
    expect(thumb).toHaveAttribute('data-src', '/photos/photo-abc/thumbnail');

    // Order 2 has no photo: placeholder, not a thumbnail request.
    expect(screen.getAllByLabelText('Kein Foto vorhanden')).toHaveLength(1);
  });
});
