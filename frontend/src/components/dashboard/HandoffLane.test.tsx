// LV-08: the "Übergaben an mich" lane showed the raw enum
// ("Übergabe: request_review"); it must show the German handoff type.
import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithQuery } from '../../test/queryWrapper';

const mockGetPending = vi.fn();
vi.mock('../../api/handoffs', () => ({
  handoffsApi: { getPending: () => mockGetPending() },
}));
vi.mock('../../contexts/OrderContext', () => ({
  useOrders: () => ({ setOrderTab: vi.fn() }),
}));

import { HandoffLane } from './HandoffLane';

describe('HandoffLane', () => {
  it('shows the German handoff type instead of the enum value', async () => {
    mockGetPending.mockResolvedValue({
      data: [{ id: 1, order_id: 13, handoff_type: 'request_review', notes: null }],
    });

    renderWithQuery(<HandoffLane />);

    expect(await screen.findByText('Übergabe: Prüfung anfordern')).toBeInTheDocument();
    expect(screen.queryByText(/request_review/)).not.toBeInTheDocument();
  });
});
