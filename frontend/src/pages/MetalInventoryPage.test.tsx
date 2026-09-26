// MetalInventoryPage — VIEWER role-projection regression (SEC-01).
//
// Every endpoint this page touches (purchases list, statistics, usage
// history, allocate-preview) is financial by nature and gated behind
// FINANCIAL_VIEW on the backend — a VIEWER 403s on all of them (see
// tests/integration/test_viewer_role_projection.py: metal_purchases_list,
// metal_usage, metal_statistics, metal_allocate_preview). Rather than
// firing four calls that all 403, the whole page is gated client-side: a
// VIEWER sees a permission hint and none of the fetches ever fire.
import { describe, expect, it, vi, afterEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithQuery } from '../test/queryWrapper';

const mockListPurchases = vi.fn();
vi.mock('../api', () => ({
  metalInventoryApi: {
    listPurchases: (...args: unknown[]) => mockListPurchases(...args),
  },
}));

const mockUseAuth = vi.fn();
vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: vi.fn() }),
  useConfirm: () => ({ showConfirm: vi.fn() }),
  useAuth: () => mockUseAuth(),
}));

// The summary cards, price chart and usage panel each make their own
// FINANCIAL_VIEW-gated calls (getStatistics / getSpotPrices / getUsageHistory)
// — stub them out so this test only has to reason about the page's own gate.
vi.mock('../components/metal/MetalSummaryCards', () => ({
  MetalSummaryCards: () => <div>summary-cards</div>,
}));
vi.mock('../components/metal/PriceChart', () => ({
  PriceChart: () => <div>price-chart</div>,
}));
vi.mock('../components/metal/UsageHistoryPanel', () => ({
  UsageHistoryPanel: () => <div>usage-history</div>,
}));
vi.mock('../components/metal/MetalPurchaseFormModal', () => ({
  MetalPurchaseFormModal: () => null,
}));
vi.mock('../components/metal/MetalTypeManager', () => ({
  MetalTypeManager: () => null,
}));
vi.mock('../components/metal/ConsumeMetalModal', () => ({
  ConsumeMetalModal: () => null,
}));

import { MetalInventoryPage } from './MetalInventoryPage';

afterEach(() => {
  vi.clearAllMocks();
});

describe('MetalInventoryPage — VIEWER role projection', () => {
  it('shows a permission hint and never calls listPurchases for VIEWER', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'VIEWER' } });
    mockListPurchases.mockResolvedValue([]);

    renderWithQuery(<MetalInventoryPage />);

    expect(await screen.findByText('Keine Berechtigung für Finanzdaten')).toBeInTheDocument();
    expect(mockListPurchases).not.toHaveBeenCalled();
    expect(screen.queryByText('summary-cards')).not.toBeInTheDocument();
  });

  it('loads purchases and renders the page for GOLDSMITH', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    mockListPurchases.mockResolvedValue([]);

    renderWithQuery(<MetalInventoryPage />);

    expect(await screen.findByText('summary-cards')).toBeInTheDocument();
    expect(mockListPurchases).toHaveBeenCalledWith({ include_depleted: true });
    expect(
      screen.queryByText('Keine Berechtigung für Finanzdaten')
    ).not.toBeInTheDocument();
  });
});

describe('MetalInventoryPage — admin-only metal type manager (FE-12)', () => {
  // The backend serialises roles lowercase ("admin"); the page used to
  // compare against 'ADMIN' and hid the button from every real admin.
  it('shows "Metalltypen verwalten" for an admin (wire value "admin")', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'admin' } });
    mockListPurchases.mockResolvedValue([]);

    renderWithQuery(<MetalInventoryPage />);

    expect(await screen.findByText('Metalltypen verwalten')).toBeInTheDocument();
  });

  it('hides "Metalltypen verwalten" for a goldsmith', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'goldsmith' } });
    mockListPurchases.mockResolvedValue([]);

    renderWithQuery(<MetalInventoryPage />);

    expect(await screen.findByText('summary-cards')).toBeInTheDocument();
    expect(screen.queryByText('Metalltypen verwalten')).not.toBeInTheDocument();
  });
});
