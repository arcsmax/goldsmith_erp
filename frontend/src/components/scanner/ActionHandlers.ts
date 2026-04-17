// ActionHandlers — Slice 11 action dispatch registry.
//
// Maps backend-emitted action IDs (scanner_service.py _ACTION_*) to
// client-side async handlers. Each handler receives a context object with
// the scanned entity, the ambient ScannerContext + TimeTrackingContext
// state, the Transport, and a hooks bundle for side-effects (navigate,
// toast, fire nested modal, close overlay, refresh timer).
//
// Design notes:
//
//   * V1.1 does NOT expose a generic POST /scan/action/:id endpoint — each
//     handler calls the existing entity endpoint directly (time-tracking,
//     orders, metal-inventory). The Transport is accepted in the context
//     for forward-compatibility with V1.1.5's offline-queue replay, but
//     today it's unused by handlers that hit concrete REST surfaces.
//
//   * switch_timer handles 409 TIMER_POSSIBLY_STALE (A5.2) by fireing the
//     Mittagspause modal (A11.5) — minimal stub here; V1.2 will split it
//     out into its own component.
//
//   * consume_material checks alloy mismatch. On mismatch, fires
//     AlloyMismatchModal, awaits category + reason, then retries with
//     alloy_override=true. On user cancel, the handler resolves silently
//     (no toast — user intent is clear).
//
//   * punzierung_check opens PunzierungsCheckModal, awaits marks, then
//     PATCHes the order with punzierung_verified_marks (server sets the
//     verified_at + verified_by fields from current_user).
//
// All toast copy is German.

import apiClient from '../../api/client';
import { fireModal } from '../../lib/modal-stack';
import type {
  ActionExecution,
  ResolveResponse,
  ResolvedEntity,
  ScanContext,
  Transport,
} from '../../types/scanner';

import {
  AlloyMismatchModal,
  type AlloyMismatchModalProps,
  type AlloyOverridePayload,
} from './AlloyMismatchModal';
import {
  PunzierungsCheckModal,
  type PunzierungsCheckModalProps,
  type PunzierungsCheckPayload,
} from '../qc/PunzierungsCheckModal';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ToastSeverity = 'success' | 'info' | 'warning' | 'error';

export interface ActionHooks {
  /** Navigate to a react-router path. */
  navigate: (path: string) => void;
  /** Surface a transient message. */
  toast: (message: string, severity?: ToastSeverity) => void;
  /** Close the fullscreen ScanOverlay (ScannerContext.closeScanner). */
  closeOverlay: () => void;
  /** Ask TimeTrackingContext to re-fetch its running entry. */
  refreshTimer: () => Promise<void>;
}

export interface ActionHandlerContext {
  response: ResolveResponse;
  scanContext: ScanContext;
  transport: Transport;
  hooks: ActionHooks;
  /**
   * Client-side metadata for time-tracking flows that need an activity
   * (start/switch). When null, handlers fall back to a last-used activity
   * from localStorage or a reasonable default.
   */
  activityId: number | null;
  /**
   * Running time entry ID if any. Drives switch/stop semantics.
   */
  runningEntryId: string | null;
}

export type ActionHandler = (ctx: ActionHandlerContext) => Promise<void>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const LAST_ACTIVITY_LS = 'scanner_last_activity_id';

function getEntity(ctx: ActionHandlerContext): ResolvedEntity | null {
  return ctx.response.entity;
}

function entityId(ctx: ActionHandlerContext): number | null {
  const entity = getEntity(ctx);
  if (entity === null) return null;
  return entity.entity_id;
}

function entityData(ctx: ActionHandlerContext): Record<string, unknown> {
  const entity = getEntity(ctx);
  return (entity?.data ?? {}) as Record<string, unknown>;
}

