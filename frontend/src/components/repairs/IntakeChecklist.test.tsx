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

  it('locks all item controls while a mutation is pending — second rapid mutation is a no-op', async () => {
    const repair = makeRepair({
      intake_checklist: [
        { key: 'krappen', label: 'Krappen/Fassungen', status: 'open' },
        { key: 'gravuren', label: 'Gravuren', status: 'open' },
      ],
    });
    // First item's upload stays pending so the list-wide lock is active.
    let resolveUpload!: (value: { id: number }) => void;
    mockUploadPhoto.mockReturnValue(
      new Promise<{ id: number }>((resolve) => {
        resolveUpload = resolve;
      })
    );
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
    const inputs = screen.getAllByLabelText(/Foto aufnehmen|Wird hochgeladen/i, {
      selector: 'input',
    });
    await userEvent.upload(inputs[0], file);
    await waitFor(() => expect(mockUploadPhoto).toHaveBeenCalledTimes(1));

    // While the first mutation is pending, the SECOND item's controls must
    // be locked too (stale-snapshot protection): its file input and its
    // "Nicht zutreffend" button are disabled — a rapid second mutation is
    // a no-op.
    expect(inputs[1]).toBeDisabled();
    screen
      .getAllByRole('button', { name: 'Nicht zutreffend' })
      .forEach((btn) => expect(btn).toBeDisabled());

    const secondFile = new File(['y'], 'gravuren.jpg', { type: 'image/jpeg' });
    await userEvent.upload(inputs[1], secondFile);
    expect(mockUploadPhoto).toHaveBeenCalledTimes(1);
    expect(mockUpdateIntakeChecklist).not.toHaveBeenCalled();

    resolveUpload({ id: 55 });
    await waitFor(() => expect(mockUpdateIntakeChecklist).toHaveBeenCalledTimes(1));
    expect(mockUpdateIntakeChecklist).toHaveBeenCalledWith(7, [
      { key: 'krappen', label: 'Krappen/Fassungen', status: 'photo', photo_id: 55 },
      { key: 'gravuren', label: 'Gravuren', status: 'open' },
    ]);
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(updatedRepair));
  });

  it('starts collapsed when the checklist is already complete on mount, and supports manual expand/collapse', async () => {
    const repair = makeRepair({
      intake_checklist: [
        { key: 'a', label: 'A', status: 'photo', photo_id: 1 },
        { key: 'b', label: 'B', status: 'na', na_reason: 'nicht vorhanden' },
      ],
    });
    render(<IntakeChecklist repair={repair} onUpdated={vi.fn()} />);

    // Fully resolved on the initial `repair` prop -> collapsed summary only,
    // no full list, no "Einklappen" control.
    expect(screen.queryByRole('button', { name: 'Einklappen' })).not.toBeInTheDocument();
    const summaryButton = screen.getByRole('button', { name: /2\/2 erledigt/ });
    expect(summaryButton).toBeInTheDocument();

    // Manual toggle still works: expand...
    await userEvent.click(summaryButton);
    expect(screen.getByText('2/2 erledigt')).toBeInTheDocument();
    const collapseButton = screen.getByRole('button', { name: 'Einklappen' });
    expect(collapseButton).toBeInTheDocument();

    // ...and collapse again.
    await userEvent.click(collapseButton);
    expect(screen.getByRole('button', { name: /2\/2 erledigt/ })).toBeInTheDocument();
  });

  it('starts expanded when the checklist is not yet complete on mount', () => {
    const repair = makeRepair({
      intake_checklist: [
        { key: 'a', label: 'A', status: 'photo', photo_id: 1 },
        { key: 'b', label: 'B', status: 'open' },
      ],
    });
    render(<IntakeChecklist repair={repair} onUpdated={vi.fn()} />);

    expect(screen.getByText('1/2 erledigt')).toBeInTheDocument();
    expect(screen.getByText('Eingangs-Checkliste')).toBeInTheDocument();
  });

  it('shows a generic upload-failure toast when the photo upload itself fails', async () => {
    const repair = makeRepair({
      intake_checklist: [{ key: 'krappen', label: 'Krappen/Fassungen', status: 'open' }],
    });
    mockUploadPhoto.mockRejectedValue(new Error('network down'));
    const onUpdated = vi.fn();

    render(<IntakeChecklist repair={repair} onUpdated={onUpdated} />);

    const file = new File(['x'], 'krappen.jpg', { type: 'image/jpeg' });
    const input = screen.getByLabelText(/Foto aufnehmen/i, { selector: 'input' });
    await userEvent.upload(input, file);

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        'Foto konnte nicht hochgeladen werden',
        'error'
      )
    );
    expect(mockUpdateIntakeChecklist).not.toHaveBeenCalled();
    expect(onUpdated).not.toHaveBeenCalled();
  });

  it('shows an honest partial-failure toast and still refreshes when the photo uploads but the checklist PUT fails', async () => {
    const repair = makeRepair({
      intake_checklist: [{ key: 'krappen', label: 'Krappen/Fassungen', status: 'open' }],
    });
    mockUploadPhoto.mockResolvedValue({ id: 55 });
    mockUpdateIntakeChecklist.mockRejectedValue(new Error('put failed'));
    const onUpdated = vi.fn();
    const onRefresh = vi.fn();

    render(<IntakeChecklist repair={repair} onUpdated={onUpdated} onRefresh={onRefresh} />);

    const file = new File(['x'], 'krappen.jpg', { type: 'image/jpeg' });
    const input = screen.getByLabelText(/Foto aufnehmen/i, { selector: 'input' });
    await userEvent.upload(input, file);

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        'Foto gespeichert, Verknüpfung fehlgeschlagen — bitte Seite neu laden',
        'error'
      )
    );
    // No crash, no false-success callback, but the parent still gets a
    // chance to refetch so the (now unlinked) stored photo becomes visible.
    expect(onUpdated).not.toHaveBeenCalled();
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
