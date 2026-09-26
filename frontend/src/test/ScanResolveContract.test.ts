// Regression test — scan/resolve response contract (2026-09 audit).
//
// The frontend's hand-written `ResolveResponse` type used to nest
// `entity_type` / `entity_id` / a `data` record INSIDE `entity`
// (`ResolvedEntity`). The real backend (and the generated OpenAPI type,
// `components["schemas"]["ResolveResponse"]` in api/generated/schema.d.ts)
// puts `entity_type` / `entity_id` at the TOP level and makes `entity` the
// role-filtered projection record itself — verified live against
// `POST /api/v1/scan/resolve` for `ORDER:1`.
//
// That mismatch made every id-based action read `undefined` off
// `ctx.response.entity.entity_type` / `.entity_id`, so `open_entity` always
// threw "Ziel nicht verfügbar." and id-carrying POSTs sent `undefined`.
//
// This test pins the exact real response body so a future regression on
// the shape fails loudly here instead of only in production.

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  default: {
    post: vi.fn(async () => ({ data: {} })),
    patch: vi.fn(async () => ({ data: {} })),
    get: vi.fn(async () => ({ data: {} })),
  },
}));

import apiClient from '../api/client';
import {
  ACTION_HANDLERS,
  type ActionHandlerContext,
} from '../components/scanner/ActionHandlers';
import type { PickedLocation } from '../components/scanner/LocationPrompt';
import type { ResolveResponse, Transport } from '../types/scanner';

// The exact backend response body for `ORDER:1` (see module doc above).
const REAL_BACKEND_RESPONSE: ResolveResponse = {
  resolved: true,
  resolution_path: 'prefix',
  entity_type: 'order',
  entity_id: 1,
  entity: {
    id: 1,
    title: 'Verlobungsring Solitaer Weber',
    status: 'in_progress',
    current_location: 'Werkbank 1',
    customer_id: 3,
    order_type: 'ring',
  },
  actions: [
    { id: 'start_timer', label: 'Timer starten', icon: 'play', primary: true },
    { id: 'open_entity', label: 'Öffnen', icon: 'link', primary: false },
  ],
  status_hint: 'In Bearbeitung',
};

function baseContext(overrides?: Partial<ActionHandlerContext>): ActionHandlerContext {
  return {
    response: REAL_BACKEND_RESPONSE,
    scanContext: {
      running_timer_id: null,
      current_order_id: null,
      current_location: 'Werkbank 1',
      device_type: 'desktop',
      input_source: 'manual',
    },
    transport: {} as Transport,
    hooks: {
      navigate: vi.fn(),
      toast: vi.fn(),
      closeOverlay: vi.fn(),
      refreshTimer: vi.fn(async () => {}),
      promptLocation: vi.fn(
        async (): Promise<PickedLocation | null> => ({ id: 5, name: 'Werkbank 2' }),
      ),
    },
    activityId: 7,
    runningEntryId: null,
    ...overrides,
  };
}

describe('scan/resolve real response contract', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('open_entity navigates to /orders/1', async () => {
    const ctx = baseContext();
    await ACTION_HANDLERS.open_entity(ctx);
    expect(ctx.hooks.navigate).toHaveBeenCalledWith('/orders/1');
  });

  it('start_timer POSTs order_id: 1 to /time-tracking/start', async () => {
    const ctx = baseContext();
    await ACTION_HANDLERS.start_timer(ctx);
    expect(apiClient.post).toHaveBeenCalledWith('/time-tracking/start', {
      order_id: 1,
      activity_id: 7,
      location: 'Werkbank 1',
    });
  });

  it('change_location POSTs to /orders/1/location', async () => {
    const ctx = baseContext();
    await ACTION_HANDLERS.change_location(ctx);
    expect(apiClient.post).toHaveBeenCalledWith('/orders/1/location', {
      location: 'Werkbank 2',
      location_id: 5,
    });
  });
});
