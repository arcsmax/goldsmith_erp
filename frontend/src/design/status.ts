// The single status map (UI-UX-PLAYBOOK 3.2; LV-05, W4).
//
// Every status the UI shows gets its German label, tone and icon from here.
// <StatusBadge kind status> (src/ui/StatusBadge.tsx) reads only this map;
// older per-page label consts re-export from it. Labels follow the playbook
// table, which wins where pages disagreed. Tones are the --tone-* token
// triplets in brand-tokens.css. The completeness test (status.test.ts)
// checks every family against the generated backend enums, so a new
// backend status fails CI instead of showing up raw.
import type { Schema } from '../api/generated';
import type { ScrapGoldStatus } from '../api/scrap-gold';
import type {
  ConsultationStatus,
  InvoiceStatus,
  OrderStatus,
  QuoteStatus,
  RepairJobStatus,
} from '../types';
import type { IconName } from '../ui/Icon';

export type StatusTone =
  | 'neutral'
  | 'info'
  | 'progress'
  | 'waiting'
  | 'check'
  | 'done'
  | 'handover'
  | 'danger';

/** Second, non-colour cue (WCAG 1.4.1): draft dashed, handed over double,
 *  cancelled struck through. */
export type StatusBorder = 'solid' | 'dashed' | 'double' | 'struck';

export interface StatusMeta {
  readonly label: string;
  readonly tone: StatusTone;
  readonly icon: IconName;
  readonly border: StatusBorder;
}

export type StatusKind =
  | 'order'
  | 'repair'
  | 'quote'
  | 'invoice'
  | 'consultation'
  | 'costChange'
  | 'handoff'
  | 'hallmark'
  | 'scrapGold'
  | 'customerUpdate'
  | 'timeEntry'
  | 'user'
  | 'job';

/** Not a backend enum (``User.is_active`` is a plain boolean) — the two
 * wire values a caller passes are the literal strings below. */
export type UserActiveStatus = 'active' | 'inactive';

type CostChangeStatus = Schema<'CostChangeStatus'>;
type CustomerUpdateStatus = Schema<'CustomerUpdateStatus'>;
type HallmarkStatus = Schema<'HallmarkStatus'>;
type HandoffStatus = Schema<'HandoffStatusEnum'>;
type JobStatus = Schema<'JobStatus'>;

type StatusTable<S extends string> = Readonly<Record<S, StatusMeta>>;

function meta(
  label: string,
  tone: StatusTone,
  icon: IconName,
  border: StatusBorder = 'solid',
): StatusMeta {
  return Object.freeze({ label, tone, icon, border });
}

export const ORDER_STATUS: StatusTable<OrderStatus> = {
  draft: meta('Entwurf', 'neutral', 'pencil', 'dashed'),
  new: meta('Neu', 'info', 'sparkles'),
  confirmed: meta('Bestätigt', 'info', 'clipboard-check'),
  in_progress: meta('In Bearbeitung', 'progress', 'hammer'),
  waiting_for_fitting: meta('Wartet auf Anprobe', 'waiting', 'hourglass'),
  fitting_done: meta('Anprobe abgeschlossen', 'progress', 'user-check'),
  ready_for_setting: meta('Bereit zum Fassen', 'progress', 'gem'),
  quality_check: meta('Qualitätskontrolle', 'check', 'scan-search'),
  completed: meta('Fertiggestellt', 'done', 'circle-check'),
  delivered: meta('Ausgeliefert', 'handover', 'package-check', 'double'),
  on_hold: meta('Pausiert', 'waiting', 'pause', 'dashed'),
  cancelled: meta('Storniert', 'danger', 'circle-x', 'struck'),
};

export const REPAIR_STATUS: StatusTable<RepairJobStatus> = {
  received: meta('Eingang', 'info', 'inbox'),
  diagnosed: meta('Diagnose', 'progress', 'search'),
  quoted: meta('Angebot offen', 'waiting', 'file-text'),
  approved: meta('Genehmigt', 'info', 'thumbs-up'),
  in_repair: meta('In Arbeit', 'progress', 'wrench'),
  quality_check: meta('Qualitätskontrolle', 'check', 'scan-search'),
  ready: meta('Abholbereit', 'done', 'circle-check'),
  picked_up: meta('Abgeholt', 'handover', 'package-check', 'double'),
  cancelled: meta('Storniert', 'danger', 'circle-x', 'struck'),
};

