// PhotoPicker tests — V1.2 Task 2.
//
// Pins:
//   (a) renders one selectable checkbox per photo returned by
//       photosApi.getForOrder.
//   (b) clicking an unselected card calls onChange with the id ADDED
//       (immutably — never mutates the selectedIds array it was given).
//   (c) clicking an already-selected card calls onChange with the id
//       REMOVED.
//   (d) once selectedIds.length reaches `max`, unselected cards are
//       disabled (selected ones stay clickable so the user can deselect).
//   (e) the `disabled` prop disables every card regardless of selection.
//   (f) a photosApi.getForOrder rejection is swallowed (logError, no
//       throw) and renders the empty state instead of crashing the tab.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { OrderPhoto } from '../../types';

const mockGetForOrder = vi.fn();
vi.mock('../../api/photos', () => ({
  photosApi: {
    getForOrder: (...args: unknown[]) => mockGetForOrder(...args),
  },
}));

const mockLogError = vi.fn();
vi.mock('../../lib/logError', () => ({
  logError: (...args: unknown[]) => mockLogError(...args),
}));

// AuthenticatedImage does its own authenticated blob fetch via apiClient —
// unrelated to what this test verifies, so it's replaced with a plain <img>.
vi.mock('../AuthenticatedImage', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => <img src={src} alt={alt} />,
}));

import { PhotoPicker } from './PhotoPicker';

function makePhotos(count: number): OrderPhoto[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `photo-${i + 1}`,
    order_id: 1,
    file_path: `/data/photos/${i + 1}.jpg`,
    notes: null,
    timestamp: `2026-07-0${i + 1}T10:00:00`,
    taken_by: 1,
  }));
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('PhotoPicker', () => {
  it('renders one selectable checkbox per photo from photosApi.getForOrder', async () => {
    mockGetForOrder.mockResolvedValue({ data: makePhotos(3) });

    render(<PhotoPicker orderId={1} selectedIds={[]} onChange={vi.fn()} />);

    const checkboxes = await screen.findAllByRole('checkbox');
    expect(checkboxes).toHaveLength(3);
    expect(mockGetForOrder).toHaveBeenCalledWith(1);
    checkboxes.forEach((cb) => expect(cb).toHaveAttribute('aria-checked', 'false'));
  });

  it('clicking an unselected card calls onChange with the id added (immutably)', async () => {
    mockGetForOrder.mockResolvedValue({ data: makePhotos(3) });
    const onChange = vi.fn();
    const selectedIds = ['photo-2'];

    render(<PhotoPicker orderId={1} selectedIds={selectedIds} onChange={onChange} />);

    const checkboxes = await screen.findAllByRole('checkbox');
    await userEvent.click(checkboxes[0]); // photo-1, unselected

    expect(onChange).toHaveBeenCalledWith(['photo-2', 'photo-1']);
    // The array passed in must not have been mutated.
    expect(selectedIds).toEqual(['photo-2']);
  });

  it('clicking a selected card calls onChange with the id removed', async () => {
    mockGetForOrder.mockResolvedValue({ data: makePhotos(3) });
    const onChange = vi.fn();

    render(
      <PhotoPicker orderId={1} selectedIds={['photo-1', 'photo-2']} onChange={onChange} />
    );

    const checkboxes = await screen.findAllByRole('checkbox');
    await userEvent.click(checkboxes[0]); // photo-1, selected

    expect(onChange).toHaveBeenCalledWith(['photo-2']);
  });

  it('disables unselected cards once selectedIds reaches max, shows the hint', async () => {
    mockGetForOrder.mockResolvedValue({ data: makePhotos(3) });
    const onChange = vi.fn();

    render(
      <PhotoPicker
        orderId={1}
        selectedIds={['photo-1', 'photo-2']}
        onChange={onChange}
        max={2}
      />
    );

    const checkboxes = await screen.findAllByRole('checkbox');
    expect(checkboxes[0]).toBeEnabled(); // selected — stays clickable to deselect
    expect(checkboxes[1]).toBeEnabled(); // selected
    expect(checkboxes[2]).toBeDisabled(); // unselected, at cap

    expect(screen.getByText('Maximal 2 Fotos')).toBeInTheDocument();

    await userEvent.click(checkboxes[2]);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('disables every card when the disabled prop is set', async () => {
    mockGetForOrder.mockResolvedValue({ data: makePhotos(2) });
    const onChange = vi.fn();

    render(
      <PhotoPicker orderId={1} selectedIds={[]} onChange={onChange} disabled />
    );

    const checkboxes = await screen.findAllByRole('checkbox');
    checkboxes.forEach((cb) => expect(cb).toBeDisabled());

    await userEvent.click(checkboxes[0]);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('renders the empty state without throwing when the load fails', async () => {
    mockGetForOrder.mockRejectedValue(new Error('network down'));

    render(<PhotoPicker orderId={1} selectedIds={[]} onChange={vi.fn()} />);

    expect(
      await screen.findByText('Keine Fotos für diesen Auftrag vorhanden.')
    ).toBeInTheDocument();
    await waitFor(() => expect(mockLogError).toHaveBeenCalledWith('PhotoPicker.load', expect.any(Error)));
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });
});
