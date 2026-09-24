// FE-02 / FE-03 regressions — scan-driven timer on a fresh device, and
// repair scans never touching the order with the same numeric id.
//
// FE-02: ScanOverlay always dispatches with activityId: null and nothing
// seeded localStorage, so start_timer / switch_timer always stopped at a
// warning toast. The handler must now ask for an activity (ActivityPicker
// via modal-stack) and send activity_id; cancelling yields a German error.
//
// FE-03: handlers ignored entity_type, so REPAIR:17 opened /orders/17 and
// start_timer booked labour on order 17. Time entries have no repair link
// yet, so timer actions on repairs must refuse without any API call.
//
// NOTE: localStorage is deliberately NOT pre-seeded here (fresh device).

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  default: {
    post: vi.fn(async () => ({ data: {} })),
    patch: vi.fn(async () => ({ data: {} })),
    get: vi.fn(async () => ({ data: {} })),
  },
}));

vi.mock('../lib/modal-stack', () => ({
  fireModal: vi.fn(),
}));

import apiClient from '../api/client';
import { fireModal } from '../lib/modal-stack';
import {
  ACTION_HANDLERS,
  type ActionHandlerContext,
} from '../components/scanner/ActionHandlers';
import { ActivityPickerModal } from '../components/scanner/ActivityPickerModal';
import type { ResolveResponse, Transport } from '../types/scanner';

const fireModalMock = fireModal as unknown as ReturnType<typeof vi.fn>;

function response(entityType: 'order' | 'repair', id: number): ResolveResponse {
  return {
    resolved: true,
    resolution_path: 'prefix',
    entity_type: entityType,
    entity_id: id,
    entity: { entity_type: entityType, entity_id: id, data: { id } },
    actions: [],
    status_hint: null,
  };
}

function ctxFor(
  resp: ResolveResponse,
  overrides?: Partial<ActionHandlerContext>,
): ActionHandlerContext {
  return {
    response: resp,
    scanContext: {
      running_timer_id: null,
      current_order_id: null,
      current_location: null,
      device_type: 'tablet',
      input_source: 'camera',
    },
    transport: {} as Transport,
    hooks: {
      navigate: vi.fn(),
      toast: vi.fn(),
      closeOverlay: vi.fn(),
      refreshTimer: vi.fn(async () => {}),
    },
    activityId: null,
    runningEntryId: null,
    userId: 5,
    ...overrides,
  };
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

describe('start_timer on a fresh device (FE-02)', () => {
  it('asks for an activity via ActivityPickerModal and sends activity_id', async () => {
    fireModalMock.mockResolvedValueOnce(12);
    const ctx = ctxFor(response('order', 42));

    await ACTION_HANDLERS.start_timer(ctx);

    expect(fireModalMock).toHaveBeenCalledWith(ActivityPickerModal, {});
    expect(apiClient.post).toHaveBeenCalledWith('/time-tracking/start', {
      order_id: 42,
      activity_id: 12,
      location: undefined,
    });
    expect(ctx.hooks.closeOverlay).toHaveBeenCalled();
  });

  it('remembers the chosen activity per user and skips the picker next time', async () => {
    fireModalMock.mockResolvedValueOnce(12);
    await ACTION_HANDLERS.start_timer(ctxFor(response('order', 42)));
    expect(localStorage.getItem('scanner_last_activity_id:5')).toBe('12');

    vi.clearAllMocks();
    await ACTION_HANDLERS.start_timer(ctxFor(response('order', 43)));
    expect(fireModalMock).not.toHaveBeenCalled();
    expect(apiClient.post).toHaveBeenCalledWith(
      '/time-tracking/start',
      expect.objectContaining({ order_id: 43, activity_id: 12 }),
    );
  });

  it("does not reuse another user's remembered activity", async () => {
    localStorage.setItem('scanner_last_activity_id:99', '3');
    fireModalMock.mockResolvedValueOnce(7);
    await ACTION_HANDLERS.start_timer(ctxFor(response('order', 42)));
    expect(fireModalMock).toHaveBeenCalled();
    expect(apiClient.post).toHaveBeenCalledWith(
      '/time-tracking/start',
      expect.objectContaining({ activity_id: 7 }),
    );
  });

  it('raises a clear German error and does not start when the picker is cancelled', async () => {
    fireModalMock.mockRejectedValueOnce(new Error('cancelled'));
    const ctx = ctxFor(response('order', 42));

    await expect(ACTION_HANDLERS.start_timer(ctx)).rejects.toThrow(
      /Keine Aktivität gewählt/,
    );
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it('switch_timer also asks for an activity and sends it to /switch', async () => {
    fireModalMock.mockResolvedValueOnce(4);
    const ctx = ctxFor(response('order', 42), { runningEntryId: 'e-1' });

    await ACTION_HANDLERS.switch_timer(ctx);

    expect(apiClient.post).toHaveBeenCalledWith(
      '/time-tracking/e-1/switch',
      expect.objectContaining({ new_order_id: 42, activity_id: 4 }),
      expect.anything(),
    );
  });
});

describe('repair scans never act on the order with the same id (FE-03)', () => {
  it('start_timer on a repair refuses without an API call or picker', async () => {
    const ctx = ctxFor(response('repair', 17), { activityId: 1 });
    await expect(ACTION_HANDLERS.start_timer(ctx)).rejects.toThrow(/Reparatur/);
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(fireModalMock).not.toHaveBeenCalled();
  });

  it('switch_timer on a repair refuses without an API call', async () => {
    const ctx = ctxFor(response('repair', 17), {
      activityId: 1,
      runningEntryId: 'e-1',
    });
    await expect(ACTION_HANDLERS.switch_timer(ctx)).rejects.toThrow(/Reparatur/);
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it('take_photo on a repair opens the repair, not /orders/17', async () => {
    const ctx = ctxFor(response('repair', 17));
    await ACTION_HANDLERS.take_photo(ctx);
    expect(ctx.hooks.navigate).toHaveBeenCalledWith('/repairs/17?action=take-photo');
  });

  it('take_photo on an order with the same number still opens the order', async () => {
    const ctx = ctxFor(response('order', 17));
    await ACTION_HANDLERS.take_photo(ctx);
    expect(ctx.hooks.navigate).toHaveBeenCalledWith('/orders/17?action=take-photo');
  });

  it('print_label on a repair routes to /repairs/17 (an existing route)', async () => {
    const ctx = ctxFor(response('repair', 17));
    await ACTION_HANDLERS.print_label(ctx);
    expect(ctx.hooks.navigate).toHaveBeenCalledWith('/repairs/17?action=print-label');
  });

  it('change_status on a repair does not open /orders/17', async () => {
    const ctx = ctxFor(response('repair', 17));
    await expect(ACTION_HANDLERS.change_status(ctx)).rejects.toThrow();
    expect(ctx.hooks.navigate).not.toHaveBeenCalled();
  });
});
