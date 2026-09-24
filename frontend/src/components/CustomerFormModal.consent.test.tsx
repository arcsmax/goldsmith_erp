// CustomerFormModal — health-data consent gate tests (GDPR-02 / GDPR-11,
// W1-05 follow-up).
//
// Backend contract (tests/integration/test_customer_allergy_consent.py):
// allergies are Art. 9 health data and the backend 422s writing them
// unless an active HEALTH_DATA consent exists for the customer
// (POST/DELETE /customers/{id}/consents, method+purpose enums in
// src/goldsmith_erp/models/consent.py).
//
// Pins:
//   (a) the allergies field is disabled until the consent checkbox is
//       confirmed (new customer — no id yet to look up a consent for).
//   (b) editing an existing customer with allergies filled and no active
//       consent yet: submitting grants the consent BEFORE the customer
//       PATCH is sent (never the other way round).
//   (c) an existing active consent is shown (with its grant date/method)
//       and offers "Einwilligung widerrufen", which revokes it and clears
//       the allergies field.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Customer } from '../types';

const mockShowToast = vi.fn();
const mockShowConfirm = vi.fn();
vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));

const mockList = vi.fn();
const mockGrant = vi.fn();
const mockRevoke = vi.fn();
vi.mock('../api/consents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/consents')>();
  return {
    ...actual,
    consentsApi: {
      list: (...args: unknown[]) => mockList(...args),
      grant: (...args: unknown[]) => mockGrant(...args),
      revoke: (...args: unknown[]) => mockRevoke(...args),
    },
  };
});

import { CustomerFormModal } from './CustomerFormModal';

function makeCustomer(overrides: Partial<Customer> = {}): Customer {
  return {
    id: 42,
    first_name: 'Anna',
    last_name: 'Muster',
    email: 'anna@example.com',
    country: 'Deutschland',
    customer_type: 'private',
    tags: [],
    is_active: true,
    created_at: '2026-01-01T10:00:00Z',
    updated_at: '2026-01-01T10:00:00Z',
    ...overrides,
  };
}

const CONSENT_CHECKBOX_LABEL = /Einwilligung .Gesundheitsdaten. liegt vor/;
const REVOKE_BUTTON_LABEL = /Einwilligung widerrufen/;

afterEach(() => {
  vi.clearAllMocks();
});

describe('CustomerFormModal — health-data consent gate', () => {
  it('disables the allergies field until the consent checkbox is confirmed (new customer)', async () => {
    render(<CustomerFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);

    const allergies = screen.getByLabelText('Allergien');
    expect(allergies).toBeDisabled();

    await userEvent.click(screen.getByLabelText(CONSENT_CHECKBOX_LABEL));

    expect(allergies).toBeEnabled();
    // consentsApi.list is never called for a customer that doesn't exist yet.
    expect(mockList).not.toHaveBeenCalled();
  });

  it('grants the health-data consent BEFORE saving the customer when allergies are added', async () => {
    mockList.mockResolvedValue([]);
    mockGrant.mockResolvedValue({
      id: 1,
      customer_id: 42,
      purpose: 'health_data',
      method: 'in_person',
      granted_at: '2026-09-25T09:00:00Z',
      revoked_at: null,
      note: 'Mündlich bestätigt',
    });
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const customer = makeCustomer();

    render(<CustomerFormModal isOpen onClose={vi.fn()} onSubmit={onSubmit} customer={customer} />);
    await waitFor(() => expect(mockList).toHaveBeenCalledWith(42));
    // CustomerFormModal auto-focuses its first field via a 30ms setTimeout
    // (see CustomerStep.test.tsx for the documented flake this avoids) —
    // wait for it to settle before typing so keystrokes can't be misrouted.
    await waitFor(() => expect(screen.getByLabelText(/Vorname/)).toHaveFocus());

    await userEvent.click(await screen.findByLabelText(CONSENT_CHECKBOX_LABEL));
    await userEvent.type(
      screen.getByLabelText(/Nachweis der Einwilligung/),
      'Mündlich bestätigt'
    );
    await userEvent.type(screen.getByLabelText('Allergien'), 'Nickel');

    await userEvent.click(screen.getByRole('button', { name: 'Aktualisieren' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(mockGrant).toHaveBeenCalledWith(42, {
      purpose: 'health_data',
      method: 'in_person',
      note: 'Mündlich bestätigt',
    });
    // Ordering: the consent must be recorded before the customer is saved.
    expect(mockGrant.mock.invocationCallOrder[0]).toBeLessThan(
      onSubmit.mock.invocationCallOrder[0]
    );
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ allergies: 'Nickel' })
    );
  });

  it('blocks submit with a German error when allergies are filled but no consent note was given', async () => {
    mockList.mockResolvedValue([]);
    const onSubmit = vi.fn();
    const customer = makeCustomer();

    render(<CustomerFormModal isOpen onClose={vi.fn()} onSubmit={onSubmit} customer={customer} />);
    await waitFor(() => expect(mockList).toHaveBeenCalledWith(42));
    await waitFor(() => expect(screen.getByLabelText(/Vorname/)).toHaveFocus());

    await userEvent.click(await screen.findByLabelText(CONSENT_CHECKBOX_LABEL));
    await userEvent.type(screen.getByLabelText('Allergien'), 'Nickel');
    await userEvent.click(screen.getByRole('button', { name: 'Aktualisieren' }));

    expect(await screen.findByText(/Nachweis zur Einwilligung/)).toBeInTheDocument();
    expect(mockGrant).not.toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('shows an existing active consent and revokes it, clearing the allergies field', async () => {
    mockList.mockResolvedValueOnce([
      {
        id: 5,
        customer_id: 42,
        purpose: 'health_data',
        method: 'written',
        granted_at: '2026-08-01T12:00:00Z',
        revoked_at: null,
        note: 'Bogen v1',
      },
    ]);
    mockShowConfirm.mockResolvedValue(true);
    mockRevoke.mockResolvedValue({
      id: 5,
      customer_id: 42,
      purpose: 'health_data',
      method: 'written',
      granted_at: '2026-08-01T12:00:00Z',
      revoked_at: '2026-09-25T09:00:00Z',
      note: 'Bogen v1',
    });
    const customer = makeCustomer({ allergies: 'Nickel' });

    render(<CustomerFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} customer={customer} />);

    const allergies = await screen.findByLabelText('Allergien');
    expect(allergies).toBeEnabled();
    expect(screen.getByText(/Einwilligung .Gesundheitsdaten. erteilt am/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: REVOKE_BUTTON_LABEL }));

    await waitFor(() => expect(mockRevoke).toHaveBeenCalledWith(42, 'health_data'));
    expect(mockShowConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ variant: 'danger' })
    );
    await waitFor(() => expect(allergies).toHaveValue(''));
    // The checkbox gate is back — no active consent anymore.
    expect(await screen.findByLabelText(CONSENT_CHECKBOX_LABEL)).not.toBeChecked();
  });
});
