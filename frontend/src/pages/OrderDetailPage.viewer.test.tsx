// OrderDetailPage — VIEWER role-projection regression (SEC-01, SEC-09,
// GDPR-03, GDPR-04).
//
// orders list/detail is "projected" for VIEWER: description,
// special_instructions, price, and nested materials[].unit_price are all
// stripped (tests/integration/test_viewer_role_projection.py::order_detail).
// order_photos_list is fully "gated" (403). Before this fix:
//   - photosApi.getForOrder was called unconditionally and 403'd for VIEWER
//   - the Materialien tab crashed on `material.unit_price.toFixed(...)`
//     once unit_price was undefined
//   - the Fotos/Kosten/Soll-Ist tabs stayed visible with no accessible data
// This test pins the fix: no crash, no forbidden calls, gated tabs absent.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { renderWithQuery } from '../test/queryWrapper';
import userEvent from '@testing-library/user-event';
import type { OrderType } from '../types';

const mockGetById = vi.fn();
vi.mock('../api', () => ({
  ordersApi: { getById: (...a: unknown[]) => mockGetById(...a) },
  materialsApi: {},
}));

const mockGetForOrder = vi.fn();
vi.mock('../api/photos', () => ({
  photosApi: { getForOrder: (...a: unknown[]) => mockGetForOrder(...a) },
}));

const mockUseAuth = vi.fn();
vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: vi.fn() }),
  // Real (component-local) state so clicking a tab button actually
  // switches `activeTab` — a plain vi.fn() stub can't reflect that back.
  useOrders: () => {
    const [tab, setTab] = useState('details');
    return {
      setActiveOrder: vi.fn(),
      setOrderTab: (_id: number, next: string) => setTab(next),
      getOrderTab: () => tab,
    };
  },
  useAuth: () => mockUseAuth(),
}));

// Header banner + customer card are unrelated to this test's focus; stub
// them so they don't need their own API mocks.
vi.mock('../components/orders/CostAlertBanner', () => ({
  CostAlertBanner: () => null,
}));
vi.mock('../components/orders/DeliveredActions', () => ({
  DeliveredActions: () => <div>abholprotokoll</div>,
}));
vi.mock('../components/orders/GemstoneList', () => ({ GemstoneList: () => <div>steine</div> }));
vi.mock('../components/orders/CustomerInfoCard', () => ({
  CustomerInfoCard: () => <div>customer-info</div>,
}));
// W2-08: the Arbeit tab mounts these together; each has its own API calls.
vi.mock('../components/TimeTrackingTab', () => ({ default: () => <div>time-tracking</div> }));
vi.mock('../components/scrap-gold', () => ({ ScrapGoldTab: () => <div>scrap-gold</div> }));
vi.mock('../components/orders/HandoffTab', () => ({ default: () => <div>handoff</div> }));
vi.mock('../components/orders/ArbeitszettelTab', () => ({ default: () => <div>arbeitszettel</div> }));
vi.mock('../components/orders/SollIstTab', () => ({ SollIstTab: () => <div>soll-ist</div> }));
vi.mock('../components/orders/CostBreakdownCard', () => ({
  CostBreakdownCard: () => <div>cost-breakdown</div>,
}));
vi.mock('../components/orders/CostChangeSection', () => ({
  CostChangeSection: () => <div>cost-change</div>,
}));

import { OrderDetailPage } from './OrderDetailPage';

function viewerAuth() {
  return { user: { role: 'VIEWER' } };
}
function goldsmithAuth() {
  return { user: { role: 'GOLDSMITH' } };
}

// Mirrors the real (type-violating) VIEWER wire payload: `description` and
// `price` are entirely absent (role_projection.py omits the keys), and
// each nested material is missing `unit_price`.
function makeViewerProjectedOrder(): OrderType {
  const order = {
    id: 42,
    title: 'Ring mit Solitär',
    status: 'completed',
    customer_id: 1,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-02T00:00:00Z',
    materials: [{ id: 1, name: 'Feingold 999', stock: 10, unit: 'g' }],
  } as unknown as OrderType;
  return order;
}

function makeFullOrder(): OrderType {
  return {
    id: 42,
    title: 'Ring mit Solitär',
    description: 'Entwurf: Solitärring, vertraulich',
    price: 1500,
    status: 'completed',
    customer_id: 1,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-02T00:00:00Z',
    materials: [
      { id: 1, name: 'Feingold 999', unit_price: 62.5, stock: 10, unit: 'g' },
    ],
  } as OrderType;
}

function renderPage() {
  return renderWithQuery(
    <Routes>
      <Route path="/orders/:orderId" element={<OrderDetailPage />} />
    </Routes>,
    { route: '/orders/42' }
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('OrderDetailPage — VIEWER role projection', () => {
  it('never calls photosApi.getForOrder and hides the Fotos/Kosten/Soll-Ist tabs for VIEWER', async () => {
    mockUseAuth.mockReturnValue(viewerAuth());
    mockGetById.mockResolvedValue(makeViewerProjectedOrder());

    renderPage();

    expect(await screen.findAllByText('Ring mit Solitär')).not.toHaveLength(0);
    expect(mockGetForOrder).not.toHaveBeenCalled();
    expect(screen.queryByRole('tab', { name: /Fotos/ })).not.toBeInTheDocument();

    // W2-08: Kosten and Soll/Ist are sections of the Arbeit tab now.
    await userEvent.click(screen.getByRole('tab', { name: 'Arbeit' }));
    expect(screen.queryByRole('heading', { name: 'Kosten' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Soll/Ist' })).not.toBeInTheDocument();
    expect(screen.queryByText('cost-breakdown')).not.toBeInTheDocument();
  });

  it('omits Beschreibung/Preis rows and does not crash on the Materialien tab for VIEWER', async () => {
    mockUseAuth.mockReturnValue(viewerAuth());
    mockGetById.mockResolvedValue(makeViewerProjectedOrder());

    renderPage();
    await screen.findAllByText('Ring mit Solitär');

    expect(screen.queryByText('Beschreibung:')).not.toBeInTheDocument();
    expect(screen.queryByText('Preis:')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'Arbeit' }));

    // W4-03: DataTable renders the table and the phone cards (CSS picks one).
    expect(await screen.findAllByText('Feingold 999')).not.toHaveLength(0);
    expect(screen.queryByText('Preis/Einheit')).not.toBeInTheDocument();
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
  });

  it('calls photosApi.getForOrder and shows the Fotos/Kosten/Soll-Ist tabs and price/description for GOLDSMITH', async () => {
    mockUseAuth.mockReturnValue(goldsmithAuth());
    mockGetById.mockResolvedValue(makeFullOrder());
    mockGetForOrder.mockResolvedValue({ data: [] });

    renderPage();

    expect(await screen.findAllByText('Ring mit Solitär')).not.toHaveLength(0);
    expect(mockGetForOrder).toHaveBeenCalledWith(42);
    expect(screen.getByRole('tab', { name: /Fotos \(/ })).toBeInTheDocument();
    expect(screen.getByText('Beschreibung:')).toBeInTheDocument();
    expect(screen.getByText('Preis:')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'Arbeit' }));
    expect(screen.getByRole('heading', { name: 'Kosten' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Soll/Ist' })).toBeInTheDocument();
  });
});
