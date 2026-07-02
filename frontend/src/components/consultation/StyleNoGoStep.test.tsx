// StyleNoGoStep — Beratungs-Wizard step 4 tests.
//
// Pins four behaviors from the Task 5 brief:
//   (a) renders loaded no-gos and style chips.
//   (b) the "Nickel" quick-allergy chip posts {category:'allergy', value:'Nickel'}
//       and appends the returned row.
//   (c) a 409 from addNoGo shows the duplicate toast and does NOT append.
//   (d) adding style word "schlicht" PATCHes {style_words: ['schlicht']}
//       (existing + new).
//
// Both api/customers and contexts are mocked BEFORE the component import so
// no network or provider tree is needed.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Consultation, NoGo, StyleProfile } from '../../types';

const mockGetNoGos = vi.fn();
const mockAddNoGo = vi.fn();
const mockDeleteNoGo = vi.fn();
const mockGetStyleProfile = vi.fn();
const mockUpdateStyleProfile = vi.fn();

vi.mock('../../api/customers', () => ({
  customersApi: {
    getNoGos: (...a: unknown[]) => mockGetNoGos(...a),
    addNoGo: (...a: unknown[]) => mockAddNoGo(...a),
    deleteNoGo: (...a: unknown[]) => mockDeleteNoGo(...a),
    getStyleProfile: (...a: unknown[]) => mockGetStyleProfile(...a),
    updateStyleProfile: (...a: unknown[]) => mockUpdateStyleProfile(...a),
  },
}));

const mockShowToast = vi.fn();
const mockShowConfirm = vi.fn();
vi.mock('../../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: mockShowConfirm }),
}));

import { StyleNoGoStep } from './StyleNoGoStep';

const EMPTY_PROFILE: StyleProfile = {
  metal_tones: [],
  finishes: [],
  stone_preferences: [],
  style_words: [],
};

function makeConsultation(overrides: Partial<Consultation> = {}): Consultation {
  return {
    id: 1,
    customer_id: 5,
    conducted_by: 1,
    status: 'draft',
    occasion: 'other',
    photos: [],
    created_at: '2026-07-02T10:00:00',
    updated_at: '2026-07-02T10:00:00',
    ...overrides,
  };
}

const noopPatch = vi.fn(async () => true);
const noopRefresh = vi.fn(async () => undefined);

const renderStep = () =>
  render(<StyleNoGoStep consultation={makeConsultation()} onPatch={noopPatch} refresh={noopRefresh} />);

beforeEach(() => {
  vi.clearAllMocks();
  mockGetNoGos.mockResolvedValue([]);
  mockGetStyleProfile.mockResolvedValue(EMPTY_PROFILE);
});

