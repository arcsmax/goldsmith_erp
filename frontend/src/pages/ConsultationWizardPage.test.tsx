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

  // NOTE: the autosave-failure path (Weiter blocked + error toast) cannot be
  // exercised until a real step reports fields — Task 4 adds
  // `blocks Weiter and toasts when the PATCH fails` to
  // OccasionBudgetStep.test.tsx-level wizard integration. Do NOT test it here.
});
