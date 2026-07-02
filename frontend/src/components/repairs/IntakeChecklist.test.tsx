// IntakeChecklist tests — pins the four behaviors from the Task 3 brief:
//   (a) capturing a photo for an open item uploads then PUTs the full
//       checklist array with that item's photo_id set.
//   (b) "nicht zutreffend" requires a reason of at least 3 characters
//       before the save button is enabled.
//   (c) a null intake_checklist renders an "ohne Checkliste" note, no crash.
//   (d) once every item is resolved, a completed summary is shown and can
//       be collapsed.
//
// api/repairs is mocked BEFORE the component import so no network is
// needed. AuthenticatedImage is mocked — it does its own authenticated
// blob fetch via apiClient, unrelated to what this test verifies.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { RepairJob } from '../../types';

const mockUploadPhoto = vi.fn();
const mockUpdateIntakeChecklist = vi.fn();

vi.mock('../../api/repairs', () => ({
  repairsApi: {
    uploadPhoto: (...a: unknown[]) => mockUploadPhoto(...a),
    updateIntakeChecklist: (...a: unknown[]) => mockUpdateIntakeChecklist(...a),
  },
  repairPhotoThumbPath: (photoId: number) => `/repairs/photos/${photoId}/thumbnail`,
}));

const mockShowToast = vi.fn();
vi.mock('../../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}));

vi.mock('../AuthenticatedImage', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => <img src={src} alt={alt} />,
}));

import { IntakeChecklist } from './IntakeChecklist';

function makeRepair(overrides: Partial<RepairJob> = {}): RepairJob {
  return {
    id: 7,
    repair_number: 'REP-2026-0007',
    bag_number: 'T-007',
    customer_id: null,
    customer: null,
    received_by: null,
    item_description: 'Ring',
    item_type: 'ring',
    metal_type: null,
    estimated_value: null,
    status: 'received',
    diagnosis_notes: null,
    estimated_cost: null,
    actual_cost: null,
    estimated_completion_date: null,
    actual_completion_date: null,
    customer_notified_at: null,
    picked_up_at: null,
    is_deleted: false,
    created_at: '2026-07-02T10:00:00',
    updated_at: '2026-07-02T10:00:00',
    photos: [],
    intake_checklist: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('IntakeChecklist', () => {
  it('capturing a photo for an open item uploads then PUTs the full list with photo_id', async () => {
    const repair = makeRepair({
      intake_checklist: [
        { key: 'krappen', label: 'Krappen/Fassungen', status: 'open' },
        { key: 'gravuren', label: 'Gravuren', status: 'open' },
      ],
    });
    mockUploadPhoto.mockResolvedValue({ id: 55 });
    const updatedRepair = makeRepair({
      intake_checklist: [
        { key: 'krappen', label: 'Krappen/Fassungen', status: 'photo', photo_id: 55 },
        { key: 'gravuren', label: 'Gravuren', status: 'open' },
      ],
    });
    mockUpdateIntakeChecklist.mockResolvedValue(updatedRepair);
    const onUpdated = vi.fn();

    render(<IntakeChecklist repair={repair} onUpdated={onUpdated} />);

    const file = new File(['x'], 'krappen.jpg', { type: 'image/jpeg' });
    const inputs = screen.getAllByLabelText(/Foto aufnehmen/i, { selector: 'input' });
    await userEvent.upload(inputs[0], file);

    await waitFor(() => expect(mockUploadPhoto).toHaveBeenCalledWith(7, file, 'intake'));
    await waitFor(() =>
      expect(mockUpdateIntakeChecklist).toHaveBeenCalledWith(7, [
        { key: 'krappen', label: 'Krappen/Fassungen', status: 'photo', photo_id: 55 },
        { key: 'gravuren', label: 'Gravuren', status: 'open' },
      ])
    );
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(updatedRepair));
  });

  it('"nicht zutreffend" requires a reason of at least 3 characters before saving', async () => {
    const repair = makeRepair({
      intake_checklist: [{ key: 'pave', label: 'Pavé-Besatz', status: 'open' }],
    });
    const updatedRepair = makeRepair({
      intake_checklist: [
        { key: 'pave', label: 'Pavé-Besatz', status: 'na', na_reason: 'abc vorhanden' },
      ],
    });
    mockUpdateIntakeChecklist.mockResolvedValue(updatedRepair);
    const onUpdated = vi.fn();

    render(<IntakeChecklist repair={repair} onUpdated={onUpdated} />);

    await userEvent.click(screen.getByRole('button', { name: 'Nicht zutreffend' }));

    const saveButton = screen.getByRole('button', { name: /Speichern/i });
    expect(saveButton).toBeDisabled();

    const reasonInput = screen.getByPlaceholderText(/Begründung/i);
    await userEvent.type(reasonInput, 'ab');
    expect(saveButton).toBeDisabled();
    expect(mockUpdateIntakeChecklist).not.toHaveBeenCalled();

    await userEvent.type(reasonInput, 'c vorhanden');
    expect(saveButton).not.toBeDisabled();

    await userEvent.click(saveButton);

    await waitFor(() =>
      expect(mockUpdateIntakeChecklist).toHaveBeenCalledWith(7, [
        { key: 'pave', label: 'Pavé-Besatz', status: 'na', na_reason: 'abc vorhanden' },
      ])
    );
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(updatedRepair));
  });

  it('renders an "ohne Checkliste" note and does not crash when intake_checklist is null', () => {
    const repair = makeRepair({ intake_checklist: null });
    render(<IntakeChecklist repair={repair} onUpdated={vi.fn()} />);
    expect(screen.getByText(/Keine Eingangs-Checkliste hinterlegt/i)).toBeInTheDocument();
  });

  it('shows a completed summary once all items are resolved, and can be collapsed', async () => {
    const repair = makeRepair({
      intake_checklist: [
        { key: 'a', label: 'A', status: 'photo', photo_id: 1 },
        { key: 'b', label: 'B', status: 'na', na_reason: 'nicht vorhanden' },
      ],
    });
    render(<IntakeChecklist repair={repair} onUpdated={vi.fn()} />);

    expect(screen.getByText('2/2 erledigt')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Einklappen' }));

    expect(screen.getByRole('button', { name: /2\/2 erledigt/ })).toBeInTheDocument();
  });
});
