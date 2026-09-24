// ConsentPanel tests — GDPR-02 / GDPR-11 "Einwilligungen" block on the
// customer detail page (W1-05 follow-up).
//
// Pins:
//   (a) a VIEWER never triggers the consent list fetch (CONSENT_MANAGE is
//       ADMIN/GOLDSMITH only — the backend would 403 it) and the panel
//       renders nothing for that role.
//   (b) ADMIN/GOLDSMITH see each consent's purpose/date/method, with a
//       revoke action for active ones.
//   (c) granting a new consent calls consentsApi.grant with the chosen
//       purpose/method and refreshes the list.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockShowToast = vi.fn();
const mockShowConfirm = vi.fn();
const mockUseAuth = vi.fn();
vi.mock('../../contexts', () => ({
  useAuth: () => mockUseAuth(),
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));

const mockList = vi.fn();
const mockGrant = vi.fn();
const mockRevoke = vi.fn();
vi.mock('../../api/consents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/consents')>();
  return {
    ...actual,
    consentsApi: {
      list: (...args: unknown[]) => mockList(...args),
      grant: (...args: unknown[]) => mockGrant(...args),
      revoke: (...args: unknown[]) => mockRevoke(...args),
    },
  };
});

import { ConsentPanel } from './ConsentPanel';

function manageAuth() {
  return { hasRole: () => true };
}

function viewerAuth() {
  return { hasRole: () => false };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('ConsentPanel', () => {
  it('renders nothing and never fetches for a role without CONSENT_MANAGE', () => {
    mockUseAuth.mockReturnValue(viewerAuth());

    const { container } = render(<ConsentPanel customerId={42} />);

    expect(container).toBeEmptyDOMElement();
    expect(mockList).not.toHaveBeenCalled();
  });

  it('lists each consent with its purpose, date and method, and offers revoke for active ones', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockList.mockResolvedValue([
      {
        id: 1,
        customer_id: 42,
        purpose: 'health_data',
        method: 'written',
        granted_at: '2026-08-01T12:00:00Z',
        revoked_at: null,
        note: 'Bogen v1',
      },
    ]);

    render(<ConsentPanel customerId={42} />);

    expect(await screen.findByText('Gesundheitsdaten')).toBeInTheDocument();
    expect(screen.getByText(/Erteilt am/)).toBeInTheDocument();
    expect(screen.getByText(/Schriftlich/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Einwilligung widerrufen' })).toBeInTheDocument();
  });

  it('revokes a consent after confirmation and reloads the list', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockList
      .mockResolvedValueOnce([
        {
          id: 1,
          customer_id: 42,
          purpose: 'health_data',
          method: 'written',
          granted_at: '2026-08-01T12:00:00Z',
          revoked_at: null,
          note: null,
        },
      ])
      .mockResolvedValueOnce([
        {
          id: 1,
          customer_id: 42,
          purpose: 'health_data',
          method: 'written',
          granted_at: '2026-08-01T12:00:00Z',
          revoked_at: '2026-09-25T09:00:00Z',
          note: null,
        },
      ]);
    mockShowConfirm.mockResolvedValue(true);
    mockRevoke.mockResolvedValue({});

    render(<ConsentPanel customerId={42} />);
    await screen.findByRole('button', { name: 'Einwilligung widerrufen' });

    await userEvent.click(screen.getByRole('button', { name: 'Einwilligung widerrufen' }));

    await waitFor(() => expect(mockRevoke).toHaveBeenCalledWith(42, 'health_data'));
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Widerrufen am/)).toBeInTheDocument();
  });

  it('grants a new consent for the selected purpose and method', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockList.mockResolvedValueOnce([]).mockResolvedValueOnce([
      {
        id: 2,
        customer_id: 42,
        purpose: 'marketing',
        method: 'portal',
        granted_at: '2026-09-25T09:00:00Z',
        revoked_at: null,
        note: null,
      },
    ]);
    mockGrant.mockResolvedValue({});

    render(<ConsentPanel customerId={42} />);
    await screen.findByText('Noch keine Einwilligungen erfasst.');

    await userEvent.click(screen.getByRole('button', { name: 'Einwilligung erfassen' }));
    await userEvent.selectOptions(screen.getByLabelText('Zweck'), 'marketing');
    await userEvent.selectOptions(screen.getByLabelText('Methode'), 'portal');
    await userEvent.click(screen.getByRole('button', { name: 'Einwilligung speichern' }));

    await waitFor(() =>
      expect(mockGrant).toHaveBeenCalledWith(42, {
        purpose: 'marketing',
        method: 'portal',
        note: undefined,
      })
    );
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
  });
});
