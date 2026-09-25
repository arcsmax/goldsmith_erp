// HandoffTab (W4-03): queries, wire values and accept for the addressee.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../../test/queryWrapper';

const mockGetForOrder = vi.fn();
const mockCreate = vi.fn();
const mockAccept = vi.fn();
vi.mock('../../api/handoffs', () => ({
  handoffsApi: {
    getForOrder: (...a: unknown[]) => mockGetForOrder(...a),
    create: (...a: unknown[]) => mockCreate(...a),
    accept: (...a: unknown[]) => mockAccept(...a),
    decline: vi.fn(),
  },
}));
vi.mock('../../api', () => ({
  usersApi: {
    getAll: () =>
      Promise.resolve([
        { id: 1, first_name: 'Anne', last_name: 'Meister', email: 'a@x.de', role: 'admin' },
        { id: 2, first_name: 'Klaus', last_name: 'Huber', email: 'k@x.de', role: 'goldsmith' },
      ]),
  },
}));
const mockShowToast = vi.fn();
vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { id: 1 } }),
  useToast: () => ({ showToast: mockShowToast }),
}));

import HandoffTab from './HandoffTab';

const pendingForMe = {
  id: 7,
  order_id: 5,
  from_user_id: 2,
  to_user_id: 1,
  from_user: { id: 2, first_name: 'Klaus', last_name: 'Huber' },
  to_user: { id: 1, first_name: 'Anne', last_name: 'Meister' },
  handoff_type: 'request_review',
  status: 'pending',
  notes: null,
  response_notes: null,
  created_at: '2026-09-20T10:00:00Z',
  responded_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGetForOrder.mockResolvedValue({ data: [pendingForMe] });
  mockCreate.mockResolvedValue({ data: {} });
  mockAccept.mockResolvedValue({ data: {} });
});

describe('HandoffTab', () => {
  it('shows the handoff with names, type label and status badge, and accepts it', async () => {
    renderWithQuery(<HandoffTab orderId={5} />);

    expect(await screen.findByText('Klaus Huber → Anne Meister')).toBeInTheDocument();
    expect(screen.getByText('Prüfung anfordern', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByText('Offen')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Übergabe annehmen' }));
    expect(mockAccept).toHaveBeenCalledWith(7);
    expect(mockGetForOrder).toHaveBeenCalledTimes(2);
  });

  it('creates a handoff with the backend wire value and excludes the current user', async () => {
    mockGetForOrder.mockResolvedValue({ data: [] });
    renderWithQuery(<HandoffTab orderId={5} />);

    expect(await screen.findByText('Noch keine Übergaben für diesen Auftrag.')).toBeInTheDocument();
    const recipient = screen.getByLabelText(/Empfänger/);
    await screen.findByRole('option', { name: 'Klaus Huber (goldsmith)' });
    expect(screen.queryByRole('option', { name: /Anne Meister/ })).not.toBeInTheDocument();

    await userEvent.selectOptions(recipient, '2');
    await userEvent.click(screen.getByRole('button', { name: 'Übergabe erstellen' }));
    expect(mockCreate).toHaveBeenCalledWith(5, {
      to_user_id: 2,
      handoff_type: 'pass_to_next',
      notes: undefined,
    });
    expect(mockShowToast).toHaveBeenCalledWith('Übergabe erstellt', 'success');
  });
});
