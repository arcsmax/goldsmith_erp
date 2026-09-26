// CustomerFormModal — email is optional (W2-10, DOM-02, decision D-11).
//
// Backend contract (tests/integration/test_customer_without_email.py):
// a customer needs at least one of email / phone / mobile; email is unique
// only when present; PATCH {"email": null} removes the address.
//
// Pins:
//   (a) a phone-only customer can be created; the payload carries no email.
//   (b) with neither email nor phone/mobile the form refuses with a German
//       message and never calls onSubmit.
//   (c) the email label no longer marks the field as required.
//   (d) clearing the email of an existing customer sends email: null.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Customer } from '../types';

vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: vi.fn() }),
  useConfirm: () => ({ showConfirm: vi.fn() }),
}));

const mockList = vi.fn().mockResolvedValue([]);
vi.mock('../api/consents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/consents')>();
  return {
    ...actual,
    consentsApi: {
      list: (...args: unknown[]) => mockList(...args),
      grant: vi.fn(),
      revoke: vi.fn(),
    },
  };
});

import { CustomerFormModal } from './CustomerFormModal';

afterEach(() => {
  vi.clearAllMocks();
});

async function fillNames() {
  await waitFor(() => expect(screen.getByLabelText(/Vorname/)).toHaveFocus());
  await userEvent.type(screen.getByLabelText(/Vorname/), 'Erika');
  await userEvent.type(screen.getByLabelText(/Nachname/), 'Laufkundin');
}

describe('CustomerFormModal — email optional', () => {
  it('creates a phone-only customer without an email in the payload', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<CustomerFormModal isOpen onClose={vi.fn()} onSubmit={onSubmit} />);

    await fillNames();
    await userEvent.type(screen.getByLabelText('Telefon'), '+49 89 123456');
    await userEvent.click(screen.getByRole('button', { name: 'Erstellen' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0];
    expect(payload).not.toHaveProperty('email');
    expect(payload.phone).toBe('+49 89 123456');
  });

  it('refuses a customer without any contact channel', async () => {
    const onSubmit = vi.fn();
    render(<CustomerFormModal isOpen onClose={vi.fn()} onSubmit={onSubmit} />);

    await fillNames();
    await userEvent.click(screen.getByRole('button', { name: 'Erstellen' }));

    expect(
      await screen.findByText(/E-Mail, Telefon oder Mobil/)
    ).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('does not mark the email field as required', () => {
    render(<CustomerFormModal isOpen onClose={vi.fn()} onSubmit={vi.fn()} />);

    const label = screen.getByText(/^E-Mail/, { selector: 'label' });
    expect(label.querySelector('.required')).toBeNull();
  });

  it('sends email: null when the email of an existing customer is cleared', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const customer: Customer = {
      id: 7,
      first_name: 'Anna',
      last_name: 'Muster',
      email: 'anna@example.com',
      phone: '+49 30 1',
      country: 'Deutschland',
      customer_type: 'private',
      tags: [],
      is_active: true,
      created_at: '2026-01-01T10:00:00Z',
      updated_at: '2026-01-01T10:00:00Z',
    };
    render(
      <CustomerFormModal isOpen onClose={vi.fn()} onSubmit={onSubmit} customer={customer} />
    );
    await waitFor(() => expect(screen.getByLabelText(/Vorname/)).toHaveFocus());

    await userEvent.clear(screen.getByLabelText(/E-Mail/));
    await userEvent.click(screen.getByRole('button', { name: 'Aktualisieren' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].email).toBeNull();
  });
});