export const QUOTE_STATUS: StatusTable<QuoteStatus> = {
  draft: meta('Entwurf', 'neutral', 'pencil', 'dashed'),
  sent: meta('Gesendet', 'waiting', 'send'),
  approved: meta('Genehmigt', 'done', 'circle-check'),
  rejected: meta('Abgelehnt', 'danger', 'circle-x'),
  expired: meta('Abgelaufen', 'neutral', 'clock'),
  converted: meta('In Auftrag umgewandelt', 'handover', 'arrow-right-left', 'double'),
};

export const INVOICE_STATUS: StatusTable<InvoiceStatus> = {
  draft: meta('Entwurf', 'neutral', 'pencil', 'dashed'),
  sent: meta('Versendet', 'waiting', 'send'),
  paid: meta('Bezahlt', 'done', 'circle-check'),
  overdue: meta('Überfällig', 'danger', 'triangle-alert'),
  cancelled: meta('Storniert', 'danger', 'circle-x', 'struck'),
};

export const CONSULTATION_STATUS: StatusTable<ConsultationStatus> = {
  draft: meta('Entwurf', 'neutral', 'pencil', 'dashed'),
  completed: meta('Abgeschlossen', 'done', 'circle-check'),
  converted: meta('Umgewandelt', 'handover', 'arrow-right-left', 'double'),
  archived: meta('Archiviert', 'neutral', 'archive'),
};

export const COST_CHANGE_STATUS: StatusTable<CostChangeStatus> = {
  draft: meta('Entwurf', 'neutral', 'pencil', 'dashed'),
  sent: meta('Gesendet', 'waiting', 'send'),
  approved: meta('Zugestimmt', 'done', 'circle-check'),
  declined: meta('Abgelehnt', 'danger', 'circle-x'),
  superseded: meta('Ersetzt', 'neutral', 'archive'),
};

export const HANDOFF_STATUS: StatusTable<HandoffStatus> = {
  pending: meta('Offen', 'waiting', 'hourglass'),
  accepted: meta('Übernommen', 'done', 'circle-check'),
  declined: meta('Abgelehnt', 'danger', 'circle-x'),
};

export const HALLMARK_STATUS: StatusTable<HallmarkStatus> = {
  pending: meta('Nicht eingereicht', 'neutral', 'clock', 'dashed'),
  submitted: meta('Eingereicht', 'waiting', 'send'),
  approved: meta('Genehmigt', 'info', 'thumbs-up'),
  rejected: meta('Abgelehnt', 'danger', 'circle-x'),
  stamped: meta('Punziert', 'done', 'stamp'),
};

export const SCRAP_GOLD_STATUS: StatusTable<ScrapGoldStatus> = {
  received: meta('Erfasst', 'info', 'inbox'),
  calculated: meta('Berechnet', 'progress', 'calculator'),
  signed: meta('Unterschrieben', 'done', 'pen-line'),
  credited: meta('Verrechnet', 'handover', 'receipt', 'double'),
};

export const CUSTOMER_UPDATE_STATUS: StatusTable<CustomerUpdateStatus> = {
  draft: meta('Entwurf', 'neutral', 'pencil', 'dashed'),
  sent: meta('Versendet', 'done', 'send'),
  send_failed: meta('Versand fehlgeschlagen', 'danger', 'triangle-alert'),
};

/**
 * D-15: the running-timer's manual-pause state (TimerWidget). Not backed by
 * a real backend enum — `TimeEntry.is_paused` is a boolean, derived from
 * whether an Interruption is open — so this table (unlike every other one
 * here) has no matching entry in `ENUM_FOR_KIND` in status.test.ts; it gets
 * its own literal-list completeness check there instead, the same way
 * `scrapGold` does. Only the "paused" state gets a badge — the plain
 * "⏱️ Läuft" text already communicates the running state.
 */
export type TimeEntryPauseStatus = 'paused';

