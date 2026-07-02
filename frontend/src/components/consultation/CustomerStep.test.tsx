// CustomerStep — quick-create error-narrowing tests (final-review fix F).
//
// Pins the `catch (err: unknown)` + `axios.isAxiosError` narrowing in
// handleCreateCustomer: FastAPI 422 `detail` is an ARRAY of field errors,
// not a string, so it must never be rendered verbatim (the old
// `err.response?.data?.detail || fallback` fell back to the array's
// stringified/"[object Object]" form only by accident — this test proves
// the typeof-string guard now does it deliberately). A genuine string
// detail (e.g. a 409 duplicate-customer message) still passes through.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockCreate = vi.fn();
vi.mock('../../api/customers', () => ({
  customersApi: {
    create: (...a: unknown[]) => mockCreate(...a),
    search: vi.fn().mockResolvedValue([]),
    getById: vi.fn(),
  },
}));

vi.mock('../../api/consultations', () => ({
  consultationsApi: { create: vi.fn() },
}));

const mockShowToast = vi.fn();
vi.mock('../../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}));

import { CustomerStep } from './CustomerStep';

beforeEach(() => {
  vi.clearAllMocks();
});

async function openModalAndFillRequiredFields() {
  await userEvent.click(screen.getByRole('button', { name: '+ Neue Kundin' }));
  await userEvent.type(screen.getByLabelText(/Vorname/), 'Anna');
  await userEvent.type(screen.getByLabelText(/Nachname/), 'Muster');
  await userEvent.type(screen.getByLabelText(/E-Mail/), 'anna@example.com');
}

describe('CustomerStep — quick-create error narrowing', () => {
  it('falls back to the generic German message when the 422 detail is an array (FastAPI shape)', async () => {
    mockCreate.mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 422,
        data: { detail: [{ msg: 'field required', loc: ['body', 'email'] }] },
      },
    });

    render(<CustomerStep onDraftCreated={vi.fn()} />);
    await openModalAndFillRequiredFields();
    await userEvent.click(screen.getByRole('button', { name: 'Erstellen' }));

    expect(await screen.findByText('Fehler beim Erstellen der Kundin')).toBeInTheDocument();
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument();
  });

  it('surfaces a genuine string detail from the backend verbatim (e.g. a duplicate-customer 409)', async () => {
    mockCreate.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409, data: { detail: 'E-Mail bereits vergeben' } },
    });

    render(<CustomerStep onDraftCreated={vi.fn()} />);
    await openModalAndFillRequiredFields();
    await userEvent.click(screen.getByRole('button', { name: 'Erstellen' }));

    expect(await screen.findByText('E-Mail bereits vergeben')).toBeInTheDocument();
  });

  it('falls back to the generic German message for a non-axios error', async () => {
    mockCreate.mockRejectedValue(new Error('boom'));

    render(<CustomerStep onDraftCreated={vi.fn()} />);
    await openModalAndFillRequiredFields();
    await userEvent.click(screen.getByRole('button', { name: 'Erstellen' }));

    expect(await screen.findByText('Fehler beim Erstellen der Kundin')).toBeInTheDocument();
  });
});
