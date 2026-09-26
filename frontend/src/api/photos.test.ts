// photosApi — order photo upload contract (W2-01, FE-13).
//
// Backend: POST /orders/{order_id}/photos, multipart field `file`, optional
// `notes` (routers/photos.py). 413 comes from the request-size middleware,
// 422 from PhotoValidationError (German detail string).
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));
vi.mock('./client', () => ({ default: { post: mocks.post, get: mocks.get } }));

import {
  MAX_PHOTO_MB,
  getPhotoUploadErrorMessage,
  photoFilePath,
  photoThumbnailPath,
  photosApi,
} from './photos';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('photosApi.upload', () => {
  it('posts the file as multipart form data to /orders/{id}/photos', async () => {
    const photo = { id: 'p-1', order_id: 42, file_path: 'x', timestamp: 't', taken_by: 1 };
    mocks.post.mockResolvedValue({ data: photo });
    const file = new File(['abc'], 'ring.jpg', { type: 'image/jpeg' });

    const result = await photosApi.upload(42, file, { notes: 'Rohling' });

    expect(result).toEqual(photo);
    const [url, body, config] = mocks.post.mock.calls[0];
    expect(url).toBe('/orders/42/photos');
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get('file')).toBe(file);
    expect((body as FormData).get('notes')).toBe('Rohling');
    expect(config.headers).toEqual({ 'Content-Type': 'multipart/form-data' });
  });

  it('omits notes when none are given and reports progress in percent', async () => {
    mocks.post.mockImplementation(async (_url, _body, config) => {
      config.onUploadProgress({ loaded: 50, total: 200 });
      return { data: { id: 'p-2' } };
    });
    const onProgress = vi.fn();
    const file = new File(['abc'], 'ring.jpg', { type: 'image/jpeg' });

    await photosApi.upload(7, file, { onProgress });

    const body = mocks.post.mock.calls[0][1] as FormData;
    expect(body.has('notes')).toBe(false);
    expect(onProgress).toHaveBeenCalledWith(25);
  });
});

describe('photo URLs', () => {
  it('builds the authenticated thumbnail and file paths', () => {
    expect(photoThumbnailPath('abc')).toBe('/photos/abc/thumbnail');
    expect(photoFilePath('abc')).toBe('/photos/abc/file');
  });
});

describe('getPhotoUploadErrorMessage', () => {
  it('shows the backend German message for 413', () => {
    const err = { response: { status: 413, data: { detail: 'Anfrage zu groß. Maximum: 10 MB.' } } };
    expect(getPhotoUploadErrorMessage(err)).toBe('Anfrage zu groß. Maximum: 10 MB.');
  });

  it('falls back to a German size message for a 413 without detail', () => {
    const err = { response: { status: 413, data: '<html>' } };
    expect(getPhotoUploadErrorMessage(err)).toBe(
      `Foto ist zu groß. Maximum: ${MAX_PHOTO_MB} MB.`
    );
  });

  it('shows the backend German message for 422', () => {
    const err = {
      response: { status: 422, data: { detail: 'Ungültiges Dateiformat. Erlaubt: JPEG, PNG, WEBP.' } },
    };
    expect(getPhotoUploadErrorMessage(err)).toBe(
      'Ungültiges Dateiformat. Erlaubt: JPEG, PNG, WEBP.'
    );
  });

  it('falls back to a German format message for a 422 with a validation list', () => {
    const err = { response: { status: 422, data: { detail: [{ msg: 'field required' }] } } };
    expect(getPhotoUploadErrorMessage(err)).toBe(
      'Foto konnte nicht verarbeitet werden. Erlaubt sind JPEG, PNG und WEBP.'
    );
  });

  it('explains a network failure in German', () => {
    expect(getPhotoUploadErrorMessage(new Error('Network Error'))).toBe(
      'Keine Verbindung zum Server. Foto wurde nicht hochgeladen.'
    );
  });
});
