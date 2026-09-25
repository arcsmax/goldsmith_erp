// Werkstatt board (W6 kanban over GET /jobs): columns per unified status,
// cards with number/title/customer/stage/deadline, kind and customer filters
// in the request, "Weiter" through the existing per-kind endpoints, arrow-key
// column navigation, and a realtime order hint refreshing the board.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../test/queryWrapper';

const mockGet = vi.fn();
const mockPatch = vi.fn();
const mockPost = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: (...a: unknown[]) => mockGet(...a),
    patch: (...a: unknown[]) => mockPatch(...a),
    post: (...a: unknown[]) => mockPost(...a),
  },
}));

let mockRole = 'GOLDSMITH';
const mockShowToast = vi.fn();
vi.mock('../contexts', () => ({
  useAuth: () => ({ user: { id: 1, role: mockRole } }),
  useToast: () => ({ showToast: mockShowToast }),
}));

import { WorkshopBoardPage } from './WorkshopBoardPage';
import { BOARD_COLUMNS } from '../components/workshop/boardModel';
import { invalidateForChannel } from '../lib/realtimeInvalidation';

type Params = { status?: string[]; kind?: string; customer_id?: number; limit?: number };

function job(id: number, overrides: Record<string, unknown> = {}) {
  return {
    id,
    kind: 'order',
    number: `AU-2026-${String(id).padStart(4, '0')}`,
    title: `Siegelring ${id}`,
    status: 'in_progress',
    kind_status: 'in_progress',
    status_label: 'In Arbeit',
    customer: { id: 3, display_name: 'Erika Muster' },
    customer_id: 3,
    deadline: null,
    order_id: 100 + id,
    repair_id: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

const BOARD_JOBS = [
  job(1),
  job(2, {
    kind: 'repair',
    number: 'REP-2026-0002',
    title: 'Kette löten',
    status: 'in_progress',
    kind_status: 'in_repair',
    order_id: null,
    repair_id: 7,
  }),
  job(3, { status: 'draft', kind_status: 'draft', customer: null, customer_id: null }),
];

function serveJobs(jobs = BOARD_JOBS) {
  mockGet.mockImplementation((url: string, config?: { params?: Params }) => {
    if (url === '/customers/search') {
      return Promise.resolve({
        data: [{ id: 9, first_name: 'Hans', last_name: 'Gold', company_name: null }],
      });
    }
    const status = config?.params?.status?.[0];
    const items = jobs.filter((j) => j.status === status);
    return Promise.resolve({
      data: { items, total: items.length, limit: 200, offset: 0, next_offset: null },
    });
  });
}

function jobCalls(): Params[] {
  return mockGet.mock.calls.filter(([url]) => url === '/jobs/').map(([, config]) => config.params);
}

function column(name: string) {
  return screen.getByRole('region', { name: new RegExp(`^${name}`) });
}

async function renderBoard() {
  const result = renderWithQuery(<WorkshopBoardPage />, { route: '/werkstatt' });
  await screen.findByRole('link', { name: 'AU-2026-0001' });
  return result;
}

afterEach(() => {
  mockGet.mockReset();
  mockPatch.mockReset();
  mockPost.mockReset();
  mockShowToast.mockReset();
  mockRole = 'GOLDSMITH';
});

describe('WorkshopBoardPage', () => {
  it('asks /jobs once per status column (≤ 200 each) and renders the cards in their columns', async () => {
    serveJobs();
    await renderBoard();

    const calls = jobCalls();
    expect(calls.map((p) => p.status)).toEqual(BOARD_COLUMNS.map((s) => [s]));
    calls.forEach((p) => {
      expect(p.limit).toBe(200);
      expect(p).not.toHaveProperty('kind');
      expect(p).not.toHaveProperty('customer_id');
    });

    const inProgress = column('In Arbeit');
    expect(within(inProgress).getByRole('link', { name: 'AU-2026-0001' })).toHaveAttribute(
      'href',
      '/orders/101',
    );
    expect(within(inProgress).getByRole('link', { name: 'REP-2026-0002' })).toHaveAttribute(
      'href',
      '/repairs/7',
    );
    expect(within(inProgress).getByText('Kette löten')).toBeInTheDocument();
    expect(within(inProgress).getAllByText('Erika Muster')).toHaveLength(2);
    // Finer per-kind stage on the card, German label from status.ts.
    expect(within(inProgress).getByText('In Bearbeitung')).toBeInTheDocument();

    const draft = column('Entwurf');
    expect(within(draft).getByText('Ohne Kunde')).toBeInTheDocument();
    expect(within(column('Fertig')).getByText('Keine Einträge')).toBeInTheDocument();
  });

  it('sends the kind filter and the picked customer with every column request', async () => {
    serveJobs();
    await renderBoard();

    await userEvent.selectOptions(screen.getByLabelText('Art'), 'repair');
    await waitFor(() => expect(jobCalls().filter((p) => p.kind === 'repair')).toHaveLength(8));

    await userEvent.type(screen.getByLabelText(/^Kunde/), 'Ha');
    await userEvent.click(await screen.findByRole('button', { name: 'Hans Gold' }));
    await waitFor(() =>
      expect(jobCalls().filter((p) => p.kind === 'repair' && p.customer_id === 9)).toHaveLength(8),
    );
    expect(screen.getByText('Hans Gold')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Kunde entfernen' }));
    expect(screen.getByLabelText(/^Kunde/)).toBeInTheDocument();
  });

  it('Weiter on an order card patches the order status to its primary next status', async () => {
    serveJobs();
    mockPatch.mockResolvedValue({ data: {} });
    await renderBoard();
    const callsBefore = jobCalls().length;

    await userEvent.click(screen.getByRole('button', { name: 'Weiter: Qualitätskontrolle (AU-2026-0001)' }));

    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith('/orders/101/status', { status: 'quality_check' }),
    );
    await waitFor(() => expect(jobCalls().length).toBeGreaterThan(callsBefore));
    expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('AU-2026-0001'), 'success');
  });

  it('Weiter on a repair card calls the repair workflow endpoint', async () => {
    serveJobs();
    mockPost.mockResolvedValue({ data: {} });
    await renderBoard();

    await userEvent.click(screen.getByRole('button', { name: 'Weiter: Qualitätskontrolle (REP-2026-0002)' }));

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/repairs/7/quality-check', {}));
  });

  it('shows the backend message when Weiter is refused', async () => {
    serveJobs();
    mockPatch.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409, data: { detail: 'Statuswechsel nicht erlaubt.' } },
    });
    await renderBoard();

    await userEvent.click(screen.getByRole('button', { name: 'Weiter: Bestätigt (AU-2026-0003)' }));

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith('Statuswechsel nicht erlaubt.', 'error'),
    );
  });

  it('offers no Weiter to a VIEWER', async () => {
    mockRole = 'VIEWER';
    serveJobs();
    await renderBoard();
    expect(screen.queryByRole('button', { name: /^Weiter/ })).not.toBeInTheDocument();
  });

  it('moves focus between columns with the arrow keys, Home and End', async () => {
    serveJobs();
    await renderBoard();
    const first = column('Entwurf');
    first.focus();

    fireEvent.keyDown(first, { key: 'ArrowRight' });
    expect(column('Eingang')).toHaveFocus();
    fireEvent.keyDown(column('Eingang'), { key: 'End' });
    expect(column('Pausiert')).toHaveFocus();
    fireEvent.keyDown(column('Pausiert'), { key: 'ArrowLeft' });
    expect(column('Fertig')).toHaveFocus();
    fireEvent.keyDown(column('Fertig'), { key: 'Home' });
    expect(first).toHaveFocus();
  });

  it('refetches the board on a realtime order hint', async () => {
    serveJobs();
    const { client } = await renderBoard();
    const before = jobCalls().length;

    await act(() => invalidateForChannel(client, 'order_updates'));

    await waitFor(() => expect(jobCalls().length).toBe(before + BOARD_COLUMNS.length));
  });
});
