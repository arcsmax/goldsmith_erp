import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockShowToast = vi.fn();
vi.mock('../contexts', () => ({
  useAuth: () => ({ hasRole: () => true, user: { id: 1, role: 'GOLDSMITH' }, isAuthenticated: true }),
  useToast: () => ({ showToast: mockShowToast }),
  useConfirm: () => ({ showConfirm: vi.fn().mockResolvedValue(true) }),
}));

const mockGetById = vi.fn();
const mockUpdate = vi.fn();
vi.mock('../api/consultations', () => ({
  consultationsApi: {
    getById: (...a: unknown[]) => mockGetById(...a),
    update: (...a: unknown[]) => mockUpdate(...a),
    create: vi.fn(),
    getPhotos: vi.fn().mockResolvedValue([]),
  },
  consultationPhotoPath: (id: string) => `/consultations/photos/${id}`,
  consultationPhotoThumbPath: (id: string) => `/consultations/photos/${id}/thumbnail`,
}));
vi.mock('../api/customers', () => ({
  customersApi: {
    getById: vi.fn().mockResolvedValue({ id: 5, first_name: 'Anna', last_name: 'Muster' }),
    search: vi.fn().mockResolvedValue([]),
    getNoGos: vi.fn().mockResolvedValue([]),
    getStyleProfile: vi
      .fn()
      .mockResolvedValue({ metal_tones: [], finishes: [], stone_preferences: [], style_words: [] }),
  },
}));

import { ConsultationWizardPage } from './ConsultationWizardPage';

const draft = {
  id: 9, customer_id: 5, conducted_by: 1, status: 'draft', occasion: 'other',
  photos: [], created_at: '2026-07-02T10:00:00', updated_at: '2026-07-02T10:00:00',
};

const renderAt = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/consultations/new" element={<ConsultationWizardPage />} />
        <Route path="/consultations/:id" element={<ConsultationWizardPage />} />
      </Routes>
    </MemoryRouter>
  );

beforeEach(() => {
  vi.clearAllMocks();
  mockGetById.mockResolvedValue(draft);
  mockUpdate.mockResolvedValue(draft);
});

describe('ConsultationWizardPage', () => {
  it('loads a draft and shows the step from the URL', async () => {
    renderAt('/consultations/9?step=2');
    await waitFor(() => expect(mockGetById).toHaveBeenCalledWith(9));
    // WizardProgress also renders the step title as a label, so scope to the
    // step heading to avoid an ambiguous multi-match on plain text.
    expect(await screen.findByRole('heading', { name: 'Anlass & Budget' })).toBeInTheDocument();
  });

  it('Weiter advances the step (empty pendingPatch skips the PATCH by design)', async () => {
    renderAt('/consultations/9?step=2');
    await screen.findByRole('heading', { name: 'Anlass & Budget' });
    await userEvent.click(screen.getByRole('button', { name: /Weiter/ }));
    expect(await screen.findByRole('heading', { name: 'Der Wunsch' })).toBeInTheDocument();
    // With placeholder steps pendingPatch is always {}, and the engine
    // deliberately skips the API call for an empty patch:
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('falls back to step 2 and does not crash on a non-numeric ?step= param', async () => {
    renderAt('/consultations/9?step=abc');
    // Number('abc') = NaN must never reach WIZARD_STEPS[NaN - 1]; the engine
    // falls back to the draft default (step 2) instead of crashing the render.
    expect(await screen.findByRole('heading', { name: 'Anlass & Budget' })).toBeInTheDocument();
  });

  it('blocks Weiter and shows an error toast when the autosave PATCH fails', async () => {
    mockUpdate.mockRejectedValueOnce(new Error('network down'));
    renderAt('/consultations/9?step=2');
    await screen.findByRole('heading', { name: 'Anlass & Budget' });

    // The real OccasionBudgetStep now reports fields via onFieldsChange —
    // pick a chip distinct from the seeded 'other' occasion so pendingPatch
    // is non-empty and Weiter actually calls the PATCH.
    await userEvent.click(screen.getByRole('button', { name: 'Hochzeit' }));
    await userEvent.click(screen.getByRole('button', { name: /Weiter/ }));

    // OccasionBudgetStep reports the full field-set of its step (not just the
    // changed field) — occasion_date/budget are unset on the seeded draft.
    await waitFor(() =>
      expect(mockUpdate).toHaveBeenCalledWith(9, {
        occasion: 'wedding',
        occasion_date: null,
        budget_min: null,
        budget_max: null,
      })
    );
    expect(mockShowToast).toHaveBeenCalledWith(
      'Speichern fehlgeschlagen — bitte erneut versuchen',
      'error'
    );
    // Still on step 2 — the failed PATCH must not advance the wizard.
    expect(screen.getByRole('heading', { name: 'Anlass & Budget' })).toBeInTheDocument();
  });
});
