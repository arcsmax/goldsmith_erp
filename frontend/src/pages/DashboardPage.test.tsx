// DashboardPage — "Heute" lanes (W2-03; FE-05, DOM-14, DOM-15).
//
// Pins: overdue lane first and in the danger style; every row links to its
// next action (order, repair, cost change, customer update); repairs are
// included; a load failure shows an error with retry instead of an empty
// "all done"; VIEWER gets no repair links and no amounts; live hints on
// realtime invalidation (W3-03) reload the summary.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OrderProvider } from '../contexts/OrderContext';
import { invalidateForChannel } from '../lib/realtimeInvalidation';
import { renderWithQuery } from '../test/queryWrapper';
import type { DashboardToday } from '../api/dashboard';

const mockGetToday = vi.fn();
vi.mock('../api/dashboard', () => ({
  dashboardApi: { getToday: (...args: unknown[]) => mockGetToday(...args) },
}));

const mockUseAuth = vi.fn();
vi.mock('../contexts', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../components/dashboard/DashboardKPIs', () => ({
  DashboardKPIs: () => <div data-testid="kpis" />,
}));
vi.mock('../components/dashboard/AlertsWidget', () => ({
  AlertsWidget: () => <div data-testid="alerts" />,
}));
vi.mock('../components/dashboard/HandoffLane', () => ({
  HandoffLane: () => null,
}));

import { DashboardPage } from './DashboardPage';

function makeSummary(overrides: Partial<DashboardToday> = {}): DashboardToday {
  return {
    today: '2026-09-25',
    generated_at: '2026-09-25T06:30:00',
    can_view_financials: true,
    truncated: false,
    overdue: [
      {
        kind: 'repair',
        id: 7,
        reference: 'REP-2026-0901',
        title: 'Kettenverschluss defekt',
        status: 'in_repair',
        due_date: '2026-09-23',
        days_overdue: 2,
        customer_name: 'Maria Muster',
        bag_number: 'T-11',
      },
      {
        kind: 'order',
        id: 1,
        reference: '#1',
        title: 'Trauringe Meier',
        status: 'in_progress',
        due_date: '2026-09-24',
        days_overdue: 1,
        customer_name: 'Maria Muster',
      },
    ],
    due_soon: [
      {
        kind: 'order',
        id: 2,
        reference: '#2',
        title: 'Kette Schulz',
        status: 'confirmed',
        due_date: '2026-09-27',
        days_overdue: -2,
      },
    ],
    customer_pending: [
      {
        kind: 'cost_change',
        id: 11,
        title: 'Collier mit Stein',
        reference: '#5',
        since: '2026-09-20T10:00:00',
        order_id: 5,
        amount: 950,
      },
      {
        kind: 'customer_update',
        id: 12,
        title: 'Trauringe Meier',
        reference: '#1',
        since: '2026-09-21T10:00:00',
        order_id: 1,
      },
      {
        kind: 'repair_ready',
        id: 8,
        title: 'Ring geweitet',
        reference: 'REP-2026-0902',
        since: '2026-09-22T10:00:00',
        repair_id: 8,
        bag_number: 'T-12',
      },
    ],
    timers: [],
    counts: { overdue: 2, due_soon: 1, customer_pending: 3, timers: 0 },
    ...overrides,
  };
}

function renderPage() {
  return renderWithQuery(
    <OrderProvider>
      <DashboardPage />
    </OrderProvider>,
  );
}

function lane(title: RegExp): HTMLElement {
  const heading = screen.getByRole('heading', { name: title });
  const section = heading.closest('section');
  if (!section) throw new Error(`lane ${title} not found`);
  return section;
}

