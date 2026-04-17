// ActionHandlers tests — Slice 11.
//
// Scope (plan §Slice 11 verification):
//   * Each handler dispatches the correct backend call + hooks side-effects.
//   * consume_material navigates to the order detail (Slice 11 scope — the
//     weight-entry + AlloyMismatchModal retry flow is exercised via the
//     exported `consumeWithMismatchRetry` primitive, not through the
//     handler directly, because V1.1 doesn't yet embed weight entry).
//   * switch_timer emits stop+start; on 409 TIMER_POSSIBLY_STALE shows the
//     warning toast placeholder and bails out (no start).
//   * punzierung_check fires PunzierungsCheckModal via modal-stack,
//     PATCHes /orders/{id} with the marks, toasts success.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Mock apiClient BEFORE importing ActionHandlers.
vi.mock('../api/client', () => ({
  default: {
    post: vi.fn(async () => ({ data: {} })),
    patch: vi.fn(async () => ({ data: {} })),
    get: vi.fn(async () => ({ data: {} })),
  },
}));

// Mock modal-stack so we can drive resolve/reject deterministically.
vi.mock('../lib/modal-stack', () => ({
  fireModal: vi.fn(),
}));

import apiClient from '../api/client';
import { fireModal } from '../lib/modal-stack';
import {
  ACTION_HANDLERS,
  buildActionExecution,
  consumeWithMismatchRetry,
  dispatchAction,
  type ActionHandlerContext,
} from '../components/scanner/ActionHandlers';
import type {
  ActionResult,
  ActionExecution,
  ResolveResponse,
  ScanContext,
  ScanEvent,
  Transport,
} from '../types/scanner';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

class StubTransport implements Transport {
  async resolve(): Promise<ResolveResponse> {
    return {
      resolved: false,
      resolution_path: 'unknown',
      entity_type: null,
      entity_id: null,
      entity: null,
      actions: [],
      status_hint: null,
    };
  }
  async logScan(_event: ScanEvent): Promise<void> {}
  async executeAction(_action: ActionExecution): Promise<ActionResult> {
    return { success: true };
  }
}

function baseContext(
  response: ResolveResponse,
  overrides?: Partial<ActionHandlerContext>,
): ActionHandlerContext {
  return {
    response,
    scanContext: {
      running_timer_id: null,
      current_order_id: null,
      current_location: null,
      device_type: 'desktop',
      input_source: 'manual',
    },
    transport: new StubTransport(),
    hooks: {
      navigate: vi.fn(),
      toast: vi.fn(),
      closeOverlay: vi.fn(),
      refreshTimer: vi.fn(async () => {}),
    },
    activityId: 1,
    runningEntryId: null,
    ...overrides,
  };
}

function orderResponse(id = 42): ResolveResponse {
  return {
    resolved: true,
    resolution_path: 'prefix',
    entity_type: 'order',
    entity_id: id,
    entity: {
      entity_type: 'order',
      entity_id: id,
      data: { id, title: 'Ring', status: 'in_progress' },
    },
    actions: [],
    status_hint: null,
  };
}

