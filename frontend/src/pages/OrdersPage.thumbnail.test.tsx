// OrdersPage — thumbnail column from `first_photo_id` (W2-01, FE-13).
// The backend sends the oldest photo id per order (null for VIEWER), and the
// list renders it through the authenticated thumbnail endpoint.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockGetAll = vi.fn();
vi.mock('../api', () => ({
  ordersApi: { getAll: (...a: unknown[]) => mockGetAll(...a) },
}));

vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: vi.fn() }),
  useConfirm: () => ({ showConfirm: vi.fn() }),
}));

vi.mock('../components/orders/OrderFormModal', () => ({
  OrderFormModal: () => null,
}));

vi.mock('../components/AuthenticatedImage', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    <img data-testid="auth-img" data-src={src} alt={alt} />
  ),
}));

import { OrdersPage } from './OrdersPage';
import { triggerRefetch } from '../lib/refetchBus';

function order(id: number, firstPhotoId: string | null) {
  return {
    id,
    title: `Auftrag ${id}`,
    description: 'Ring',
    status: 'in_progress',
    customer_id: 1,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    first_photo_id: firstPhotoId,
  };
}

afterEach(() => {
  vi.clearAllMocks();
  mockGetAll.mockReset();
});

describe('OrdersPage — realtime refresh (W2-13 hook)', () => {
  it('reloads the list when the orders topic fires', async () => {
    mockGetAll.mockResolvedValueOnce([order(1, null)]);
    mockGetAll.mockResolvedValueOnce([order(1, 'photo-uuid-9')]);

    render(
      <MemoryRouter>
        <OrdersPage />
      </MemoryRouter>
    );
    expect(await screen.findByText('Auftrag 1')).toBeInTheDocument();
    expect(mockGetAll).toHaveBeenCalledTimes(1);

    triggerRefetch('orders');

    await waitFor(() => expect(mockGetAll).toHaveBeenCalledTimes(2));
    const img = await screen.findByTestId('auth-img');
    expect(img).toHaveAttribute('data-src', '/photos/photo-uuid-9/thumbnail');
  });
});

describe('OrdersPage — photo thumbnail', () => {
  it('renders the first photo thumbnail and nothing for orders without one', async () => {
    mockGetAll.mockResolvedValue([order(1, 'photo-uuid-1'), order(2, null)]);

    render(
      <MemoryRouter>
        <OrdersPage />
      </MemoryRouter>
    );

    const imgs = await screen.findAllByTestId('auth-img');
    expect(imgs).toHaveLength(1);
    expect(imgs[0]).toHaveAttribute('data-src', '/photos/photo-uuid-1/thumbnail');
    expect(imgs[0]).toHaveAttribute('alt', 'Foto zu Auftrag 1');
    expect(screen.getByRole('columnheader', { name: 'Foto' })).toBeInTheDocument();
  });
});
