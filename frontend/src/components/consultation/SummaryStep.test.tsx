// SummaryStep — Beratungs-Wizard step 7 tests.
//
// Pins four behaviors from the Task 8 brief:
//   (a) renders the wishes text verbatim + the formatted de-DE budget range.
//   (b) "Auftrag anlegen": confirm -> convert(id, 'order') -> navigate to the
//       returned converted_order_id.
//   (c) a 409 on convert (already converted) toasts "Bereits konvertiert"
//       and navigates to the existing order from err.response.data.detail.
//   (d) status === 'converted' renders the read-only banner and no action
//       buttons.
//
// react-router-dom's useNavigate is mocked via the async-orig pattern (see
// src/test/ScannerPageV2.test.tsx) — no MemoryRouter needed since the whole
// module is replaced and SummaryStep only calls useNavigate().
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Consultation, ConsultationUpdateInput } from '../../types';

const mocks = vi.hoisted(() => ({ navigate: vi.fn() }));

vi.mock('react-router-dom', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

const mockConvert = vi.fn();
vi.mock('../../api/consultations', () => ({
  consultationsApi: {
    convert: (...a: unknown[]) => mockConvert(...a),
  },
  consultationPhotoThumbPath: (photoId: string) => `/consultations/photos/${photoId}/thumbnail`,
}));

const mockGetById = vi.fn();
const mockGetNoGos = vi.fn();
vi.mock('../../api/customers', () => ({
  customersApi: {
    getById: (...a: unknown[]) => mockGetById(...a),
    getNoGos: (...a: unknown[]) => mockGetNoGos(...a),
  },
}));

const mockShowToast = vi.fn();
const mockShowConfirm = vi.fn();
vi.mock('../../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));

vi.mock('../AuthenticatedImage', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => <img src={src} alt={alt} />,
}));

import { SummaryStep, formatBudgetRange } from './SummaryStep';

// Intl.NumberFormat('de-DE', {style: 'currency', ...}) inserts a NBSP
// (U+00A0) between the amount and "€". @testing-library/dom's default
// text matcher normalizes the DOM's text content (NBSP -> regular space)
// before comparing, but does NOT normalize a plain-string matcher passed to
// getByText — so an un-normalized query with the raw NBSP never matches.
// Collapse whitespace on the expected string the same way before querying.
const normalizeWs = (s: string) => s.replace(/\s+/g, ' ').trim();

function makeConsultation(overrides: Partial<Consultation> = {}): Consultation {
  return {
    id: 9,
    customer_id: 5,
    conducted_by: 1,
    status: 'draft',
    occasion: 'wedding',
    occasion_date: null,
    budget_min: null,
    budget_max: null,
    piece_type: null,
    wishes: null,
    materials_discussed: null,
    source_material: null,
    notes: null,
    follow_up_at: null,
    converted_quote_id: null,
    converted_order_id: null,
    photos: [],
    created_at: '2026-07-02T10:00:00',
    updated_at: '2026-07-02T10:00:00',
    ...overrides,
  };
}

const noopPatch = vi.fn(async () => true);
const noopRefresh = vi.fn(async () => undefined);

const renderStep = (consultation: Consultation) =>
  render(<SummaryStep consultation={consultation} onPatch={noopPatch} refresh={noopRefresh} />);

beforeEach(() => {
  vi.clearAllMocks();
  mockGetById.mockResolvedValue({ id: 5, first_name: 'Anna', last_name: 'Muster' });
  mockGetNoGos.mockResolvedValue([]);
  mockShowConfirm.mockResolvedValue(true);
});

describe('SummaryStep', () => {
  it('renders the wishes text and the formatted de-DE budget range', async () => {
    const consultation = makeConsultation({
      wishes: 'Ein schlichter Ring mit kleinem Diamanten',
      budget_min: 800,
      budget_max: 1500,
    });
    renderStep(consultation);

    await waitFor(() => expect(mockGetById).toHaveBeenCalledWith(5));
    expect(
      screen.getByText('Ein schlichter Ring mit kleinem Diamanten')
    ).toBeInTheDocument();
    expect(
      screen.getByText(normalizeWs(formatBudgetRange(800, 1500) as string))
    ).toBeInTheDocument();
  });

  it('"Auftrag anlegen": confirm -> convert(id, order) -> navigate to the returned order id', async () => {
    mockConvert.mockResolvedValue({ ...makeConsultation(), converted_order_id: 77 });
    renderStep(makeConsultation());
    await waitFor(() => expect(mockGetById).toHaveBeenCalled());

    await userEvent.click(screen.getByRole('button', { name: 'Auftrag anlegen' }));

    await waitFor(() => expect(mockConvert).toHaveBeenCalledWith(9, 'order'));
    expect(mocks.navigate).toHaveBeenCalledWith('/orders/77');
  });

  it('"Auftrag anlegen": falls back to /orders when the response has no converted_order_id', async () => {
    mockConvert.mockResolvedValue({ ...makeConsultation(), converted_order_id: null });
    renderStep(makeConsultation());
    await waitFor(() => expect(mockGetById).toHaveBeenCalled());

    await userEvent.click(screen.getByRole('button', { name: 'Auftrag anlegen' }));

    await waitFor(() => expect(mockConvert).toHaveBeenCalledWith(9, 'order'));
    expect(mocks.navigate).toHaveBeenCalledWith('/orders');
  });

  it('409 on convert toasts "Bereits konvertiert" and navigates to the existing order', async () => {
    mockConvert.mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 409,
        data: { detail: { message: 'Beratung wurde bereits konvertiert', order_id: 55, quote_id: null } },
      },
    });
    renderStep(makeConsultation());
    await waitFor(() => expect(mockGetById).toHaveBeenCalled());

    await userEvent.click(screen.getByRole('button', { name: 'Auftrag anlegen' }));

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith('Bereits konvertiert', 'error')
    );
    expect(mocks.navigate).toHaveBeenCalledWith('/orders/55');
  });

  it('saves follow_up_at as local noon so the calendar date survives a negative-UTC-offset read (e.g. -05:00)', async () => {
    const patchSpy = vi.fn(async (_fields: ConsultationUpdateInput) => true);
    render(<SummaryStep consultation={makeConsultation()} onPatch={patchSpy} refresh={noopRefresh} />);
    await waitFor(() => expect(mockGetById).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText('Neue Wiedervorlage'), {
      target: { value: '2026-07-10' },
    });
    await userEvent.click(screen.getByRole('button', { name: 'Speichern & abschließen' }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
    const [sentFields] = patchSpy.mock.calls[0];
    const sentIso = sentFields.follow_up_at as string;

    // A date-only string parses as UTC midnight (the pre-fix bug) — reading
    // that back in any negative-UTC-offset zone rolls to the previous day.
    // Assert the goldsmith's chosen date (10.07.2026) survives regardless.
    const formatted = new Intl.DateTimeFormat('de-DE', { timeZone: 'America/Bogota' }).format(
      new Date(sentIso)
    );
    expect(formatted).toBe('10.7.2026');
  });

  it('status "converted" renders the read-only banner and no action buttons', async () => {
    const consultation = makeConsultation({ status: 'converted', converted_order_id: 42 });
    renderStep(consultation);

    expect(
      await screen.findByText('Diese Beratung wurde bereits überführt.')
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Kostenvoranschlag erstellen' })
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Auftrag anlegen' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Archivieren' })).not.toBeInTheDocument();
  });
});