beforeEach(() => {
  mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH', first_name: 'Anne' } });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('DashboardPage — Heute lanes', () => {
  it('renders the overdue lane first, in the danger style, most overdue first', async () => {
    mockGetToday.mockResolvedValue(makeSummary());
    renderPage();

    await screen.findByRole('heading', { name: /Überfällig/ });
    const laneHeadings = screen
      .getAllByRole('heading', { level: 2 })
      .map((h) => h.textContent ?? '');
    expect(laneHeadings[0]).toMatch(/^Überfällig/);

    const rows = within(lane(/Überfällig/)).getAllByRole('link');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Kettenverschluss defekt');
    expect(rows[0]).toHaveAttribute('href', '/repairs/7');
    expect(rows[1]).toHaveTextContent('Trauringe Meier');
    expect(rows[1]).toHaveTextContent('1 Tag überfällig');
    expect(rows[1]).toHaveAttribute('href', '/orders/1');
    rows.forEach((row) => expect(row).toHaveClass('deadline-urgent'));
  });

  it('links every customer-pending row to its next action', async () => {
    mockGetToday.mockResolvedValue(makeSummary());
    renderPage();

    await screen.findByRole('heading', { name: /Wartet auf Kunde/ });
    const pending = lane(/Wartet auf Kunde/);
    expect(within(pending).getByRole('link', { name: /Kostenänderung ansehen/ })).toHaveAttribute(
      'href',
      '/orders/5',
    );
    expect(
      within(pending).getByRole('link', { name: /Kundeninfo erneut senden/ }),
    ).toHaveAttribute('href', '/orders/1');
    expect(within(pending).getByRole('link', { name: /Abholung erfassen/ })).toHaveAttribute(
      'href',
      '/repairs/8',
    );
    expect(within(pending).getByText(/950,00/)).toBeInTheDocument();
  });

  it('opens the order on the matching tab when a cost-change row is tapped', async () => {
    mockGetToday.mockResolvedValue(makeSummary());
    renderPage();

    const link = await screen.findByRole('link', { name: /Kostenänderung ansehen/ });
    await userEvent.click(link);
    const stored = JSON.parse(localStorage.getItem('goldsmith_order_tabs') ?? '[]');
    expect(JSON.stringify(stored)).toContain('kosten');
  });

  it('shows an error with retry instead of an empty lane when loading fails', async () => {
    mockGetToday.mockRejectedValueOnce(new Error('network down'));
    mockGetToday.mockResolvedValueOnce(makeSummary());
    renderPage();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('konnte nicht geladen werden');
    expect(screen.queryByText(/alles erledigt/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Übersicht neu laden' }));
    expect(await screen.findByRole('heading', { name: /Überfällig/ })).toBeInTheDocument();
    expect(mockGetToday).toHaveBeenCalledTimes(2);
  });

  it('gives VIEWER no repair links and no amounts', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'VIEWER', first_name: 'Vera' } });
    const summary = makeSummary({
      can_view_financials: false,
      customer_pending: [
        {
          kind: 'repair_ready',
          id: 8,
          title: 'Ring geweitet',
          reference: 'REP-2026-0902',
          since: '2026-09-22T10:00:00',
          repair_id: 8,
        },
      ],
    });
    mockGetToday.mockResolvedValue(summary);
    renderPage();

    await screen.findByRole('heading', { name: /Überfällig/ });
    const overdueLinks = within(lane(/Überfällig/)).getAllByRole('link');
    expect(overdueLinks).toHaveLength(1);
    expect(overdueLinks[0]).toHaveAttribute('href', '/orders/1');
    expect(screen.getByText('Kettenverschluss defekt')).toBeInTheDocument();
    expect(within(lane(/Wartet auf Kunde/)).queryAllByRole('link')).toHaveLength(0);
    expect(screen.queryByText(/€/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('kpis')).not.toBeInTheDocument();
  });

  it('shows the Kennzahlen section below the work lanes for ADMIN', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'ADMIN', first_name: 'Anne' } });
    mockGetToday.mockResolvedValue(makeSummary());
    renderPage();

    await screen.findByRole('heading', { name: /Überfällig/ });
    expect(screen.getByTestId('kpis')).toBeInTheDocument();
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(headings[0]).toMatch(/^Überfällig/);
    expect(headings[headings.length - 1]).toBe('Kennzahlen');
  });

  it('reloads the summary when a live order hint arrives', async () => {
    mockGetToday.mockResolvedValue(makeSummary());
    const { client } = renderPage();
    await screen.findByRole('heading', { name: /Überfällig/ });
    expect(mockGetToday).toHaveBeenCalledTimes(1);

    await act(() => invalidateForChannel(client, 'order_updates'));
    expect(mockGetToday).toHaveBeenCalledTimes(2);

    await act(() => invalidateForChannel(client, 'time_tracking_updates'));
    expect(mockGetToday).toHaveBeenCalledTimes(3);
  });
});