function metalResponse(id = 85): ResolveResponse {
  return {
    resolved: true,
    resolution_path: 'prefix',
    entity_type: 'metal_purchase',
    entity_id: id,
    entity: {
      entity_type: 'metal_purchase',
      entity_id: id,
      data: { id, metal_type: 'gold_18k', alloy: '585', lot_number: 'L1' },
    },
    actions: [],
    status_hint: null,
  };
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Registry + dispatch
// ---------------------------------------------------------------------------

describe('ACTION_HANDLERS registry', () => {
  it('registers all expected action IDs', () => {
    const expected = [
      'start_timer',
      'stop_timer',
      'switch_timer',
      'change_status',
      'change_location',
      'switch_activity',
      'log_interruption',
      'take_photo',
      'print_label',
      'open_entity',
      'consume_material',
      'punzierung_check',
    ];
    for (const id of expected) {
      expect(typeof ACTION_HANDLERS[id]).toBe('function');
    }
  });

  it('dispatchAction throws on unknown action', async () => {
    await expect(
      dispatchAction('no_such_action', baseContext(orderResponse())),
    ).rejects.toThrow(/Unbekannte Aktion/);
  });
});

// ---------------------------------------------------------------------------
// start_timer
// ---------------------------------------------------------------------------

describe('start_timer handler', () => {
  it('POSTs to /time-tracking/start with order_id + activity_id + location', async () => {
    const ctx = baseContext(orderResponse(7), {
      scanContext: {
        running_timer_id: null,
        current_order_id: null,
        current_location: 'Werkbank 1',
        device_type: 'tablet',
        input_source: 'camera',
      },
    });
    await ACTION_HANDLERS.start_timer(ctx);
    expect(apiClient.post).toHaveBeenCalledWith('/time-tracking/start', {
      order_id: 7,
      activity_id: 1,
      location: 'Werkbank 1',
    });
    expect(ctx.hooks.refreshTimer).toHaveBeenCalled();
    expect(ctx.hooks.closeOverlay).toHaveBeenCalled();
  });

  it('warns the user when no activity is available', async () => {
    const ctx = baseContext(orderResponse(7), { activityId: null });
    await ACTION_HANDLERS.start_timer(ctx);
    expect(ctx.hooks.toast).toHaveBeenCalled();
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it('throws if entity id is missing', async () => {
    const ctx = baseContext({
      ...orderResponse(1),
      entity: null,
      entity_id: null,
    });
    await expect(ACTION_HANDLERS.start_timer(ctx)).rejects.toThrow();
  });

  it('persists activity id to localStorage for next scan', async () => {
    const ctx = baseContext(orderResponse(7));
    await ACTION_HANDLERS.start_timer(ctx);
    expect(localStorage.getItem('scanner_last_activity_id')).toBe('1');
  });
});

// ---------------------------------------------------------------------------
// stop_timer
// ---------------------------------------------------------------------------

describe('stop_timer handler', () => {
  it('POSTs to /time-tracking/<id>/stop and refreshes', async () => {
    const ctx = baseContext(orderResponse(7), { runningEntryId: 'abc-123' });
    await ACTION_HANDLERS.stop_timer(ctx);
    expect(apiClient.post).toHaveBeenCalledWith(
      '/time-tracking/abc-123/stop',
      {},
    );
    expect(ctx.hooks.refreshTimer).toHaveBeenCalled();
  });

  it('throws when no running entry is set', async () => {
    const ctx = baseContext(orderResponse(7), { runningEntryId: null });
    await expect(ACTION_HANDLERS.stop_timer(ctx)).rejects.toThrow(
      /kein laufender/i,
    );
  });
});

// ---------------------------------------------------------------------------
// switch_timer
// ---------------------------------------------------------------------------

describe('switch_timer handler', () => {
  it('stops old timer then starts new one', async () => {
    const ctx = baseContext(orderResponse(99), {
      runningEntryId: 'running-1',
    });
    await ACTION_HANDLERS.switch_timer(ctx);
    // Called twice — stop then start.
    const calls = (apiClient.post as unknown as ReturnType<typeof vi.fn>).mock
      .calls;
    expect(calls[0][0]).toBe('/time-tracking/running-1/stop');
    expect(calls[1][0]).toBe('/time-tracking/start');
    expect(calls[1][1]).toEqual(
      expect.objectContaining({ order_id: 99, activity_id: 1 }),
    );
    expect(ctx.hooks.refreshTimer).toHaveBeenCalled();
    expect(ctx.hooks.closeOverlay).toHaveBeenCalled();
  });

  it('falls back to start_timer when no running entry is present', async () => {
    const ctx = baseContext(orderResponse(99), { runningEntryId: null });
    await ACTION_HANDLERS.switch_timer(ctx);
    const calls = (apiClient.post as unknown as ReturnType<typeof vi.fn>).mock
      .calls;
    // Only the start call should fire.
    expect(calls.length).toBe(1);
    expect(calls[0][0]).toBe('/time-tracking/start');
  });

  it('handles 409 TIMER_POSSIBLY_STALE by warning and bailing out', async () => {
    const err = {
      response: {
        status: 409,
        data: { detail: { code: 'TIMER_POSSIBLY_STALE' } },
      },
    };
    (apiClient.post as unknown as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(err)
      // subsequent start never called
      .mockResolvedValueOnce({ data: {} });
    const ctx = baseContext(orderResponse(99), {
      runningEntryId: 'running-1',
    });
    await ACTION_HANDLERS.switch_timer(ctx);
    expect(ctx.hooks.toast).toHaveBeenCalled();
    // Start was NOT attempted.
    const calls = (apiClient.post as unknown as ReturnType<typeof vi.fn>).mock
      .calls;
    expect(calls.length).toBe(1);
    expect(calls[0][0]).toBe('/time-tracking/running-1/stop');
  });

  it('rethrows non-stale stop errors', async () => {
    const err = {
      response: { status: 500, data: { detail: 'Internal' } },
    };
    (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      err,
    );
    const ctx = baseContext(orderResponse(99), { runningEntryId: 'running-1' });
    await expect(ACTION_HANDLERS.switch_timer(ctx)).rejects.toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// punzierung_check
// ---------------------------------------------------------------------------

describe('punzierung_check handler', () => {
  it('fires PunzierungsCheckModal and PATCHes /orders/<id> with marks', async () => {
    (fireModal as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      marks: ['feingehalt_750', 'meisterzeichen'],
    });
    const ctx = baseContext(orderResponse(42));
    await ACTION_HANDLERS.punzierung_check(ctx);
    expect(fireModal).toHaveBeenCalled();
    expect(apiClient.patch).toHaveBeenCalledWith('/orders/42', {
      punzierung_verified_marks: ['feingehalt_750', 'meisterzeichen'],
    });
    expect(ctx.hooks.toast).toHaveBeenCalledWith(
      expect.stringContaining('2 Punzen'),
      'success',
    );
    expect(ctx.hooks.closeOverlay).toHaveBeenCalled();
  });

  it('does nothing when the user cancels the modal', async () => {
    (fireModal as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('cancelled'),
    );
    const ctx = baseContext(orderResponse(42));
    await ACTION_HANDLERS.punzierung_check(ctx);
    expect(apiClient.patch).not.toHaveBeenCalled();
    expect(ctx.hooks.closeOverlay).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// consume_material
// ---------------------------------------------------------------------------

describe('consume_material handler', () => {
  it('warns and closes when no order is in context', async () => {
    const ctx = baseContext(metalResponse(85));
    await ACTION_HANDLERS.consume_material(ctx);
    expect(ctx.hooks.toast).toHaveBeenCalled();
    expect(ctx.hooks.navigate).not.toHaveBeenCalled();
  });

  it('navigates to the order detail consume-material flow when order is set', async () => {
    const ctx = baseContext(metalResponse(85), {
      scanContext: {
        running_timer_id: 'x',
        current_order_id: 42,
        current_location: null,
        device_type: 'desktop',
        input_source: 'manual',
      },
    });
    await ACTION_HANDLERS.consume_material(ctx);
    expect(ctx.hooks.navigate).toHaveBeenCalledWith(
      '/orders/42?action=consume-material&metal_purchase_id=85',
    );
    expect(ctx.hooks.closeOverlay).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// consumeWithMismatchRetry — exported primitive
// ---------------------------------------------------------------------------

describe('consumeWithMismatchRetry', () => {
  it('returns {overridden:false} when the initial POST succeeds', async () => {
    (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      { data: {} },
    );
    const result = await consumeWithMismatchRetry({
      metalPurchaseId: 85,
      metalAlloy: '585',
      orderId: 42,
      orderAlloy: '750',
      weightGrams: 12.5,
      metalType: 'gold_14k',
    });
    expect(result.overridden).toBe(false);
    expect(fireModal).not.toHaveBeenCalled();
  });

  it('on 409 ALLOY_MISMATCH fires AlloyMismatchModal and retries with override', async () => {
    (apiClient.post as unknown as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce({
        response: { status: 409, data: { detail: { code: 'ALLOY_MISMATCH' } } },
      })
      .mockResolvedValueOnce({ data: {} });
    (fireModal as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      override_reason_category: 'kleinteil',
      override_reason: 'Restmaterial',
    });
    const result = await consumeWithMismatchRetry({
      metalPurchaseId: 85,
      metalAlloy: '585',
      orderId: 42,
      orderAlloy: '750',
      weightGrams: 12.5,
      metalType: 'gold_14k',
    });
    expect(result.overridden).toBe(true);
    const calls = (apiClient.post as unknown as ReturnType<typeof vi.fn>).mock
      .calls;
    const retryPayload = calls[1][1] as Record<string, unknown>;
    expect(retryPayload.alloy_override).toBe(true);
    expect(retryPayload.override_reason).toBe('Restmaterial');
    expect(retryPayload.override_reason_category).toBe('kleinteil');
  });

  it('throws "Entnahme abgebrochen." when the user cancels the modal', async () => {
    (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      {
        response: { status: 409, data: { detail: { code: 'ALLOY_MISMATCH' } } },
      },
    );
    (fireModal as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('cancelled'),
    );
    await expect(
      consumeWithMismatchRetry({
        metalPurchaseId: 85,
        metalAlloy: '585',
        orderId: 42,
        orderAlloy: '750',
        weightGrams: 12.5,
        metalType: 'gold_14k',
      }),
    ).rejects.toThrow(/abgebrochen/i);
  });
});

// ---------------------------------------------------------------------------
// Nav-only handlers
// ---------------------------------------------------------------------------

describe('navigation-only handlers', () => {
  it('change_status navigates to /orders/<id>?edit=status', async () => {
    const ctx = baseContext(orderResponse(42));
    await ACTION_HANDLERS.change_status(ctx);
    expect(ctx.hooks.navigate).toHaveBeenCalledWith(
      '/orders/42?edit=status',
    );
    expect(ctx.hooks.closeOverlay).toHaveBeenCalled();
  });

  it('change_location navigates to /orders/<id>?edit=location', async () => {
    const ctx = baseContext(orderResponse(42));
    await ACTION_HANDLERS.change_location(ctx);
    expect(ctx.hooks.navigate).toHaveBeenCalledWith(
      '/orders/42?edit=location',
    );
  });

  it('open_entity routes by entity_type', async () => {
    const ctx = baseContext(orderResponse(42));
    await ACTION_HANDLERS.open_entity(ctx);
    expect(ctx.hooks.navigate).toHaveBeenCalledWith('/orders/42');
  });

  it('take_photo navigates with action=take-photo', async () => {
    const ctx = baseContext(orderResponse(42));
    await ACTION_HANDLERS.take_photo(ctx);
    expect(ctx.hooks.navigate).toHaveBeenCalledWith(
      '/orders/42?action=take-photo',
    );
  });
});

// ---------------------------------------------------------------------------
// buildActionExecution — forward-compat contract
// ---------------------------------------------------------------------------

describe('buildActionExecution', () => {
  it('builds an ActionExecution with a v4 UUID idempotency key', () => {
    const entity = {
      entity_type: 'order',
      entity_id: 42,
      data: { id: 42 },
    };
    const exec = buildActionExecution('start_timer', entity, {
      activity_id: 1,
    });
    expect(exec.action_id).toBe('start_timer');
    expect(exec.entity_type).toBe('order');
    expect(exec.entity_id).toBe(42);
    expect(exec.payload).toEqual({ activity_id: 1 });
    // crypto.randomUUID() returns a canonical v4 UUID.
    expect(exec.idempotency_key).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  });
});
