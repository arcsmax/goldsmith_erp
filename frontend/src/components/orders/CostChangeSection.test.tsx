// CostChangeSection tests — V1.2 Task 5.
//
// Pins:
//   (a) history renders returned cost-changes newest-first with status
//       badges + netto amounts.
//   (b) creating a cost change (via the real CostChangeForm) calls
//       createCostChange with the parsed input, then refreshes history and
//       fires onChanged.
//   (c) "Antwort erfassen" on a `sent` row opens the record-response modal
//       and submits recordCostChangeResponse with the chosen
//       status/method/evidence, then fires onChanged.
//   (d) a `draft` row's "Senden" confirms via showConfirm, then calls
//       sendCostChange and shows the honest delivered/PDF toast.
//   (e) write actions are hidden AND listCostChanges is never called for a
//       VIEWER (COST_CHANGE_VIEW 403s backend-side for that role).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { CostChange } from '../../api/customer-updates';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockListCostChanges = vi.fn();
const mockCreateCostChange = vi.fn();
const mockSendCostChange = vi.fn();
const mockRecordCostChangeResponse = vi.fn();

vi.mock('../../api/customer-updates', () => ({
  customerUpdatesApi: {
    listCostChanges: (...args: unknown[]) => mockListCostChanges(...args),
    createCostChange: (...args: unknown[]) => mockCreateCostChange(...args),
    sendCostChange: (...args: unknown[]) => mockSendCostChange(...args),
    recordCostChangeResponse: (...args: unknown[]) => mockRecordCostChangeResponse(...args),
  },
}));

const mockLogError = vi.fn();
vi.mock('../../lib/logError', () => ({
  logError: (...args: unknown[]) => mockLogError(...args),
}));

