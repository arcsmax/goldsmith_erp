// PhotoUpload — camera/upload control for the order Fotos tab (W2-01).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createTestQueryClient, renderWithQuery } from '../../test/queryWrapper';
import { queryKeys } from '../../api/queryKeys';

const mocks = vi.hoisted(() => ({ upload: vi.fn() }));
vi.mock('../../api/photos', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return {
    ...actual,
    photosApi: { upload: mocks.upload },
  };
});

import { PhotoUpload } from './PhotoUpload';

function jpeg(name: string, bytes = 3): File {
  return new File(['x'.repeat(bytes)], name, { type: 'image/jpeg' });
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('PhotoUpload', () => {
  it('renders a large camera input for multiple images', () => {
    renderWithQuery(<PhotoUpload orderId={42} onUploaded={vi.fn()} />);

    const input = screen.getByLabelText('Foto aufnehmen');
    expect(input).toHaveAttribute('type', 'file');
    expect(input).toHaveAttribute('accept', 'image/*');
    expect(input).toHaveAttribute('capture', 'environment');
    expect(input).toHaveAttribute('multiple');
  });

  it('uploads every selected file and reports each new photo', async () => {
    const onUploaded = vi.fn();
    mocks.upload
      .mockResolvedValueOnce({ id: 'p-1' })
      .mockResolvedValueOnce({ id: 'p-2' });
    renderWithQuery(<PhotoUpload orderId={42} onUploaded={onUploaded} />);

    const first = jpeg('a.jpg');
    const second = jpeg('b.jpg');
    await userEvent.upload(screen.getByLabelText('Foto aufnehmen'), [first, second]);

    await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(2));
    expect(mocks.upload).toHaveBeenNthCalledWith(1, 42, first, expect.objectContaining({
      onProgress: expect.any(Function),
    }));
    expect(mocks.upload).toHaveBeenNthCalledWith(2, 42, second, expect.anything());
    expect(onUploaded).toHaveBeenNthCalledWith(1, { id: 'p-1' });
    expect(await screen.findByRole('status')).toHaveTextContent('2 Fotos hochgeladen');
  });

  it('shows the backend German message on 422 and keeps going', async () => {
    const onUploaded = vi.fn();
    mocks.upload
      .mockRejectedValueOnce({
        response: { status: 422, data: { detail: 'Ungültiges Dateiformat. Erlaubt: JPEG, PNG, WEBP.' } },
      })
      .mockResolvedValueOnce({ id: 'p-2' });
    renderWithQuery(<PhotoUpload orderId={42} onUploaded={onUploaded} />);

    await userEvent.upload(screen.getByLabelText('Foto aufnehmen'), [jpeg('a.jpg'), jpeg('b.jpg')]);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'a.jpg: Ungültiges Dateiformat. Erlaubt: JPEG, PNG, WEBP.'
    );
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith({ id: 'p-2' }));
  });

  it('shows the backend German message on 413', async () => {
    mocks.upload.mockRejectedValueOnce({
      response: { status: 413, data: { detail: 'Anfrage zu groß. Maximum: 10 MB.' } },
    });
    renderWithQuery(<PhotoUpload orderId={42} onUploaded={vi.fn()} />);

    await userEvent.upload(screen.getByLabelText('Foto aufnehmen'), jpeg('gross.jpg'));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'gross.jpg: Anfrage zu groß. Maximum: 10 MB.'
    );
  });

  it('rejects a file over 8 MB before uploading', async () => {
    renderWithQuery(<PhotoUpload orderId={42} onUploaded={vi.fn()} />);
    const big = jpeg('riesig.jpg');
    Object.defineProperty(big, 'size', { value: 9 * 1024 * 1024 });

    await userEvent.upload(screen.getByLabelText('Foto aufnehmen'), big);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'riesig.jpg: Foto ist zu groß. Maximum: 8 MB.'
    );
    expect(mocks.upload).not.toHaveBeenCalled();
  });

  it('opens the file picker once when autoOpen is set', () => {
    const clickSpy = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => {});
    const onAutoOpened = vi.fn();

    const { rerender } = renderWithQuery(
      <PhotoUpload orderId={42} onUploaded={vi.fn()} autoOpen onAutoOpened={onAutoOpened} />
    );
    rerender(<PhotoUpload orderId={42} onUploaded={vi.fn()} autoOpen onAutoOpened={onAutoOpened} />);

    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(onAutoOpened).toHaveBeenCalledTimes(1);
  });

  it('appends the new photo to the cached photo list and refreshes the Verlauf', async () => {
    mocks.upload.mockResolvedValueOnce({ id: 'p-2' });
    const client = createTestQueryClient();
    client.setQueryData(queryKeys.orders.photos(42), [{ id: 'p-1' }]);
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    renderWithQuery(<PhotoUpload orderId={42} onUploaded={vi.fn()} />, { client });

    await userEvent.upload(screen.getByLabelText('Foto aufnehmen'), jpeg('a.jpg'));

    await waitFor(() =>
      expect(client.getQueryData(queryKeys.orders.photos(42))).toEqual([{ id: 'p-1' }, { id: 'p-2' }]),
    );
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.orders.timeline(42) });
  });
});
