// scrap-gold API client contract tests — DOM-19.
//
// Before this fix, ScrapGoldItemCreateInput.alloy was typed `number` and
// ScrapGoldTab called `scrapGoldApi.addItem(..., { alloy: Number(alloy) })`.
// The backend's Pydantic schema (goldsmith_erp/models/scrap_gold.py,
// ScrapGoldItemCreate.alloy) has only ever accepted a string alloy code
// (now the AlloyType enum) — so every add-item request 422'd and the UI
// could never add an Altgold item at all.
//
// These tests pin the exact payload shape the backend accepts: `alloy` is
// sent through untouched as the string the caller passed in, never coerced
// to a number.
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockPost = vi.fn();
const mockGet = vi.fn();
const mockDelete = vi.fn();
vi.mock('./client', () => ({
  default: {
    post: (...a: unknown[]) => mockPost(...a),
    get: (...a: unknown[]) => mockGet(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
}));

import { scrapGoldApi } from './scrap-gold';

beforeEach(() => vi.clearAllMocks());

describe('scrapGoldApi.addItem', () => {
  it('sends the alloy code as a string, unmodified — the exact backend contract', async () => {
    mockPost.mockResolvedValue({
      data: { id: 1, scrap_gold_id: 3, description: 'Alter Ehering', alloy: '585', weight_g: 15, fine_content_g: 8.775, photo_path: null, created_at: '2026-09-25T00:00:00Z' },
    });

    await scrapGoldApi.addItem(3, { description: 'Alter Ehering', alloy: '585', weight_g: 15 });

    expect(mockPost).toHaveBeenCalledWith('/scrap-gold/3/items', {
      description: 'Alter Ehering',
      alloy: '585',
      weight_g: 15,
    });
    // The historical bug: alloy silently coerced to a number before this
    // call ever reached the network layer.
    const [, body] = mockPost.mock.calls[0];
    expect(typeof (body as { alloy: unknown }).alloy).toBe('string');
  });

  it('sends a silver alloy code with its "ag" prefix intact (never a bare permille number)', async () => {
    mockPost.mockResolvedValue({
      data: { id: 2, scrap_gold_id: 3, description: 'Silberkette', alloy: 'ag925', weight_g: 10, fine_content_g: 9.25, photo_path: null, created_at: '2026-09-25T00:00:00Z' },
    });

    await scrapGoldApi.addItem(3, { description: 'Silberkette', alloy: 'ag925', weight_g: 10 });

    expect(mockPost).toHaveBeenCalledWith('/scrap-gold/3/items', {
      description: 'Silberkette',
      alloy: 'ag925',
      weight_g: 10,
    });
  });

  it('round-trips the alloy code from the response as a string (no numeric alloy anywhere)', async () => {
    mockPost.mockResolvedValue({
      data: {
        id: 4,
        scrap_gold_id: 3,
        description: 'Platinring',
        alloy: 'pt950',
        weight_g: 20,
        fine_content_g: 19,
        photo_path: null,
        created_at: '2026-09-25T00:00:00Z',
      },
    });

    const result = await scrapGoldApi.addItem(3, {
      description: 'Platinring',
      alloy: 'pt950',
      weight_g: 20,
    });

    expect(result.alloy).toBe('pt950');
    expect(typeof result.alloy).toBe('string');
  });
});

describe('scrapGoldApi.calculateAlloy', () => {
  it('passes the alloy code through as a string query param', async () => {
    mockGet.mockResolvedValue({
      data: { alloy: '750', weight_g: 8, fine_content_g: 6.0, fine_content_percent: 75 },
    });

    await scrapGoldApi.calculateAlloy('750', 8);

    expect(mockGet).toHaveBeenCalledWith('/scrap-gold/alloy-calculator', {
      params: { alloy: '750', weight_g: 8 },
    });
  });
});
