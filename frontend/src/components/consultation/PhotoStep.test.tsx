// PhotoStep — Beratungs-Wizard step 6 tests.
//
// Pins three behaviors from the Task 7 brief:
//   (a) renders existing photos from consultation.photos with kind badges.
//   (b) selecting kind 'reference' then choosing a file calls
//       uploadPhoto(id, file, 'reference', undefined) and then refresh().
//   (c) a 9MB File shows the size toast and never calls the API.
//
// api/consultations is mocked BEFORE the component import so no network is
// needed. AuthenticatedImage is also mocked — it does its own authenticated
// blob fetch via apiClient, unrelated to what this test verifies, and would
// otherwise trip the global MSW "error on unhandled request" setup.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Consultation, ConsultationPhoto } from '../../types';

const mockUploadPhoto = vi.fn();
const mockDeletePhoto = vi.fn();

vi.mock('../../api/consultations', () => ({
  consultationsApi: {
    uploadPhoto: (...a: unknown[]) => mockUploadPhoto(...a),
    deletePhoto: (...a: unknown[]) => mockDeletePhoto(...a),
  },
  consultationPhotoThumbPath: (photoId: string) => `/consultations/photos/${photoId}/thumbnail`,
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

import { PhotoStep, PHOTO_KIND_LABELS } from './PhotoStep';

function makeConsultation(overrides: Partial<Consultation> = {}): Consultation {
  return {
    id: 9,
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
const mockRefresh = vi.fn(async () => undefined);

const renderStep = (consultation: Consultation) =>
  render(<PhotoStep consultation={consultation} onPatch={noopPatch} refresh={mockRefresh} />);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PhotoStep', () => {
  it('renders existing photos from consultation.photos with kind badges', () => {
    const photos: ConsultationPhoto[] = [
      {
        id: 'p1',
        consultation_id: 9,
        kind: 'reference',
        notes: null,
        timestamp: '2026-07-02T10:00:00',
      },
      {
        id: 'p2',
        consultation_id: 9,
        kind: 'sketch',
        notes: null,
        timestamp: '2026-07-02T10:05:00',
      },
    ];

    renderStep(makeConsultation({ photos }));

    // Kind labels also appear as chip-selector button text, so scope each
    // assertion to its own photo card (found via the img's alt text) instead
    // of the ambiguous plain text.
    const images = screen.getAllByRole('img');
    expect(images).toHaveLength(2);
    const referenceCard = images[0].closest('.consultation-photo-card') as HTMLElement;
    const sketchCard = images[1].closest('.consultation-photo-card') as HTMLElement;
    expect(within(referenceCard).getByText(PHOTO_KIND_LABELS.reference)).toBeInTheDocument();
    expect(within(sketchCard).getByText(PHOTO_KIND_LABELS.sketch)).toBeInTheDocument();
  });

  it('selecting kind "reference" then choosing a file calls uploadPhoto and refresh', async () => {
    mockUploadPhoto.mockResolvedValue({
      id: 'p3',
      consultation_id: 9,
      kind: 'reference',
      notes: null,
      timestamp: '2026-07-02T10:10:00',
    });
    renderStep(makeConsultation());

    // Single-select chip group: role="radio" inside role="radiogroup"
    // (final-review polish, replaces aria-pressed).
    await userEvent.click(screen.getByRole('radio', { name: PHOTO_KIND_LABELS.reference }));

    const file = new File(['x'], 'idea.jpg', { type: 'image/jpeg' });
    const input = screen.getByLabelText(/Foto hinzufügen/i, { selector: 'input' });
    await userEvent.upload(input, file);

    await waitFor(() =>
      expect(mockUploadPhoto).toHaveBeenCalledWith(9, file, 'reference', undefined)
    );
    await waitFor(() => expect(mockRefresh).toHaveBeenCalled());
  });

  it('a 9MB file shows the size toast and never calls the API', async () => {
    renderStep(makeConsultation());

    const bigFile = new File([new ArrayBuffer(9 * 1024 * 1024)], 'big.jpg', {
      type: 'image/jpeg',
    });
    const input = screen.getByLabelText(/Foto hinzufügen/i, { selector: 'input' });
    await userEvent.upload(input, bigFile);

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        expect.stringContaining('8 MB'),
        'error'
      )
    );
    expect(mockUploadPhoto).not.toHaveBeenCalled();
  });
});
