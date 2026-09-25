// Werkstatt board model (W6 kanban over the jobs spine, ARCH-02).
//
// Columns are the unified job statuses of the generated `JobStatus` enum.
// Closed work (delivered, cancelled) stays off the board; it is reachable
// from the order and repair lists.
//
// "Weiter" advances one card by its obvious next step, using the existing
// per-kind endpoints: PATCH /orders/{id}/status with the order's primary
// next status, or the repair workflow POSTs that need no input (start,
// quality check, pickup). Steps that need input (diagnosis, customer
// approval, Fertigmeldung with the actual cost) stay on the detail page.
import type { JobListItem, JobStatus } from '../../api/jobs';
import { ordersApi } from '../../api/orders';
import { MAX_PAGE_SIZE } from '../../api/paged';
import { repairsApi } from '../../api/repairs';
import { primaryNextStatus } from '../orders/orderStatus';
import type { StatusKind } from '../../design/status';

export const BOARD_COLUMNS: readonly JobStatus[] = [
  'draft',
  'intake',
  'awaiting_approval',
  'confirmed',
  'in_progress',
  'quality_check',
  'ready',
  'on_hold',
];

/** Cards per column; the backend caps a page at 200. */
export const BOARD_COLUMN_LIMIT = MAX_PAGE_SIZE;

/** Earliest deadline first, so the most urgent card sits on top. */
export const BOARD_SORT = 'deadline,number';

export type JobKindFilter = 'all' | 'order' | 'repair';

export const KIND_LABELS: Readonly<Record<JobListItem['kind'], string>> = {
  order: 'Auftrag',
  repair: 'Reparatur',
};

type RepairStep = 'start' | 'quality_check' | 'pickup';

/** Next repair step per raw repair status, only for steps without input. */
const REPAIR_NEXT: Readonly<Record<string, { step: RepairStep; target: string }>> = {
  approved: { step: 'start', target: 'in_repair' },
  in_repair: { step: 'quality_check', target: 'quality_check' },
  ready: { step: 'pickup', target: 'picked_up' },
};

export interface AdvanceStep {
  /** Raw per-kind target status (for the German label from status.ts). */
  target: string;
  /** StatusKind of `target`: "order" or "repair". */
  statusKind: StatusKind;
  run: () => Promise<unknown>;
}

function orderStep(job: JobListItem): AdvanceStep | null {
  const target = primaryNextStatus(job.kind_status);
  if (!target || job.order_id == null) return null;
  const orderId = job.order_id;
  return {
    target,
    statusKind: 'order',
    run: () => ordersApi.changeStatus(orderId, { status: target }),
  };
}

function repairStep(job: JobListItem): AdvanceStep | null {
  const next = REPAIR_NEXT[job.kind_status];
  if (!next || job.repair_id == null) return null;
  const repairId = job.repair_id;
  const run = {
    start: () => repairsApi.startRepair(repairId),
    quality_check: () => repairsApi.submitQualityCheck(repairId),
    pickup: () => repairsApi.pickup(repairId),
  }[next.step];
  return { target: next.target, statusKind: 'repair', run };
}

/** The card's "Weiter" step, or null when it needs the detail page. */
export function advanceStep(job: JobListItem): AdvanceStep | null {
  return job.kind === 'order' ? orderStep(job) : repairStep(job);
}

/** Detail page of the order or repair behind a job. */
export function jobHref(job: JobListItem): string | null {
  if (job.kind === 'order' && job.order_id != null) return `/orders/${job.order_id}`;
  if (job.kind === 'repair' && job.repair_id != null) return `/repairs/${job.repair_id}`;
  return null;
}

/** Keys that move focus between board columns. */
export const COLUMN_NAV_KEYS: ReadonlySet<string> = new Set(['ArrowLeft', 'ArrowRight', 'Home', 'End']);

/** Index of the column that a navigation key moves focus to. */
export function nextColumnIndex(key: string, current: number, count: number): number {
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  if (key === 'ArrowLeft') return Math.max(current - 1, 0);
  if (key === 'ArrowRight') return Math.min(current + 1, count - 1);
  return current;
}
