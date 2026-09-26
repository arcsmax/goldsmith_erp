// StyleNoGoStep — Beratungs-Wizard step 4 tests.
//
// Pins the behaviors from the Task 5 brief plus the HEALTH_DATA consent gate
// added for the "Schnellauswahl Allergien 422" bug:
//   (a) renders loaded no-gos and style chips.
//   (b) with an active HEALTH_DATA consent, the "Nickel" quick-allergy chip
//       posts {category:'allergy', value:'Nickel'} and appends the returned row.
//   (c) a 409 from addNoGo shows the duplicate toast and does NOT append.
//   (d) adding style word "schlicht" PATCHes {style_words: ['schlicht']}
//       (existing + new).
//   (e) without an active HEALTH_DATA consent, the allergy chips are
//       disabled; confirming the consent block grants the consent, then the
//       chip can be clicked and posts the no-go.
//   (f) a non-2xx error's backend detail (e.g. the consent-required 422) is
//       shown via getErrorMessage instead of the old generic toast.
//   (g) non-health no-gos (e.g. "kein Gelbgold", category metal) never need
//       consent and keep working regardless of the HEALTH_DATA state.
//
// Both api/customers, api/consents and contexts are mocked BEFORE the
// component import so no network or provider tree is needed. api/consents is
// only PARTIALLY mocked (list/grant) — findActiveConsent and the label maps
// stay real so HealthDataConsentBlock renders exactly as in production.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Consultation, NoGo, StyleProfile } from '../../types';
import type { ConsentRecord } from '../../api/consents';

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

const mockConsentsList = vi.fn();
const mockConsentsGrant = vi.fn();

vi.mock('../../api/consents', async () => {
  const actual = await vi.importActual<typeof import('../../api/consents')>(
    '../../api/consents'
  );
  return {
    ...actual,
    consentsApi: {
      ...actual.consentsApi,
      list: (...a: unknown[]) => mockConsentsList(...a),
      grant: (...a: unknown[]) => mockConsentsGrant(...a),
    },
  };
});

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

const ACTIVE_HEALTH_CONSENT: ConsentRecord = {
  id: 9,
  customer_id: 5,
  purpose: 'health_data',
  method: 'in_person',
  granted_at: '2026-07-01T09:00:00',
  revoked_at: null,
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
  // Default: the customer already has an active HEALTH_DATA consent, so the
  // pre-existing chip/style-profile behaviors below don't need to go
  // through the grant flow — that flow gets its own tests.
  mockConsentsList.mockResolvedValue([ACTIVE_HEALTH_CONSENT]);
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

  it('quick-allergy chip "Nickel" posts {category: allergy, value: Nickel} and appends the row (consent already granted)', async () => {
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
    await waitFor(() => expect(screen.getByRole('button', { name: 'Nickel' })).toBeEnabled());

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
    await waitFor(() => expect(screen.getByRole('button', { name: 'Nickel' })).toBeEnabled());

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
      await waitFor(() => expect(screen.getByRole('button', { name: 'Nickel' })).toBeEnabled());

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

  describe('HEALTH_DATA consent gate', () => {
    beforeEach(() => {
      // No active consent for this describe block — the scenario from the
      // bug report (customer has no HEALTH_DATA consent yet).
      mockConsentsList.mockResolvedValue([]);
    });

    it('disables the allergy quick-select chips until the consent is granted', async () => {
      renderStep();
      await waitFor(() => expect(mockConsentsList).toHaveBeenCalledWith(5));

      expect(await screen.findByRole('button', { name: 'Nickel' })).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Kupfer' })).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Silber' })).toBeDisabled();
      expect(screen.getByText('Einwilligung Gesundheitsdaten')).toBeInTheDocument();
    });

    it('confirming the consent block calls the consent endpoint, then a chip click calls the no-go endpoint', async () => {
      mockConsentsGrant.mockResolvedValue(ACTIVE_HEALTH_CONSENT);
      const created: NoGo = {
        id: 3,
        customer_id: 5,
        category: 'allergy',
        value: 'Kupfer',
        note: null,
        source_consultation_id: null,
        created_at: '2026-07-02T10:00:00',
      };
      mockAddNoGo.mockResolvedValue(created);

      renderStep();
      await waitFor(() => expect(mockConsentsList).toHaveBeenCalledWith(5));
      expect(await screen.findByRole('button', { name: 'Kupfer' })).toBeDisabled();

      await userEvent.click(screen.getByRole('button', { name: 'Einwilligung bestätigen' }));

      await waitFor(() =>
        expect(mockConsentsGrant).toHaveBeenCalledWith(5, {
          purpose: 'health_data',
          method: 'in_person',
          note: undefined,
        })
      );
      // Only AFTER the grant resolves does the chip become clickable.
      await waitFor(() => expect(screen.getByRole('button', { name: 'Kupfer' })).toBeEnabled());

      await userEvent.click(screen.getByRole('button', { name: 'Kupfer' }));

      await waitFor(() =>
        expect(mockAddNoGo).toHaveBeenCalledWith(5, { category: 'allergy', value: 'Kupfer' })
      );
      // Consent endpoint really was called BEFORE the no-go endpoint.
      expect(mockConsentsGrant.mock.invocationCallOrder[0]).toBeLessThan(
        mockAddNoGo.mock.invocationCallOrder[0]
      );
    });

    it('shows the backend German error text (not a generic toast) when the consent gate rejects a no-go', async () => {
      mockAddNoGo.mockRejectedValue({
        isAxiosError: true,
        response: {
          status: 422,
          data: {
            detail:
              "Allergien sind Gesundheitsdaten (Art. 9 DSGVO) und dürfen nur mit " +
              "ausdrücklicher Einwilligung der Kundin/des Kunden gespeichert werden. " +
              "Bitte zuerst die Einwilligung 'Gesundheitsdaten' erfassen.",
          },
        },
      });
      // Simulate a race where the chip was clickable (consent looked granted
      // client-side) but the backend still rejects it — the toast must show
      // the backend's own message, not "No-Go konnte nicht angelegt werden".
      mockConsentsList.mockResolvedValue([ACTIVE_HEALTH_CONSENT]);

      renderStep();
      await waitFor(() => expect(screen.getByRole('button', { name: 'Nickel' })).toBeEnabled());

      await userEvent.click(screen.getByRole('button', { name: 'Nickel' }));

      await waitFor(() =>
        expect(mockShowToast).toHaveBeenCalledWith(
          expect.stringContaining('Gesundheitsdaten (Art. 9 DSGVO)'),
          'error'
        )
      );
    });

    it('lets a non-health no-go (e.g. "kein Gelbgold", category metal) through without any consent', async () => {
      const created: NoGo = {
        id: 4,
        customer_id: 5,
        category: 'metal',
        value: 'Gelbgold',
        note: null,
        source_consultation_id: null,
        created_at: '2026-07-02T10:00:00',
      };
      mockAddNoGo.mockResolvedValue(created);

      renderStep();
      await waitFor(() => expect(mockConsentsList).toHaveBeenCalledWith(5));

      await userEvent.type(screen.getByLabelText('Wert'), 'Gelbgold');
      // Category defaults to 'metal' — the submit button must NOT be gated.
      expect(screen.getByRole('button', { name: 'No-Go hinzufügen' })).toBeEnabled();
      await userEvent.click(screen.getByRole('button', { name: 'No-Go hinzufügen' }));

      await waitFor(() =>
        expect(mockAddNoGo).toHaveBeenCalledWith(5, { category: 'metal', value: 'Gelbgold' })
      );
      expect(mockConsentsGrant).not.toHaveBeenCalled();
    });
  });
});