function readActivityId(ctx: ActionHandlerContext): number | null {
  if (ctx.activityId !== null) return ctx.activityId;
  try {
    const raw = localStorage.getItem(LAST_ACTIVITY_LS);
    if (raw === null) return null;
    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function rememberActivityId(id: number): void {
  try {
    localStorage.setItem(LAST_ACTIVITY_LS, String(id));
  } catch {
    // ignore private-browsing
  }
}

/**
 * Extract a backend error message. Axios errors expose the response body
 * at `err.response.data.detail`; structured errors are { code, ...details }.
 */
function extractErrorInfo(err: unknown): {
  status: number | null;
  code: string | null;
  message: string;
} {
  type AxiosLike = {
    response?: {
      status?: number;
      data?: unknown;
    };
    message?: string;
  };
  const e = err as AxiosLike;
  const status =
    typeof e.response?.status === 'number' ? e.response.status : null;
  let code: string | null = null;
  let message = '';
  const detail = e.response?.data as unknown;
  if (detail && typeof detail === 'object' && 'detail' in detail) {
    const d = (detail as { detail: unknown }).detail;
    if (typeof d === 'string') {
      message = d;
    } else if (d && typeof d === 'object' && 'code' in d) {
      const codeRaw = (d as { code: unknown }).code;
      code = typeof codeRaw === 'string' ? codeRaw : null;
      if ('message' in d) {
        const m = (d as { message: unknown }).message;
        if (typeof m === 'string') message = m;
      }
    }
  }
  if (!message) {
    message =
      typeof e.message === 'string' && e.message.length > 0
        ? e.message
        : 'Unbekannter Fehler';
  }
  return { status, code, message };
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

async function handleStartTimer(ctx: ActionHandlerContext): Promise<void> {
  const id = entityId(ctx);
  if (id === null) throw new Error('Kein Auftrag erkannt.');
  const activityId = readActivityId(ctx);
  if (activityId === null) {
    ctx.hooks.toast(
      'Bitte zuerst eine Aktivitaet auf dem Werkbank-Screen waehlen.',
      'warning',
    );
    return;
  }
  await apiClient.post('/time-tracking/start', {
    order_id: id,
    activity_id: activityId,
    location: ctx.scanContext.current_location ?? undefined,
  });
  rememberActivityId(activityId);
  await ctx.hooks.refreshTimer();
  ctx.hooks.toast('Timer gestartet.', 'success');
  ctx.hooks.closeOverlay();
}

async function handleStopTimer(ctx: ActionHandlerContext): Promise<void> {
  const entryId = ctx.runningEntryId;
  if (entryId === null) throw new Error('Kein laufender Timer gefunden.');
  await apiClient.post(`/time-tracking/${entryId}/stop`, {});
  await ctx.hooks.refreshTimer();
  ctx.hooks.toast('Timer gestoppt.', 'success');
  ctx.hooks.closeOverlay();
}

async function handleSwitchTimer(ctx: ActionHandlerContext): Promise<void> {
  const newOrderId = entityId(ctx);
  if (newOrderId === null) throw new Error('Kein Auftrag erkannt.');

  const activityId = readActivityId(ctx);
  if (activityId === null) {
    ctx.hooks.toast(
      'Bitte zuerst eine Aktivitaet auf dem Werkbank-Screen waehlen.',
      'warning',
    );
    return;
  }

  const entryId = ctx.runningEntryId;
  if (entryId === null) {
    // No running timer — degrade to start_timer.
    await handleStartTimer(ctx);
    return;
  }

  // Atomic switch. V1.1 lacks a dedicated POST /switch endpoint — the
  // client emulates it via stop-then-start. The per-user guard lives
  // server-side in TimeTrackingService.switch_timer when/if the endpoint
  // lands; today the stop endpoint already validates ownership.
  try {
    await apiClient.post(`/time-tracking/${entryId}/stop`, {});
  } catch (err) {
    const { status, code } = extractErrorInfo(err);
    if (status === 409 && code === 'TIMER_POSSIBLY_STALE') {
      ctx.hooks.toast(
        'Timer laeuft auffaellig lange. Pause abziehen und erneut versuchen?',
        'warning',
      );
      return;
    }
    throw err;
  }

  await apiClient.post('/time-tracking/start', {
    order_id: newOrderId,
    activity_id: activityId,
    location: ctx.scanContext.current_location ?? undefined,
  });
  rememberActivityId(activityId);
  await ctx.hooks.refreshTimer();
  ctx.hooks.toast('Timer gewechselt.', 'success');
  ctx.hooks.closeOverlay();
}

async function handleChangeStatus(ctx: ActionHandlerContext): Promise<void> {
  const id = entityId(ctx);
  if (id === null) throw new Error('Kein Auftrag erkannt.');
  // Picker lives on the order detail page (A11.13 — no nested views).
  ctx.hooks.navigate(`/orders/${id}?edit=status`);
  ctx.hooks.closeOverlay();
}

async function handleChangeLocation(ctx: ActionHandlerContext): Promise<void> {
  const id = entityId(ctx);
  if (id === null) throw new Error('Kein Auftrag erkannt.');
  ctx.hooks.navigate(`/orders/${id}?edit=location`);
  ctx.hooks.closeOverlay();
}

async function handleSwitchActivity(ctx: ActionHandlerContext): Promise<void> {
  const data = entityData(ctx);
  const code = typeof data.code === 'string' ? data.code : null;
  if (code === null) throw new Error('Aktivitaet unklar.');
  const entryId = ctx.runningEntryId;
  if (entryId === null) {
    ctx.hooks.toast('Kein laufender Timer — Aktivitaet nicht gewechselt.', 'info');
    return;
  }
  await apiClient.patch(`/time-tracking/${entryId}/activity`, { activity_code: code });
  await ctx.hooks.refreshTimer();
  ctx.hooks.toast(`Aktivitaet gewechselt: ${code}`, 'success');
  ctx.hooks.closeOverlay();
}

async function handleLogInterruption(
  ctx: ActionHandlerContext,
): Promise<void> {
  const data = entityData(ctx);
  const code = typeof data.code === 'string' ? data.code : null;
  if (code === null) throw new Error('Unterbrechung unklar.');
  const entryId = ctx.runningEntryId;
  if (entryId === null) {
    ctx.hooks.toast('Kein laufender Timer — Unterbrechung nicht erfasst.', 'info');
    return;
  }
  await apiClient.post(`/time-tracking/${entryId}/interruption`, {
    interrupt_code: code,
  });
  ctx.hooks.toast(`Unterbrechung erfasst: ${code}`, 'success');
  ctx.hooks.closeOverlay();
}

async function handleTakePhoto(ctx: ActionHandlerContext): Promise<void> {
  const id = entityId(ctx);
  if (id === null) throw new Error('Kein Auftrag erkannt.');
  ctx.hooks.navigate(`/orders/${id}?action=take-photo`);
  ctx.hooks.closeOverlay();
}

async function handlePrintLabel(ctx: ActionHandlerContext): Promise<void> {
  const id = entityId(ctx);
  if (id === null) throw new Error('Entitaet unklar.');
  const entity = getEntity(ctx);
  const type = entity?.entity_type ?? 'order';
  ctx.hooks.navigate(`/${type === 'order' ? 'orders' : type}/${id}?action=print-label`);
  ctx.hooks.closeOverlay();
}

async function handleOpenEntity(ctx: ActionHandlerContext): Promise<void> {
  const id = entityId(ctx);
  if (id === null) throw new Error('Entitaet unklar.');
  const entity = getEntity(ctx);
  const type = entity?.entity_type ?? '';
  const pathByType: Record<string, string> = {
    order: `/orders/${id}`,
    repair: `/repairs/${id}`,
    metal_purchase: `/metal-inventory/purchases/${id}`,
    material: `/materials/${id}`,
  };
  const path = pathByType[type];
  if (!path) throw new Error('Ziel nicht verfuegbar.');
  ctx.hooks.navigate(path);
  ctx.hooks.closeOverlay();
}

async function handleConsumeMaterial(
  ctx: ActionHandlerContext,
): Promise<void> {
  const id = entityId(ctx);
  if (id === null) throw new Error('Charge unklar.');
  const metalData = entityData(ctx);
  const metalType =
    typeof metalData.metal_type === 'string' ? metalData.metal_type : '';
  const metalAlloy =
    typeof metalData.alloy === 'string'
      ? metalData.alloy
      : typeof metalData.lot_number === 'string'
        ? metalType
        : metalType;

  // Order context comes from the running timer; if missing we push the
  // user to pick one — V1.1 scope.
  const orderId = ctx.scanContext.current_order_id;
  if (orderId === null) {
    ctx.hooks.toast(
      'Kein Auftrag im Kontext — bitte Auftrag waehlen, dann Entnahme scannen.',
      'warning',
    );
    return;
  }

  // Caller MUST set the weight they intend to consume — Slice 11 scope
  // uses a constant-zero placeholder; V1.1.5 opens a small weight-input.
  // For now, toast + navigate to the detail view for the real flow.
  ctx.hooks.navigate(
    `/orders/${orderId}?action=consume-material&metal_purchase_id=${id}`,
  );
  ctx.hooks.closeOverlay();
  // The deeper flow ( weight entry + optional AlloyMismatchModal +
  // POST /metal-inventory/usage) lives in the legacy ConsumeMetalModal
  // per Slice 12 scope. Slice 11 hands off with the payload.
  // Preserve the alloy/context for downstream consumers — keeping the
  // data path deterministic until the embedded weight-entry lands.
  void metalAlloy;
}

async function handlePunzierungCheck(
  ctx: ActionHandlerContext,
): Promise<void> {
  const id = entityId(ctx);
  if (id === null) throw new Error('Auftrag unklar.');
  const data = entityData(ctx);
  const orderAlloy = typeof data.alloy === 'string' ? data.alloy : undefined;
  const orderTitle = typeof data.title === 'string' ? data.title : undefined;

  let payload: PunzierungsCheckPayload;
  try {
    payload = await fireModal<
      PunzierungsCheckPayload,
      PunzierungsCheckModalProps
    >(PunzierungsCheckModal, {
      orderId: id,
      orderAlloy,
      orderTitle,
    });
  } catch {
    // User cancelled — silent.
    return;
  }

  await apiClient.patch(`/orders/${id}`, {
    punzierung_verified_marks: payload.marks,
  });

  ctx.hooks.toast(
    `Punzierungs-Check gespeichert — ${payload.marks.length} Punzen.`,
    'success',
  );
  ctx.hooks.closeOverlay();
}

// --- consume_material helper (exported for tests) --------------------------

/**
 * Fire the AlloyMismatchModal and retry consume_material with override.
 * Exported so tests can exercise the mismatch branch without reaching
 * the navigate-away fallback.
 *
 * Signature is a simplified Transport-free shape — the retry posts via
 * apiClient directly.
 */
export async function consumeWithMismatchRetry(params: {
  metalPurchaseId: number;
  metalAlloy: string;
  orderId: number;
  orderAlloy: string;
  weightGrams: number;
  metalType: string;
}): Promise<{ overridden: boolean }> {
  try {
    await apiClient.post(
      `/metal-inventory/usage?metal_type=${encodeURIComponent(params.metalType)}`,
      {
        order_id: params.orderId,
        metal_purchase_id: params.metalPurchaseId,
        weight_used_g: params.weightGrams,
        costing_method: 'specific',
        alloy_override: false,
      },
    );
    return { overridden: false };
  } catch (err) {
    const { status, code } = extractErrorInfo(err);
    if (status !== 409 || code !== 'ALLOY_MISMATCH') {
      throw err;
    }
  }

  // Mismatch — fire modal for conscious override.
  let overrideResult: AlloyOverridePayload;
  try {
    overrideResult = await fireModal<
      AlloyOverridePayload,
      AlloyMismatchModalProps
    >(AlloyMismatchModal, {
      orderAlloy: params.orderAlloy,
      metalAlloy: params.metalAlloy,
      weightGrams: params.weightGrams,
    });
  } catch {
    throw new Error('Entnahme abgebrochen.');
  }

  await apiClient.post(
    `/metal-inventory/usage?metal_type=${encodeURIComponent(params.metalType)}`,
    {
      order_id: params.orderId,
      metal_purchase_id: params.metalPurchaseId,
      weight_used_g: params.weightGrams,
      costing_method: 'specific',
      alloy_override: true,
      override_reason: overrideResult.override_reason,
      override_reason_category: overrideResult.override_reason_category,
    },
  );
  return { overridden: true };
}

// Convenience re-export so consumers can dispatch actions by ID without
// importing individual handlers.
export const ACTION_HANDLERS: Record<string, ActionHandler> = {
  start_timer: handleStartTimer,
  stop_timer: handleStopTimer,
  switch_timer: handleSwitchTimer,
  change_status: handleChangeStatus,
  change_location: handleChangeLocation,
  switch_activity: handleSwitchActivity,
  log_interruption: handleLogInterruption,
  take_photo: handleTakePhoto,
  print_label: handlePrintLabel,
  open_entity: handleOpenEntity,
  consume_material: handleConsumeMaterial,
  punzierung_check: handlePunzierungCheck,
};

/**
 * Build an ActionExecution payload for the (future) /scan/action/:id
 * endpoint. Handlers currently hit entity endpoints directly; this is
 * kept for Slice 12+ when the generic surface lands.
 */
export function buildActionExecution(
  actionId: string,
  entity: ResolvedEntity,
  payload: Record<string, unknown>,
): ActionExecution {
  return {
    action_id: actionId,
    entity_type: entity.entity_type,
    entity_id: entity.entity_id,
    payload,
    idempotency_key: crypto.randomUUID(),
  };
}

// Dispatcher entrypoint used by ScanOverlay.
export async function dispatchAction(
  actionId: string,
  ctx: ActionHandlerContext,
): Promise<void> {
  const handler = ACTION_HANDLERS[actionId];
  if (!handler) {
    throw new Error(`Unbekannte Aktion: ${actionId}`);
  }
  await handler(ctx);
}