export const TIME_ENTRY_STATUS: StatusTable<TimeEntryPauseStatus> = {
  paused: meta('Pausiert', 'waiting', 'pause', 'dashed'),
};

/** UsersPage account status (W7 hygiene): was a bespoke `.users-active-state`
 * span with an icon and text, never wired into <StatusBadge>. */
export const USER_STATUS: StatusTable<UserActiveStatus> = {
  active: meta('Aktiv', 'done', 'circle-check'),
  inactive: meta('Inaktiv', 'neutral', 'circle-x'),
};

/** Unified job lifecycle over orders and repairs (ARCH-02, Werkstatt board).
 * Labels match the backend's JOB_STATUS_LABELS (services/job_service.py). */
export const JOB_STATUS: StatusTable<JobStatus> = {
  draft: meta('Entwurf', 'neutral', 'pencil', 'dashed'),
  intake: meta('Eingang', 'info', 'inbox'),
  awaiting_approval: meta('Wartet auf Freigabe', 'waiting', 'hourglass'),
  confirmed: meta('Bestätigt', 'info', 'clipboard-check'),
  in_progress: meta('In Arbeit', 'progress', 'hammer'),
  quality_check: meta('Qualitätskontrolle', 'check', 'scan-search'),
  ready: meta('Fertig', 'done', 'circle-check'),
  delivered: meta('Ausgeliefert', 'handover', 'package-check', 'double'),
  on_hold: meta('Pausiert', 'waiting', 'pause', 'dashed'),
  cancelled: meta('Storniert', 'danger', 'circle-x', 'struck'),
};

export const STATUS_MAP: Readonly<Record<StatusKind, Readonly<Record<string, StatusMeta>>>> = {
  order: ORDER_STATUS,
  repair: REPAIR_STATUS,
  quote: QUOTE_STATUS,
  invoice: INVOICE_STATUS,
  consultation: CONSULTATION_STATUS,
  costChange: COST_CHANGE_STATUS,
  handoff: HANDOFF_STATUS,
  hallmark: HALLMARK_STATUS,
  scrapGold: SCRAP_GOLD_STATUS,
  customerUpdate: CUSTOMER_UPDATE_STATUS,
  timeEntry: TIME_ENTRY_STATUS,
  user: USER_STATUS,
  job: JOB_STATUS,
};

/**
 * Meta for one status, or undefined for a value the map does not know.
 * Some older endpoints send upper-case values (handoffs: "PENDING"), so the
 * lookup falls back to the lower-case key.
 */
export function getStatusMeta(kind: StatusKind, status: string): StatusMeta | undefined {
  const table = STATUS_MAP[kind];
  if (Object.prototype.hasOwnProperty.call(table, status)) return table[status];
  const lower = status.toLowerCase();
  return Object.prototype.hasOwnProperty.call(table, lower) ? table[lower] : undefined;
}

/** German label, or the raw value when the status is unknown. */
export function getStatusLabel(kind: StatusKind, status: string): string {
  return getStatusMeta(kind, status)?.label ?? status;
}

/** Plain value -> label record, for selects and filter chips. */
export function statusLabelsFor<S extends string>(
  table: StatusTable<S>,
): Readonly<Record<S, string>> {
  const entries = Object.entries(table) as [S, StatusMeta][];
  return Object.fromEntries(entries.map(([key, value]) => [key, value.label])) as Record<
    S,
    string
  >;
}

/**
 * Handoff types are not statuses, but the dashboard and the order page both
 * show them next to handoff badges, so they live with the handoff family
 * (LV-08; wire values of HandoffTypeEnum).
 */
export const HANDOFF_TYPE_LABELS: Readonly<Record<Schema<'HandoffTypeEnum'>, string>> = {
  pass_to_next: 'Weitergabe',
  request_review: 'Prüfung anfordern',
  return_for_rework: 'Zurück zur Nacharbeit',
  mark_complete: 'Fertigmeldung',
};

export function getHandoffTypeLabel(type: string): string {
  const key = type.toLowerCase() as Schema<'HandoffTypeEnum'>;
  return Object.prototype.hasOwnProperty.call(HANDOFF_TYPE_LABELS, key)
    ? HANDOFF_TYPE_LABELS[key]
    : type;
}