const mockShowToast = vi.fn();
const mockShowConfirm = vi.fn();
const mockUseAuth = vi.fn();
vi.mock('../../contexts', () => ({
  useAuth: () => mockUseAuth(),
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));

import { CostChangeSection } from './CostChangeSection';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeCostChange(overrides: Partial<CostChange> = {}): CostChange {
  return {
    id: 1,
    order_id: 1,
    quote_id: 9,
    original_amount: 1000,
    new_amount: 1200,
    delta_percent: 20,
    reason: 'Zusätzlicher Steinbesatz gewünscht.',
    line_items: [],
    status: 'draft',
    response_method: null,
    response_evidence: null,
    responded_at: null,
    recorded_by: null,
    created_at: '2026-07-01T10:00:00Z',
    created_by: 1,
    updated_at: '2026-07-01T10:00:00Z',
    ...overrides,
  };
}

function manageAuth() {
  return { hasRole: () => true };
}

function viewerAuth() {
  return { hasRole: () => false };
}

afterEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CostChangeSection', () => {
  it('renders history newest-first with status badges and netto amounts', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListCostChanges.mockResolvedValue([
      makeCostChange({
        id: 1,
        status: 'approved',
        reason: 'Älterer Eintrag',
        created_at: '2026-06-01T10:00:00Z',
      }),
      makeCostChange({
        id: 2,
        status: 'declined',
        reason: 'Neuerer Eintrag',
        created_at: '2026-07-01T10:00:00Z',
      }),
    ]);

    render(<CostChangeSection orderId={5} />);

    const items = await screen.findAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText('Neuerer Eintrag')).toBeInTheDocument();
    expect(within(items[0]).getByText('Abgelehnt')).toBeInTheDocument();
    expect(within(items[1]).getByText('Älterer Eintrag')).toBeInTheDocument();
    expect(within(items[1]).getByText('Genehmigt')).toBeInTheDocument();
    expect(mockListCostChanges).toHaveBeenCalledWith(5);
  });

  it('creating a cost change calls createCostChange then refreshes history and fires onChanged', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListCostChanges.mockResolvedValueOnce([]).mockResolvedValueOnce([
      makeCostChange({ id: 10, status: 'draft' }),
    ]);
    mockCreateCostChange.mockResolvedValue(makeCostChange({ id: 10, status: 'draft' }));
    const onChanged = vi.fn();

    render(<CostChangeSection orderId={7} onChanged={onChanged} />);
    await waitFor(() => expect(mockListCostChanges).toHaveBeenCalledWith(7));

    await userEvent.type(screen.getByLabelText(/Neuer Betrag/), '1200');
    await userEvent.type(
      screen.getByLabelText(/Begründung/),
      'Zusätzlicher Steinbesatz wurde vom Kunden gewünscht.'
    );
    await userEvent.click(screen.getByRole('button', { name: 'Kostenänderung anlegen' }));

    await waitFor(() =>
      expect(mockCreateCostChange).toHaveBeenCalledWith(7, {
        new_amount: 1200,
        reason: 'Zusätzlicher Steinbesatz wurde vom Kunden gewünscht.',
        line_items: [],
      })
    );
    await waitFor(() => expect(mockListCostChanges).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it('surfaces the backend\'s specific error detail (not the generic text) when create is rejected', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListCostChanges.mockResolvedValue([]);
    mockCreateCostChange.mockRejectedValue({
      response: { data: { detail: 'Kein Kostenvoranschlag' } },
    });

    render(<CostChangeSection orderId={8} />);
    await waitFor(() => expect(mockListCostChanges).toHaveBeenCalledWith(8));

    await userEvent.type(screen.getByLabelText(/Neuer Betrag/), '1200');
    await userEvent.type(
      screen.getByLabelText(/Begründung/),
      'Zusätzlicher Steinbesatz wurde vom Kunden gewünscht.'
    );
    await userEvent.click(screen.getByRole('button', { name: 'Kostenänderung anlegen' }));

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        expect.stringContaining('Kein Kostenvoranschlag'),
        'error'
      )
    );
    expect(mockShowToast).not.toHaveBeenCalledWith(
      'Kostenänderung konnte nicht angelegt werden.',
      'error'
    );
  });

  it('"Antwort erfassen" on a sent row submits recordCostChangeResponse with the chosen status/method/evidence and fires onChanged', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    const sentChange = makeCostChange({ id: 42, status: 'sent' });
    mockListCostChanges.mockResolvedValue([sentChange]);
    mockRecordCostChangeResponse.mockResolvedValue(
      makeCostChange({ id: 42, status: 'declined' })
    );
    const onChanged = vi.fn();

    render(<CostChangeSection orderId={3} onChanged={onChanged} />);

    const item = (await screen.findAllByRole('listitem'))[0];
    await userEvent.click(within(item).getByRole('button', { name: 'Antwort erfassen' }));

    const dialog = await screen.findByRole('dialog');
    await userEvent.selectOptions(
      within(dialog).getByLabelText('Antwort des Kunden'),
      'declined'
    );
    await userEvent.selectOptions(
      within(dialog).getByLabelText('Art der Rückmeldung'),
      'phone'
    );
    await userEvent.type(
      within(dialog).getByLabelText('Nachweis / Notiz'),
      'Kunde hat telefonisch abgelehnt.'
    );
    await userEvent.click(within(dialog).getByRole('button', { name: 'Antwort speichern' }));

    await waitFor(() =>
      expect(mockRecordCostChangeResponse).toHaveBeenCalledWith(42, {
        status: 'declined',
        response_method: 'phone',
        response_evidence: 'Kunde hat telefonisch abgelehnt.',
      })
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes the record-response modal when Escape is pressed', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    const sentChange = makeCostChange({ id: 43, status: 'sent' });
    mockListCostChanges.mockResolvedValue([sentChange]);

    render(<CostChangeSection orderId={3} />);

    const item = (await screen.findAllByRole('listitem'))[0];
    await userEvent.click(within(item).getByRole('button', { name: 'Antwort erfassen' }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(mockRecordCostChangeResponse).not.toHaveBeenCalled();
  });

  it('"Senden" on a draft row confirms, sends, and shows the honest delivered toast', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    const draftChange = makeCostChange({ id: 55, status: 'draft' });
    mockListCostChanges.mockResolvedValue([draftChange]);
    mockShowConfirm.mockResolvedValue(true);
    mockSendCostChange.mockResolvedValue({
      update: {},
      delivered: true,
      method: 'email',
    });

    render(<CostChangeSection orderId={4} />);

    const item = (await screen.findAllByRole('listitem'))[0];
    await userEvent.click(within(item).getByRole('button', { name: 'Senden' }));

    await waitFor(() => expect(mockShowConfirm).toHaveBeenCalled());
    await waitFor(() => expect(mockSendCostChange).toHaveBeenCalledWith(55));
    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('versendet'), 'success')
    );
  });

  it('never sends when the send confirmation is declined', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    const draftChange = makeCostChange({ id: 56, status: 'draft' });
    mockListCostChanges.mockResolvedValue([draftChange]);
    mockShowConfirm.mockResolvedValue(false);

    render(<CostChangeSection orderId={4} />);

    const item = (await screen.findAllByRole('listitem'))[0];
    await userEvent.click(within(item).getByRole('button', { name: 'Senden' }));

    await waitFor(() => expect(mockShowConfirm).toHaveBeenCalled());
    expect(mockSendCostChange).not.toHaveBeenCalled();
  });

  it('hides write actions and never calls listCostChanges for a VIEWER', async () => {
    mockUseAuth.mockReturnValue(viewerAuth());

    render(<CostChangeSection orderId={11} />);

    expect(screen.getByText(/Keine Berechtigung/)).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Kostenänderung anlegen' })
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Neuer Betrag/)).not.toBeInTheDocument();
    expect(mockListCostChanges).not.toHaveBeenCalled();
  });
});
