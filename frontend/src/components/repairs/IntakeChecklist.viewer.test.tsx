// IntakeChecklist — VIEWER role-projection regression (SEC-09/GDPR-04).
//
// A checklist item with status 'photo' renders its thumbnail via
// repairPhotoThumbPath -> GET /repairs/photos/{id}/thumbnail, which 403s
// for a caller without DESIGN_VIEW (VIEWER) — see
// tests/integration/test_viewer_role_projection.py::repair_photo_thumbnail.
// The status chip ("Foto ✓") already conveys the item is resolved, so the
// thumbnail is simply omitted for that role instead of triggering a 403.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { RepairJob } from '../../types';

vi.mock('../../api/repairs', () => ({
  repairsApi: {
    uploadPhoto: vi.fn(),
    updateIntakeChecklist: vi.fn(),
  },
  repairPhotoThumbPath: (photoId: number) => `/repairs/photos/${photoId}/thumbnail`,
}));

const mockUseAuth = vi.fn();
vi.mock('../../contexts', () => ({
  useToast: () => ({ showToast: vi.fn() }),
  useAuth: () => mockUseAuth(),
}));

const mockAuthenticatedImage = vi.fn();
vi.mock('../AuthenticatedImage', () => ({
  default: (props: { src: string; alt: string }) => {
    mockAuthenticatedImage(props);
    return <img src={props.src} alt={props.alt} />;
  },
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
    intake_checklist: [
      { key: 'krappen', label: 'Krappen/Fassungen', status: 'photo', photo_id: 55 },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('IntakeChecklist — VIEWER role projection', () => {
  it('does not render the photo thumbnail (and never requests it) for VIEWER', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'VIEWER' } });

    render(
      <IntakeChecklist repair={makeRepair()} onUpdated={vi.fn()} onRefresh={vi.fn()} />
    );

    // Single resolved item -> starts collapsed; expand to see the row.
    await userEvent.click(screen.getByRole('button', { name: /Anzeigen/ }));

    // The status chip still shows the item is resolved...
    expect(screen.getByText('Foto ✓')).toBeInTheDocument();
    // ...but the thumbnail (and its GET /repairs/photos/{id}/thumbnail
    // request) never happens for a role without DESIGN_VIEW.
    expect(mockAuthenticatedImage).not.toHaveBeenCalled();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('renders the photo thumbnail for GOLDSMITH (DESIGN_VIEW held)', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });

    render(
      <IntakeChecklist repair={makeRepair()} onUpdated={vi.fn()} onRefresh={vi.fn()} />
    );

    await userEvent.click(screen.getByRole('button', { name: /Anzeigen/ }));

    expect(mockAuthenticatedImage).toHaveBeenCalledWith(
      expect.objectContaining({ src: '/repairs/photos/55/thumbnail' })
    );
    expect(screen.getByRole('img')).toBeInTheDocument();
  });
});
