// CostAlertBanner tests — V1.2 Task 4.
//
// Pins:
//   (a) over_threshold:false → renders nothing (no fetch result surfaces).
//   (b) over_threshold:true, baseline_source:'quote' → renders delta_abs +
//       delta_percent (one decimal) + the quote-baseline phrasing.
//   (c) baseline_source:'approved_change' → the approved-change phrasing.
//   (d) clicking the CTA calls onCreateCostChange.
//   (e) VIEWER (hasRole → false) → renders nothing AND getProjectedCost is
//       never called (COST_CHANGE_VIEW 403s backend-side for VIEWER).
//   (f) a failed fetch is swallowed + logged, never crashes the page.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ProjectedCost } from '../../api/customer-updates';
import { formatCurrency, formatPercentage } from '../../utils/formatters';

// jest-dom's toHaveTextContent normalizer collapses all whitespace (including
// the NBSP that Intl.NumberFormat('de-DE', {style:'currency'}) places before
// the € sign) down to a single regular space — so the *expected* string must
// be normalized the same way, or an exact-match NBSP never matches.
function normalizeSpace(value: string): string {
  return value.replace(/ /g, ' ');
}

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetProjectedCost = vi.fn();
vi.mock('../../api/customer-updates', () => ({
  customerUpdatesApi: {
    getProjectedCost: (...args: unknown[]) => mockGetProjectedCost(...args),
  },
}));

const mockLogError = vi.fn();
vi.mock('../../lib/logError', () => ({
  logError: (...args: unknown[]) => mockLogError(...args),
}));

const mockUseAuth = vi.fn();
vi.mock('../../contexts', () => ({
  useAuth: () => mockUseAuth(),
}));

import { CostAlertBanner } from './CostAlertBanner';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function manageAuth() {
  return { hasRole: () => true };
}

function viewerAuth() {
  return { hasRole: () => false };
}

function makeProjectedCost(overrides: Partial<ProjectedCost> = {}): ProjectedCost {
  return {
    material_cost: 100,
    gemstone_cost: 50,
    labor_minutes_billable: 120,
    labor_cost: 150,
    projected_total: 1245.5,
    quote_id: 9,
    quote_total: 1000,
    delta_percent: 24.55,
    delta_abs: 245.5,
    over_threshold: true,
    baseline_source: 'quote',
    ...overrides,
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CostAlertBanner', () => {
  it('renders nothing when over_threshold is false', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockGetProjectedCost.mockResolvedValue(makeProjectedCost({ over_threshold: false }));

    const { container } = render(
      <CostAlertBanner orderId={1} onCreateCostChange={vi.fn()} />
    );

    await waitFor(() => expect(mockGetProjectedCost).toHaveBeenCalledWith(1));
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders delta_abs + delta_percent + quote-baseline phrasing when over threshold', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockGetProjectedCost.mockResolvedValue(
      makeProjectedCost({ baseline_source: 'quote', delta_abs: 245.5, delta_percent: 24.55 })
    );

    render(<CostAlertBanner orderId={2} onCreateCostChange={vi.fn()} />);

    const banner = await screen.findByRole('alert');
    expect(banner).toHaveTextContent(normalizeSpace(formatCurrency(245.5)));
    expect(banner).toHaveTextContent(formatPercentage(24.55));
    expect(banner).toHaveTextContent('gegenüber dem Kostenvoranschlag');
  });

  it('shows the approved-change baseline phrasing when baseline_source is approved_change', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockGetProjectedCost.mockResolvedValue(
      makeProjectedCost({ baseline_source: 'approved_change' })
    );

    render(<CostAlertBanner orderId={3} onCreateCostChange={vi.fn()} />);

    const banner = await screen.findByRole('alert');
    expect(banner).toHaveTextContent('gegenüber der bereits genehmigten Kostenänderung');
  });

  it('shows a neutral phrasing when baseline_source is null/undefined', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockGetProjectedCost.mockResolvedValue(makeProjectedCost({ baseline_source: null }));

    render(<CostAlertBanner orderId={4} onCreateCostChange={vi.fn()} />);

    const banner = await screen.findByRole('alert');
    expect(banner).toHaveTextContent('gegenüber der Kalkulationsbasis');
  });

  it('calls onCreateCostChange when the CTA is clicked', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockGetProjectedCost.mockResolvedValue(makeProjectedCost());
    const onCreateCostChange = vi.fn();

    render(<CostAlertBanner orderId={5} onCreateCostChange={onCreateCostChange} />);

    const button = await screen.findByRole('button', { name: '§649 Kostenänderung anlegen' });
    await userEvent.click(button);

    expect(onCreateCostChange).toHaveBeenCalledTimes(1);
  });

  it('renders nothing and never calls getProjectedCost for a VIEWER', async () => {
    mockUseAuth.mockReturnValue(viewerAuth());

    const { container } = render(
      <CostAlertBanner orderId={6} onCreateCostChange={vi.fn()} />
    );

    // Give any stray microtask a chance to run before asserting the negative.
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(mockGetProjectedCost).not.toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });

  it('swallows a failed fetch, logs it, and renders nothing', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    const error = new Error('network down');
    mockGetProjectedCost.mockRejectedValue(error);

    const { container } = render(
      <CostAlertBanner orderId={7} onCreateCostChange={vi.fn()} />
    );

    await waitFor(() => expect(mockLogError).toHaveBeenCalledWith('CostAlertBanner.load', error));
    expect(container).toBeEmptyDOMElement();
  });
});
