// OrderPhotosTab — "Für Kunden sichtbar" checkbox (media_assets.customer_visible).
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../../test/queryWrapper';
import type { OrderPhoto } from '../../types';

const mockList = vi.fn();
const mockToggle = vi.fn();
vi.mock('../../api/media', () => ({
  mediaApi: {
    listForOwner: (...a: unknown[]) => mockList(...a),
    setCustomerVisible: (...a: unknown[]) => mockToggle(...a),
  },
}));
vi.mock('./PhotoUpload', () => ({ PhotoUpload: () => null }));
vi.mock('../AuthenticatedImage', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => <img data-src={src} alt={alt} />,
}));

import { OrderPhotosTab } from './OrderPhotosTab';

const photo = (id: string): OrderPhoto =>
  ({ id, order_id: 42, file_path: 'x', timestamp: '2026-09-01T10:00:00Z', taken_by: 1 }) as OrderPhoto;

const asset = (id: string, visible: boolean) => ({
  id,
  owner_type: 'order',
  owner_id: 42,
  kind: 'photo',
  mime: 'image/jpeg',
  customer_visible: visible,
  sort_order: 0,
  created_at: '2026-09-01T10:00:00Z',
});

describe('OrderPhotosTab customer visibility', () => {
  beforeEach(() => {
    mockList.mockReset();
    mockToggle.mockReset();
  });

  it('shows the flag per photo and saves a toggle', async () => {
    mockList.mockResolvedValue([asset('p1', false), asset('p2', true)]);
    mockToggle.mockResolvedValue(asset('p1', true));

    renderWithQuery(
      <OrderPhotosTab
        orderId={42}
        photos={[photo('p1'), photo('p2')]}
        autoCapture={false}
        onAutoCaptureDone={() => {}}
      />
    );

    const first = await screen.findByRole('checkbox', { name: 'Foto 1 für Kunden sichtbar' });
    const second = screen.getByRole('checkbox', { name: 'Foto 2 für Kunden sichtbar' });
    expect(mockList).toHaveBeenCalledWith('order', 42);
    expect(first).not.toBeChecked();
    expect(second).toBeChecked();

    await userEvent.click(first);

    expect(mockToggle).toHaveBeenCalledWith('p1', true);
    await waitFor(() => expect(first).toBeChecked());
  });

  it('hides the checkbox when the media list is unavailable', async () => {
    mockList.mockRejectedValue(new Error('403'));

    renderWithQuery(
      <OrderPhotosTab
        orderId={42}
        photos={[photo('p1')]}
        autoCapture={false}
        onAutoCaptureDone={() => {}}
      />
    );

    await waitFor(() => expect(mockList).toHaveBeenCalled());
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
});
