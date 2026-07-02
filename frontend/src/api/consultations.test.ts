import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockPost = vi.fn();
const mockGet = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();
vi.mock('./client', () => ({
  default: {
    post: (...a: unknown[]) => mockPost(...a),
    get: (...a: unknown[]) => mockGet(...a),
    patch: (...a: unknown[]) => mockPatch(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
}));

import { consultationsApi, consultationPhotoThumbPath } from './consultations';

beforeEach(() => vi.clearAllMocks());

describe('consultationsApi', () => {
  it('uploadPhoto sends multipart FormData with kind and notes', async () => {
    mockPost.mockResolvedValue({ data: { id: 'u1' } });
    const file = new File(['x'], 'skizze.jpg', { type: 'image/jpeg' });
    await consultationsApi.uploadPhoto(7, file, 'sketch', 'Erste Idee');
    const [url, body, config] = mockPost.mock.calls[0];
    expect(url).toBe('/consultations/7/photos');
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get('kind')).toBe('sketch');
    expect((body as FormData).get('notes')).toBe('Erste Idee');
    expect((config as { headers: Record<string, string> }).headers['Content-Type']).toBe(
      'multipart/form-data'
    );
  });

  it('convert posts the target', async () => {
    mockPost.mockResolvedValue({ data: { id: 7, status: 'converted' } });
    await consultationsApi.convert(7, 'order');
    expect(mockPost).toHaveBeenCalledWith('/consultations/7/convert', { target: 'order' });
  });

  it('thumbnail path helper matches backend route', () => {
    expect(consultationPhotoThumbPath('abc')).toBe('/consultations/photos/abc/thumbnail');
  });
});
