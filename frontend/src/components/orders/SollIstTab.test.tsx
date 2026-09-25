// SollIstTab tests — W3-04 follow-up (defense-in-depth).
//
// docs/review/2026-09-25/PROGRESS.md "Open follow-ups": "SollIstTab.tsx has
// no internal FINANCIAL_VIEW guard, relies solely on the parent tab being
// hidden." Soll/Ist shows prices and costs (SEC-01 financial data), so it
// must refuse to render — and never even query — for a caller without
// FINANCIAL_VIEW, independent of whatever the parent tab does.
//
// Pins:
//   (a) a role without FINANCIAL_VIEW (VIEWER) sees the standard
//       "no permission" empty state and getComparison/getInvoices are never
//       called, even for a finished order.
//   (b) a role with FINANCIAL_VIEW (GOLDSMITH) on a finished order still
//       renders the comparison as before.
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithQuery } from '../../test/queryWrapper';
import type { OrderComparison } from '../../types';

const mockGetComparison = vi.fn();
const mockGetInvoices = vi.fn();
const mockCreateFromOrder = vi.fn();

vi.mock('../../api', () => ({
  ordersApi: { getComparison: (...args: unknown[]) => mockGetComparison(...args) },
  invoicesApi: {
    getInvoices: (...args: unknown[]) => mockGetInvoices(...args),
    createFromOrder: (...args: unknown[]) => mockCreateFromOrder(...args),
  },
}));

vi.mock('../../lib/logError', () => ({ logError: vi.fn() }));

const mockShowToast = vi.fn();
vi.mock('../../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}));

import { SollIstTab } from './SollIstTab';
import { FINANCIAL_HIDDEN_HINT } from '../../lib/roles';

function makeComparison(overrides: Partial<OrderComparison> = {}): OrderComparison {
  return {
    order_id: 1,
    order_title: 'Ring',
    order_type: 'custom',
    status: 'completed',
    completed_at: '2026-09-01T00:00:00Z',
    hours: { soll: 4, ist: 5, deviation_percent: 25, deviation_abs: 1, is_significant: true },
    material_weight: { soll: 10, ist: 10, deviation_percent: 0, deviation_abs: 0, is_significant: false },
    material_cost: { soll: 100, ist: 100, deviation_percent: 0, deviation_abs: 0, is_significant: false },
    total_price: { soll: 500, ist: 500, deviation_percent: 0, deviation_abs: 0, is_significant: false },
    activity_breakdown: [],
    overall_accuracy_score: 80,
    has_significant_deviation: true,
    ...overrides,
  };
}

describe('SollIstTab', () => {
  it('hides financial data and never queries for a role without FINANCIAL_VIEW', async () => {
    renderWithQuery(<SollIstTab orderId={1} orderStatus="completed" role="VIEWER" />);

    expect(await screen.findByText(FINANCIAL_HIDDEN_HINT)).toBeInTheDocument();
    expect(mockGetComparison).not.toHaveBeenCalled();
    expect(mockGetInvoices).not.toHaveBeenCalled();
  });

  it('renders the comparison for a finished order when the role has FINANCIAL_VIEW', async () => {
    mockGetComparison.mockResolvedValue(makeComparison());
    mockGetInvoices.mockResolvedValue([]);

    renderWithQuery(<SollIstTab orderId={1} orderStatus="completed" role="GOLDSMITH" />);

    await waitFor(() => expect(mockGetComparison).toHaveBeenCalledWith(1));
    expect(await screen.findByText('Kennzahlen Soll und Ist')).toBeInTheDocument();
    expect(screen.queryByText(FINANCIAL_HIDDEN_HINT)).not.toBeInTheDocument();
  });
});
