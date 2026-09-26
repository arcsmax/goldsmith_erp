// RepairDetailPage — playbook detail frame (W4-03).
//
// Pins: the five tabs mirror the order page (Übersicht, Arbeit, Fotos,
// Kunde, Verlauf) with `?tab=` deep links; a VIEWER gets no Fotos tab, no
// status step, no cancel and no prices; the primary action is the next
// status step and its answer lands in the page without a reload.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { RepairJob } from '../types';
import { renderWithQuery } from '../test/queryWrapper';

const mockGetById = vi.fn();
const mockApprove = vi.fn();
const mockCancel = vi.fn();
vi.mock('../api/repairs', () => ({
  repairsApi: {
    getById: (...args: unknown[]) => mockGetById(...args),
    approve: (...args: unknown[]) => mockApprove(...args),
    cancel: (...args: unknown[]) => mockCancel(...args),
  },
  repairPhotoPath: (id: number) => `/repairs/photos/${id}`,
  repairPhotoThumbPath: (id: number) => `/repairs/photos/${id}/thumbnail`,
}));

vi.mock('../components/repairs/RepairCustomerUpdatePanel', () => ({
  RepairCustomerUpdatePanel: () => null,
}));

const mockRole = vi.fn(() => 'GOLDSMITH');
const mockShowToast = vi.fn();
const mockShowConfirm = vi.fn();
vi.mock('../contexts', () => ({
  useAuth: () => ({ user: { role: mockRole() } }),
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));

import { RepairDetailPage } from './RepairDetailPage';

function makeRepair(overrides: Partial<RepairJob> = {}): RepairJob {
  return {
    id: 5,
    repair_number: 'REP-2026-0005',
    bag_number: 'TU-5',
    item_description: 'Ring, Stein lose',
    item_type: 'ring',
    status: 'quoted',
    customer_id: 3,
    customer: { id: 3, first_name: 'Erika', last_name: 'Muster', email: null, phone: '0171 1' },
    is_deleted: false,
    created_at: '2026-09-01T09:00:00Z',
    updated_at: '2026-09-02T09:00:00Z',
    photos: [],
    diagnosis_notes: 'Krappe verbogen',
    estimated_cost: 120,
    actual_cost: null,
    estimated_value: 500,
    ...overrides,
  } as RepairJob;
}

function renderPage(path = '/repairs/5') {
  return renderWithQuery(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/repairs/:id" element={<RepairDetailPage />} />
      </Routes>
    </MemoryRouter>,
    { route: null },
  );
}

async function tabNames(): Promise<string[]> {
  const list = await screen.findByRole('tablist', { name: 'Reparaturbereiche' });
  return within(list)
    .getAllByRole('tab')
    .map((tab) => tab.textContent ?? '');
}

afterEach(() => {
  vi.clearAllMocks();
  mockRole.mockReturnValue('GOLDSMITH');
});

describe('RepairDetailPage — tabs', () => {
  it('shows the five order-page tabs for a goldsmith, Übersicht first', async () => {
    mockGetById.mockResolvedValue(makeRepair());
    renderPage();

    expect(await tabNames()).toEqual(['Übersicht', 'Arbeit', 'Fotos (0)', 'Kunde', 'Verlauf']);
    expect(screen.getByRole('tab', { name: 'Übersicht', selected: true })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'REP-2026-0005' })).toBeInTheDocument();
  });

  it('drops the Fotos tab for a VIEWER', async () => {
    mockRole.mockReturnValue('VIEWER');
    mockGetById.mockResolvedValue(makeRepair());
    renderPage();

    expect(await tabNames()).toEqual(['Übersicht', 'Arbeit', 'Kunde', 'Verlauf']);
  });

  it('opens the tab named in ?tab= and switches panels on click', async () => {
    const user = userEvent.setup();
    mockGetById.mockResolvedValue(makeRepair());
    renderPage('/repairs/5?tab=verlauf');

    const panel = await screen.findByRole('tabpanel');
    expect(within(panel).getByRole('heading', { name: 'Verlauf' })).toBeInTheDocument();
    expect(within(panel).getByText('Eingang')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Arbeit' }));
    expect(within(screen.getByRole('tabpanel')).getByText('Krappe verbogen')).toBeInTheDocument();
    expect(screen.getByText('120,00 €')).toBeInTheDocument();
  });

  it('falls back to Übersicht for ?tab=fotos when the role may not see photos', async () => {
    mockRole.mockReturnValue('VIEWER');
    mockGetById.mockResolvedValue(makeRepair());
    renderPage('/repairs/5?tab=fotos');

    await screen.findByRole('tablist');
    expect(screen.getByRole('tab', { name: 'Übersicht', selected: true })).toBeInTheDocument();
  });

  it('shows the customer on the Kunde tab with a link to the customer', async () => {
    const user = userEvent.setup();
    mockGetById.mockResolvedValue(makeRepair());
    renderPage();

    await user.click(await screen.findByRole('tab', { name: 'Kunde' }));
    const panel = screen.getByRole('tabpanel');
    expect(within(panel).getByText('Erika Muster')).toBeInTheDocument();
    expect(within(panel).getByRole('link', { name: 'Zur Kundin / zum Kunden' })).toHaveAttribute(
      'href',
      '/customers/3',
    );
  });
});

describe('RepairDetailPage — next step and role gates', () => {
  it('offers the next status step and shows the new status from the answer', async () => {
    const user = userEvent.setup();
    mockGetById.mockResolvedValue(makeRepair());
    mockApprove.mockResolvedValue(makeRepair({ status: 'approved' }));
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Angebot bestätigen' }));

    await waitFor(() => expect(mockApprove).toHaveBeenCalledWith(5));
    expect(await screen.findByRole('button', { name: 'Reparatur starten' })).toBeInTheDocument();
    expect(mockShowToast).toHaveBeenCalledWith('Angebot bestätigt', 'success');
  });

  it('cancels only after the confirm dialog says yes', async () => {
    const user = userEvent.setup();
    mockGetById.mockResolvedValue(makeRepair());
    mockShowConfirm.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    mockCancel.mockResolvedValue(makeRepair({ status: 'cancelled' }));
    renderPage();

    const cancel = await screen.findByRole('button', { name: 'Reparatur stornieren' });
    await user.click(cancel);
    expect(mockCancel).not.toHaveBeenCalled();

    await user.click(cancel);
    await waitFor(() => expect(mockCancel).toHaveBeenCalledWith(5));
  });

  it('shows a VIEWER no status step, no cancel and no prices', async () => {
    const user = userEvent.setup();
    mockRole.mockReturnValue('VIEWER');
    mockGetById.mockResolvedValue(makeRepair());
    renderPage();

    await screen.findByRole('tablist');
    expect(screen.queryByRole('button', { name: 'Angebot bestätigen' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reparatur stornieren' })).not.toBeInTheDocument();
    expect(screen.queryByText('Versicherungswert')).not.toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Arbeit' }));
    expect(screen.getByText('Krappe verbogen')).toBeInTheDocument();
    expect(screen.queryByText('120,00 €')).not.toBeInTheDocument();
  });

  it('shows the load error with a retry', async () => {
    const user = userEvent.setup();
    mockGetById.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(makeRepair());
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'REP-2026-0005' })).toBeInTheDocument();
  });
});
