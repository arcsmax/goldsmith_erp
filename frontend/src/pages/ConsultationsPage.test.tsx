// ConsultationsPage tests — Task 9 (V1.1 consultation frontend).
//
// Pins:
//   (a) cards render occasion label, piece-type label, status badge, and
//       created date (dd.MM.yyyy) from consultationsApi.getAll; the
//       follow-up date renders only when set.
//   (b) clicking the 'Entwurf' status chip refetches with {status: 'draft'}.
//   (c) clicking a draft card navigates to ?step=2 (resume); clicking a
//       non-draft card navigates to ?step=7 (summary/read-only).
//
// react-router-dom's useNavigate is mocked via the async-orig pattern (see
// SummaryStep.test.tsx / ScannerPageV2.test.tsx) — no MemoryRouter needed
// since the whole module is replaced and the page only calls useNavigate().
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mocks = vi.hoisted(() => ({ navigate: vi.fn() }));

vi.mock('react-router-dom', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

const mockGetAll = vi.fn();
vi.mock('../api/consultations', () => ({
  consultationsApi: {
    getAll: (...a: unknown[]) => mockGetAll(...a),
  },
}));

import { ConsultationsPage } from './ConsultationsPage';
import type { ConsultationListItem } from '../types';

const draftItem: ConsultationListItem = {
  id: 1,
  customer_id: 5,
  occasion: 'wedding',
  piece_type: 'ring',
  status: 'draft',
  follow_up_at: null,
  created_at: '2026-06-01T10:00:00',
};

const completedItem: ConsultationListItem = {
  id: 2,
  customer_id: 6,
  occasion: 'birthday',
  piece_type: 'pendant',
  status: 'completed',
  follow_up_at: '2026-07-15T00:00:00',
  created_at: '2026-06-10T10:00:00',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGetAll.mockResolvedValue([draftItem, completedItem]);
});

describe('ConsultationsPage', () => {
  it('renders cards from mocked getAll with occasion, piece type, status badge, and dates', async () => {
    render(<ConsultationsPage />);

    expect(await screen.findByText('Hochzeit')).toBeInTheDocument();
    expect(screen.getByText('Ring')).toBeInTheDocument();
    // 'Entwurf' also labels the filter chip — scope to the status badge.
    expect(
      screen.getByText('Entwurf', { selector: '.consultation-status-badge' })
    ).toBeInTheDocument();
    expect(screen.getByText('01.06.2026')).toBeInTheDocument();

    expect(screen.getByText('Geburtstag')).toBeInTheDocument();
    expect(screen.getByText('Anhänger')).toBeInTheDocument();
    expect(
      screen.getByText('Abgeschlossen', { selector: '.consultation-status-badge' })
    ).toBeInTheDocument();
    // Follow-up date renders when set (draftItem has none, completedItem does).
    expect(screen.getByText(/15\.07\.2026/)).toBeInTheDocument();

    // Initial fetch has no status filter applied.
    expect(mockGetAll).toHaveBeenCalledWith({ status: undefined });
  });

  it('clicking the Entwurf chip refetches with {status: "draft"}', async () => {
    render(<ConsultationsPage />);
    await screen.findByText('Hochzeit');

    await userEvent.click(screen.getByRole('button', { name: 'Entwurf' }));

    await waitFor(() =>
      expect(mockGetAll).toHaveBeenLastCalledWith({ status: 'draft' })
    );
  });

  it('clicking a draft card navigates to step=2 (resume)', async () => {
    render(<ConsultationsPage />);
    await screen.findByText('Hochzeit');

    await userEvent.click(screen.getByText('Hochzeit'));

    expect(mocks.navigate).toHaveBeenCalledWith('/consultations/1?step=2');
  });

  it('clicking a non-draft card navigates to step=7 (summary)', async () => {
    render(<ConsultationsPage />);
    await screen.findByText('Geburtstag');

    await userEvent.click(screen.getByText('Geburtstag'));

    expect(mocks.navigate).toHaveBeenCalledWith('/consultations/2?step=7');
  });

  it('shows an empty state when no consultations match the filter', async () => {
    mockGetAll.mockResolvedValue([]);
    render(<ConsultationsPage />);

    expect(await screen.findByText('Keine Beratungen gefunden.')).toBeInTheDocument();
  });
});
