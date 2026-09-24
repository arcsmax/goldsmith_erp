// RepairCustomerUpdatePanel tests (DOM-12 / W2-02):
//   (a) hidden entirely before the repair can have a draft (status not yet
//       ready/picked_up) — no network call either.
//   (b) shows the draft + "Kunde benachrichtigen" button once one exists.
//   (c) clicking the button sends it, shows a success toast, and asks the
//       parent to refetch the repair (customer_notified_at truthfulness
//       lives server-side — this panel never guesses it).
//   (d) a non-delivered send (SMTP unset) shows an error toast but still
//       does not crash and still refetches.
//   (e) once sent, shows the sent timestamp instead of the button.
//
// api/customer-updates is mocked BEFORE the component import so no network
// is needed — mirrors IntakeChecklist.test.tsx's mocking convention.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { RepairJob } from '../../types';
import type { CustomerUpdate } from '../../api/customer-updates';

const mockListRepairUpdates = vi.fn();
const mockSendRepairUpdate = vi.fn();

vi.mock('../../api/customer-updates', () => ({
  customerUpdatesApi: {
    listRepairUpdates: (...a: unknown[]) => mockListRepairUpdates(...a),
    sendRepairUpdate: (...a: unknown[]) => mockSendRepairUpdate(...a),
  },
}));

const mockShowToast = vi.fn();
vi.mock('../../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}));

import { RepairCustomerUpdatePanel } from './RepairCustomerUpdatePanel';

function makeRepair(overrides: Partial<RepairJob> = {}): RepairJob {
  return {
    id: 9,
    repair_number: 'REP-2026-0009',
    bag_number: 'T-009',
    customer_id: 3,
    customer: { id: 3, first_name: 'Anna', last_name: 'Kundin', email: 'anna@example.com' },
    received_by: null,
    item_description: 'Kette',
    item_type: 'chain',
    metal_type: null,
    estimated_value: null,
    status: 'ready',
    diagnosis_notes: null,
    estimated_cost: null,
    actual_cost: 35,
    estimated_completion_date: null,
    actual_completion_date: '2026-09-20T10:00:00',
    customer_notified_at: null,
    picked_up_at: null,
    is_deleted: false,
    created_at: '2026-09-18T10:00:00',
    updated_at: '2026-09-20T10:00:00',
    photos: [],
    intake_checklist: null,
    ...overrides,
  };
}

function makeUpdate(overrides: Partial<CustomerUpdate> = {}): CustomerUpdate {
  return {
    id: 55,
    order_id: null,
    repair_job_id: 9,
    kind: 'ready_for_pickup',
    subject: 'Ihr Schmuckstueck ist fertig zur Abholung — Auftrag #9',
    body: 'Ihr Schmuckstueck ist fertig und kann abgeholt werden.',
    photo_ids: [],
    cost_change_request_id: null,
    token: 'tok-55',
    status: 'draft',
    sent_at: null,
    sent_by: 1,
    delivery_method: null,
    created_at: '2026-09-20T10:05:00',
    updated_at: '2026-09-20T10:05:00',
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('RepairCustomerUpdatePanel', () => {
  it('renders nothing and makes no request before the repair can have a draft', () => {
    const repair = makeRepair({ status: 'in_repair' });
    const { container } = render(
      <RepairCustomerUpdatePanel repair={repair} onRepairRefresh={vi.fn()} />
    );

    expect(container).toBeEmptyDOMElement();
    expect(mockListRepairUpdates).not.toHaveBeenCalled();
  });

  it('shows the draft and a "Kunde benachrichtigen" button once one exists', async () => {
    mockListRepairUpdates.mockResolvedValue([makeUpdate()]);
    const repair = makeRepair({ status: 'ready' });

    render(<RepairCustomerUpdatePanel repair={repair} onRepairRefresh={vi.fn()} />);

    await waitFor(() => expect(mockListRepairUpdates).toHaveBeenCalledWith(9));
    expect(await screen.findByText(/fertig zur Abholung/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Kunde benachrichtigen' })).toBeInTheDocument();
  });

  it('sends the draft, shows a success toast, and asks the parent to refetch', async () => {
    const draft = makeUpdate();
    mockListRepairUpdates.mockResolvedValue([draft]);
    const sentUpdate = makeUpdate({
      status: 'sent',
      sent_at: '2026-09-25T09:00:00',
      delivery_method: 'email',
    });
    mockSendRepairUpdate.mockResolvedValue({
      update: sentUpdate,
      delivered: true,
      method: 'email',
    });
    const onRepairRefresh = vi.fn();
    const repair = makeRepair({ status: 'ready' });

    render(<RepairCustomerUpdatePanel repair={repair} onRepairRefresh={onRepairRefresh} />);

    const button = await screen.findByRole('button', { name: 'Kunde benachrichtigen' });
    await userEvent.click(button);

    await waitFor(() => expect(mockSendRepairUpdate).toHaveBeenCalledWith(9));
    expect(mockShowToast).toHaveBeenCalledWith('Kunde wurde benachrichtigt', 'success');
    expect(onRepairRefresh).toHaveBeenCalledTimes(1);

    // Re-renders from the send RESULT immediately (no need to wait for the
    // parent's refetch) — button is replaced by the sent confirmation.
    expect(await screen.findByText(/Verschickt am/)).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Kunde benachrichtigen' })
    ).not.toBeInTheDocument();
  });

  it('shows an error toast (not a crash) when the send is not delivered', async () => {
    mockListRepairUpdates.mockResolvedValue([makeUpdate()]);
    mockSendRepairUpdate.mockResolvedValue({
      update: makeUpdate({ status: 'send_failed' }),
      delivered: false,
      method: null,
    });
    const onRepairRefresh = vi.fn();
    const repair = makeRepair({ status: 'ready' });

    render(<RepairCustomerUpdatePanel repair={repair} onRepairRefresh={onRepairRefresh} />);

    const button = await screen.findByRole('button', { name: 'Kunde benachrichtigen' });
    await userEvent.click(button);

    await waitFor(() => expect(mockShowToast).toHaveBeenCalledWith(expect.any(String), 'error'));
    expect(onRepairRefresh).toHaveBeenCalledTimes(1);
  });

  it('shows the sent timestamp instead of a button once already sent', async () => {
    mockListRepairUpdates.mockResolvedValue([
      makeUpdate({ status: 'sent', sent_at: '2026-09-21T08:30:00', delivery_method: 'email' }),
    ]);
    const repair = makeRepair({ status: 'picked_up' });

    render(<RepairCustomerUpdatePanel repair={repair} onRepairRefresh={vi.fn()} />);

    expect(await screen.findByText(/Verschickt am/)).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Kunde benachrichtigen' })
    ).not.toBeInTheDocument();
  });
});
