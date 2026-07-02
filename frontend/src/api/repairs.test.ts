import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockPost = vi.fn();
const mockGet = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();
vi.mock('./client', () => ({
  default: {
    post: (...a: unknown[]) => mockPost(...a),
    get: (...a: unknown[]) => mockGet(...a),
    put: (...a: unknown[]) => mockPut(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
}));

import { repairPhotoPath, repairPhotoThumbPath, repairsApi } from './repairs';
import type { IntakeChecklistItem } from '../types';

beforeEach(() => vi.clearAllMocks());

describe('repairsApi', () => {
  it('uploadPhoto sends multipart FormData with phase and no notes when omitted', async () => {
    mockPost.mockResolvedValue({ data: { id: 1 } });
    const file = new File(['x'], 'eingang.jpg', { type: 'image/jpeg' });
    await repairsApi.uploadPhoto(7, file, 'intake');

    const [url, body, config] = mockPost.mock.calls[0];
    expect(url).toBe('/repairs/7/photos');
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get('file')).toBe(file);
    expect((body as FormData).get('phase')).toBe('intake');
    expect((body as FormData).get('notes')).toBeNull();
    expect((config as { headers: Record<string, string> }).headers['Content-Type']).toBe(
      'multipart/form-data'
    );
  });

  it('uploadPhoto includes notes in the FormData when provided', async () => {
    mockPost.mockResolvedValue({ data: { id: 2 } });
    const file = new File(['x'], 'reparatur.jpg', { type: 'image/jpeg' });
    await repairsApi.uploadPhoto(7, file, 'during_repair', 'Krappen gerichtet');

    const body = mockPost.mock.calls[0][1] as FormData;
    expect(body.get('phase')).toBe('during_repair');
    expect(body.get('notes')).toBe('Krappen gerichtet');
  });

  it('deletePhoto calls DELETE on the photo endpoint', async () => {
    mockDelete.mockResolvedValue({});
    await repairsApi.deletePhoto(42);
    expect(mockDelete).toHaveBeenCalledWith('/repairs/photos/42');
  });

  it('updateIntakeChecklist PUTs the full items array', async () => {
    mockPut.mockResolvedValue({ data: { id: 7, intake_checklist: [] } });
    const items: IntakeChecklistItem[] = [
      { key: 'krappen', label: 'Krappen/Fassungen', status: 'open' },
      { key: 'gravuren', label: 'Gravuren', status: 'na', na_reason: 'Kein Gravurauftrag' },
    ];
    await repairsApi.updateIntakeChecklist(7, items);
    expect(mockPut).toHaveBeenCalledWith('/repairs/7/intake-checklist', { items });
  });

  it('addPhoto no longer exists (removed dead JSON-shape method)', () => {
    expect((repairsApi as Record<string, unknown>).addPhoto).toBeUndefined();
  });

  it('photo path helpers match backend routes', () => {
    expect(repairPhotoPath(9)).toBe('/repairs/photos/9');
    expect(repairPhotoThumbPath(9)).toBe('/repairs/photos/9/thumbnail');
  });
});
