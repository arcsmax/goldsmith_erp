// RepairDetailPage — VIEWER role-projection regression (SEC-09/GDPR-04).
//
// The backend strips `photos` entirely from RepairJobRead for a caller
// without DESIGN_VIEW (VIEWER) — see role_projection.py and
// tests/integration/test_viewer_role_projection.py::repair_detail. Before
// this fix, `repair.photos.length` (building the tab list) and
// `repair.photos.filter(...)` (PhotosTab) both crashed on the resulting
// `undefined`, taking down the whole page for a VIEWER. Repair photo list
// / file / thumbnail endpoints are also individually gated (403), so the
// Fotos tab must never be reachable — and never fetched — for that role.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { RepairJob } from '../types';

const mockGetById = vi.fn();
vi.mock('../api/repairs', () => ({
  repairsApi: {
    getById: (...args: unknown[]) => mockGetById(...args),
  },
  repairPhotoPath: (id: number) => `/repairs/photos/${id}`,
  repairPhotoThumbPath: (id: number) => `/repairs/photos/${id}/thumbnail`,
}));

const mockUseAuth = vi.fn();
vi.mock('../contexts', () => ({
  useAuth: () => mockUseAuth(),
  useToast: () => ({ showToast: vi.fn() }),
  useConfirm: () => ({ showConfirm: vi.fn() }),
}));

import { RepairDetailPage } from './RepairDetailPage';

function viewerAuth() {
  return { user: { role: 'VIEWER' } };
}

function goldsmithAuth() {
  return { user: { role: 'GOLDSMITH' } };
}

// The backend omits `photos` and `intake_checklist` may still be present
// (financial fields on the intake checklist itself are out of scope here),
// but `photos` is the field under test — deliberately absent, mirroring
// the real projected response for VIEWER.
function makeRepair(overrides: Partial<RepairJob> = {}): RepairJob {
  return {
    id: 1,
    repair_number: 'R-2026-0001',
    bag_number: 'B-1',
    item_description: 'Ring, Stein lose',
    item_type: 'ring',
    status: 'received',
    is_deleted: false,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    photos: [],
    estimated_cost: 120,
    actual_cost: null,
    estimated_value: 500,
    ...overrides,
  } as RepairJob;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/repairs/1']}>
      <Routes>
        <Route path="/repairs/:id" element={<RepairDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('RepairDetailPage — VIEWER role projection', () => {
  it('does not crash when `photos` is absent from the response (backend strips it for VIEWER)', async () => {
    mockUseAuth.mockReturnValue(viewerAuth());
    // `photos` cast away below to mirror the real (type-violating) wire
    // payload a VIEWER actually receives — role_projection.py omits the key.
    const repair = makeRepair();
    delete (repair as any).photos;
    mockGetById.mockResolvedValue(repair);

    renderPage();

    expect(await screen.findByText('R-2026-0001')).toBeInTheDocument();
  });

  it('hides the Fotos tab for VIEWER and never renders a tab labelled with a photo count', async () => {
    mockUseAuth.mockReturnValue(viewerAuth());
    const repair = makeRepair();
    delete (repair as any).photos;
    mockGetById.mockResolvedValue(repair);

    renderPage();

    await screen.findByText('R-2026-0001');
    expect(screen.queryByRole('tab', { name: /Fotos/ })).not.toBeInTheDocument();
  });

  it('shows the Fotos tab for GOLDSMITH and it is clickable without crashing', async () => {
    mockUseAuth.mockReturnValue(goldsmithAuth());
    mockGetById.mockResolvedValue(makeRepair({ photos: [] }));

    renderPage();

    await screen.findByText('R-2026-0001');
    const tab = screen.getByRole('tab', { name: 'Fotos (0)' });
    expect(tab).toBeInTheDocument();
    await userEvent.click(tab);
    expect(screen.getByRole('tab', { name: 'Fotos (0)', selected: true })).toBeInTheDocument();
  });
});

describe('RepairDetailPage — Annahmeschein (W2-12)', () => {
  it('offers the Annahmeschein reprint to GOLDSMITH', async () => {
    mockUseAuth.mockReturnValue(goldsmithAuth());
    mockGetById.mockResolvedValue(makeRepair());

    renderPage();

    await screen.findByText('R-2026-0001');
    expect(screen.getByRole('button', { name: 'Annahmeschein drucken' })).toBeInTheDocument();
  });

  it('hides the Annahmeschein from VIEWER (the PDF carries photos)', async () => {
    mockUseAuth.mockReturnValue(viewerAuth());
    const repair = makeRepair();
    delete (repair as any).photos;
    mockGetById.mockResolvedValue(repair);

    renderPage();

    await screen.findByText('R-2026-0001');
    expect(screen.queryByRole('button', { name: 'Annahmeschein drucken' })).not.toBeInTheDocument();
  });
});