describe('StyleNoGoStep', () => {
  it('renders loaded no-gos and style chips', async () => {
    const noGo: NoGo = {
      id: 1,
      customer_id: 5,
      category: 'allergy',
      value: 'Nickel',
      note: null,
      source_consultation_id: null,
      created_at: '2026-07-02T10:00:00',
    };
    mockGetNoGos.mockResolvedValue([noGo]);
    mockGetStyleProfile.mockResolvedValue({
      metal_tones: ['Gelbgold'],
      finishes: [],
      stone_preferences: [],
      style_words: ['schlicht'],
    });

    renderStep();

    // "Nickel" also appears in the quick-allergy chip row, so scope to the
    // loaded no-go entry's own delete button instead of the ambiguous text.
    expect(await screen.findByLabelText('Nickel löschen')).toBeInTheDocument();
    expect(screen.getByText('Gelbgold')).toBeInTheDocument();
    expect(screen.getByText('schlicht')).toBeInTheDocument();
  });

  it('quick-allergy chip "Nickel" posts {category: allergy, value: Nickel} and appends the row', async () => {
    const created: NoGo = {
      id: 2,
      customer_id: 5,
      category: 'allergy',
      value: 'Nickel',
      note: null,
      source_consultation_id: null,
      created_at: '2026-07-02T10:00:00',
    };
    mockAddNoGo.mockResolvedValue(created);
    renderStep();
    await waitFor(() => expect(mockGetNoGos).toHaveBeenCalled());

    await userEvent.click(screen.getByRole('button', { name: 'Nickel' }));

    await waitFor(() =>
      expect(mockAddNoGo).toHaveBeenCalledWith(5, { category: 'allergy', value: 'Nickel' })
    );
    expect(await screen.findByLabelText('Nickel löschen')).toBeInTheDocument();
  });

  it('shows the duplicate toast on a 409 and does not append the row', async () => {
    mockAddNoGo.mockRejectedValue({ isAxiosError: true, response: { status: 409 } });
    renderStep();
    await waitFor(() => expect(mockGetNoGos).toHaveBeenCalled());

    await userEvent.click(screen.getByRole('button', { name: 'Nickel' }));

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith('Dieses No-Go existiert bereits', 'error')
    );
    expect(screen.queryByLabelText('Nickel löschen')).not.toBeInTheDocument();
  });

  it('never logs request/response bodies on a failed addNoGo (PII: allergy values)', async () => {
    // Axios attaches the outgoing request body at err.config.data and FastAPI
    // 422s echo the input in err.response.data — neither may reach the console
    // (health-adjacent allergy data; binding "never log no-go values" rule).
    const SENTINEL = 'GEHEIME-ALLERGIE-SENTINEL';
    mockAddNoGo.mockRejectedValue({
      isAxiosError: true,
      message: 'Request failed with status code 422',
      code: 'ERR_BAD_REQUEST',
      config: {
        url: '/customers/5/no-gos',
        data: JSON.stringify({ category: 'allergy', value: SENTINEL }),
      },
      response: {
        status: 422,
        data: { detail: [{ input: { category: 'allergy', value: SENTINEL } }] },
      },
    });
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      renderStep();
      await waitFor(() => expect(mockGetNoGos).toHaveBeenCalled());

      await userEvent.click(screen.getByRole('button', { name: 'Nickel' }));
      await waitFor(() => expect(consoleErrorSpy).toHaveBeenCalled());

      const loggedText = consoleErrorSpy.mock.calls
        .map((args) => args.map((arg) => JSON.stringify(arg) ?? String(arg)).join(' '))
        .join('\n');
      expect(loggedText).toContain('No-Go anlegen fehlgeschlagen');
      expect(loggedText).not.toContain(SENTINEL);
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  it('adding style word "schlicht" PATCHes {style_words: [schlicht]} (existing + new)', async () => {
    mockUpdateStyleProfile.mockResolvedValue({ ...EMPTY_PROFILE, style_words: ['schlicht'] });
    renderStep();
    await waitFor(() => expect(mockGetStyleProfile).toHaveBeenCalled());

    const input = screen.getByLabelText('Stil-Worte');
    await userEvent.type(input, 'schlicht{Enter}');

    await waitFor(() =>
      expect(mockUpdateStyleProfile).toHaveBeenCalledWith(5, { style_words: ['schlicht'] })
    );
    expect(await screen.findByText('schlicht')).toBeInTheDocument();
  });

  it('rejects a style entry over 100 chars with a toast and never PATCHes it (mirrors the backend cap)', async () => {
    renderStep();
    await waitFor(() => expect(mockGetStyleProfile).toHaveBeenCalled());

    const input = screen.getByLabelText('Stil-Worte');
    await userEvent.type(input, `${'x'.repeat(101)}{Enter}`);

    expect(mockShowToast).toHaveBeenCalledWith(
      'Eintrag darf maximal 100 Zeichen haben',
      'error'
    );
    expect(mockUpdateStyleProfile).not.toHaveBeenCalled();
  });

  it('rejects a new style entry once the list already has 50 items (mirrors the backend cap)', async () => {
    const fullList = Array.from({ length: 50 }, (_, i) => `wort${i}`);
    mockGetStyleProfile.mockResolvedValue({ ...EMPTY_PROFILE, style_words: fullList });
    renderStep();
    await waitFor(() => expect(mockGetStyleProfile).toHaveBeenCalled());

    const input = screen.getByLabelText('Stil-Worte');
    await userEvent.type(input, 'einmehr{Enter}');

    expect(mockShowToast).toHaveBeenCalledWith('Maximal 50 Einträge pro Liste', 'error');
    expect(mockUpdateStyleProfile).not.toHaveBeenCalled();
  });
});
