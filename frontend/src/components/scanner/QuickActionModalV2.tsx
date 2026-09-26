// QuickActionModalV2 — the action sheet after a scan (V1.1 Slice 11,
// rebuilt on the Sheet primitive in the 2026-09 scan-tracking audit).
//
// The scan is already logged (scan_only) when this sheet opens; the sheet
// only makes the NEXT step easy:
//   * Header: Kurzbezeichnung + id + status (A11.4); the status hint opens
//     the piece (A11.12).
//   * Actions: the backend's role-filtered list (only ids the client can
//     execute; ScanOverlay filters), primary first, as 56px bench buttons:
//     Timer starten / wechseln, Foto, Status weiter, Übergabe, Standort
//     setzen, Öffnen, Nur erfassen.
//   * Unknown code: a German message instead of actions (the scan is logged
//     as "unrecognised").
//   * Sheet primitive: focus moves in, Tab stays inside, Escape closes,
//     focus returns — no hand-rolled trap.
//
// All copy is German. Icons come from the shared icon set (no emoji).

import React, { useCallback, useMemo, useState } from 'react';

import type { ActionItem, ResolveResponse } from '../../types/scanner';
import { Button, Sheet, type IconName } from '../../ui';
import { unrecognisedMessage } from '../../lib/scanPayload';
import '../../styles/components/QuickActionModalV2.css';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface QuickActionModalV2Props {
  resolveResponse: ResolveResponse;
  /**
   * Fired when the user taps an action. The handler resolves once the
   * backend action has completed. Errors are surfaced inline.
   */
  onAction: (actionId: string) => Promise<void>;
  onClose: () => void;
  onContinueScanning: () => void;
  /** Optional: tapping the status-hint line opens the entity detail page. */
  onStatusHintClick?: () => void;
  /** The scanned text, shown when the code is not recognised. */
  rawPayload?: string;
}

// ---------------------------------------------------------------------------
// Kurzbezeichnung helpers (A11.4)
// ---------------------------------------------------------------------------

const TITLE_TRUNCATE = 40;

function truncate(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

interface EntityDisplay {
  /** Top-row identifier, monospace. e.g. "ORDER:42" */
  idLabel: string;
  /** Prominent Kurzbezeichnung, e.g. "Trauring Mueller M." */
  title: string;
  /** Optional status pill text. */
  statusPill: string | null;
  /** Optional status-hint subline. */
  statusHint: string | null;
}

function buildEntityDisplay(response: ResolveResponse): EntityDisplay {
  const entityType = response.entity_type ?? '';
  const entityId = response.entity_id;
  const data = (response.entity ?? {}) as Record<string, unknown>;

  // ORDER
  if (entityType === 'order') {
    const title = typeof data.title === 'string' ? data.title : '';
    const customerInitials =
      typeof data.customer_initials === 'string' ? data.customer_initials : null;
    const status = typeof data.status === 'string' ? data.status : null;
    const orderNumber =
      typeof data.order_number === 'string' ? data.order_number : null;

    const titlePart = truncate(title || 'Auftrag', TITLE_TRUNCATE);
    const displayTitle = customerInitials
      ? `${customerInitials} — ${titlePart}`
      : titlePart;

    return {
      idLabel: orderNumber ? orderNumber : `ORDER:${entityId ?? '?'}`,
      title: displayTitle,
      statusPill: status ? formatStatus(status) : null,
      statusHint: response.status_hint,
    };
  }

  // REPAIR
  if (entityType === 'repair') {
    const repairNumber =
      typeof data.repair_number === 'string' ? data.repair_number : null;
    const bagNumber =
      typeof data.bag_number === 'string' ? data.bag_number : null;
    const itemDescription =
      typeof data.item_type === 'string'
        ? data.item_type
        : typeof data.diagnosis_notes === 'string'
          ? data.diagnosis_notes
          : '';
    const status = typeof data.status === 'string' ? data.status : null;

    const parts: string[] = [];
    if (repairNumber) parts.push(repairNumber);
    if (bagNumber) parts.push(bagNumber);
    if (itemDescription) parts.push(truncate(itemDescription, TITLE_TRUNCATE));

    return {
      idLabel: repairNumber ? repairNumber : `REPAIR:${entityId ?? '?'}`,
      title: parts.length > 0 ? parts.join(' — ') : 'Reparatur',
      statusPill: status ? formatStatus(status) : null,
      statusHint: response.status_hint,
    };
  }

  // METAL
  if (entityType === 'metal_purchase') {
    const alloyName = typeof data.metal_type === 'string' ? data.metal_type : '';
    const lotNumber =
      typeof data.lot_number === 'string' ? data.lot_number : null;
    const title = lotNumber
      ? `${alloyName || 'Metall'} — Lot ${lotNumber}`
      : alloyName || 'Metall';
    return {
      idLabel: `METAL:${entityId ?? '?'}`,
      title,
      statusPill: null,
      statusHint: response.status_hint,
    };
  }

  // MATERIAL
  if (entityType === 'material') {
    const name = typeof data.name === 'string' ? data.name : '';
    return {
      idLabel: `MATERIAL:${entityId ?? '?'}`,
      title: name || 'Material',
      statusPill: null,
      statusHint: response.status_hint,
    };
  }

  // ACTIVITY / INTERRUPT / unknown — fall-through
  const fallbackTitle =
    typeof data.label === 'string'
      ? data.label
      : typeof data.code === 'string'
        ? data.code
        : entityType || 'Scan';
  return {
    idLabel: entityId !== null ? `${entityType}:${entityId}` : entityType,
    title: fallbackTitle,
    statusPill: null,
    statusHint: response.status_hint,
  };
}

/** Format a raw status enum value into a German display label. */
function formatStatus(raw: string): string {
  const map: Record<string, string> = {
    new: 'Neu',
    in_progress: 'In Arbeit',
    quality_check: 'Qualitätskontrolle',
    completed: 'Abgeschlossen',
    delivered: 'Ausgeliefert',
    cancelled: 'Storniert',
    received: 'Angenommen',
    in_repair: 'In Reparatur',
    ready_for_pickup: 'Abholbereit',
  };
  return map[raw.toLowerCase()] ?? raw.toUpperCase();
}

// ---------------------------------------------------------------------------
// Icons (shared icon set, aria-hidden inside the Button primitive)
// ---------------------------------------------------------------------------

const ACTION_ICONS: Readonly<Record<string, IconName>> = {
  start_timer: 'clock',
  stop_timer: 'pause',
  switch_timer: 'arrow-right-left',
  change_status: 'arrow-right',
  advance_repair: 'arrow-right',
  take_photo: 'camera',
  handover: 'user-check',
  change_location: 'archive',
  open_entity: 'file-text',
  print_label: 'clipboard',
  consume_material: 'gem',
  punzierung_check: 'stamp',
  log_only: 'check',
};

function iconForAction(id: string): IconName {
  return ACTION_ICONS[id] ?? 'scan';
}

/** Primary first; ties keep the server order. */
function sortActions(actions: readonly ActionItem[]): ActionItem[] {
  return [...actions].sort((a, b) => (a.primary === b.primary ? 0 : a.primary ? -1 : 1));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const EntityHeader: React.FC<{
  display: EntityDisplay;
  onStatusHintClick?: () => void;
}> = ({ display, onStatusHintClick }) => (
  <div className="qa-header">
    <div className="qa-header__row qa-header__row--top">
      <span className="qa-id" data-testid="qa-id">
        {display.idLabel}
      </span>
      {display.statusPill !== null && (
        <span className="qa-status-pill" data-testid="qa-status-pill">
          {display.statusPill}
        </span>
      )}
    </div>
    <p className="qa-live" role="status" aria-live="polite" data-testid="qa-live">
      {display.title}
      {display.statusPill !== null ? ` · ${display.statusPill}` : ''}
    </p>
    {display.statusHint !== null &&
      (onStatusHintClick ? (
        <button
          type="button"
          className="qa-status-hint qa-status-hint--tappable"
          onClick={onStatusHintClick}
          data-testid="qa-status-hint"
          aria-label={`Details öffnen: ${display.statusHint}`}
        >
          {display.statusHint}
        </button>
      ) : (
        <p className="qa-status-hint" data-testid="qa-status-hint">
          {display.statusHint}
        </p>
      ))}
  </div>
);

export const QuickActionModalV2: React.FC<QuickActionModalV2Props> = ({
  resolveResponse,
  onAction,
  onClose,
  onContinueScanning,
  onStatusHintClick,
  rawPayload,
}) => {
  const [pendingActionId, setPendingActionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const display = useMemo(() => buildEntityDisplay(resolveResponse), [resolveResponse]);
  const actions = useMemo(() => sortActions(resolveResponse.actions), [resolveResponse.actions]);
  const isUnrecognised = !resolveResponse.resolved;
  const title = isUnrecognised ? 'Code nicht erkannt' : display.title;

  const handleAction = useCallback(
    async (actionId: string): Promise<void> => {
      setError(null);
      setPendingActionId(actionId);
      try {
        await onAction(actionId);
      } catch (err) {
        setError(err instanceof Error && err.message.length > 0 ? err.message : 'Aktion fehlgeschlagen.');
      } finally {
        setPendingActionId(null);
      }
    },
    [onAction],
  );

  return (
    <Sheet
      open
      onClose={onClose}
      title={title}
      className="qa-modal-v2"
      footer={
        <Button
          variant="secondary"
          size="lg"
          block
          icon="scan"
          onClick={onContinueScanning}
          data-testid="qa-continue"
        >
          Weiterscannen
        </Button>
      }
    >
      <div data-testid="qa-modal-v2">
        <span className="ui-visually-hidden" data-testid="qa-title">
          {title}
        </span>
        {!isUnrecognised && (
          <EntityHeader display={display} onStatusHintClick={onStatusHintClick} />
        )}
        {error !== null && (
          <p className="qa-error" role="alert" data-testid="qa-error">
            {error}
          </p>
        )}
        {isUnrecognised ? (
          <p className="qa-empty-access" role="alert" data-testid="qa-unrecognised">
            {unrecognisedMessage(rawPayload ?? display.idLabel)} Der Scan wurde trotzdem erfasst.
          </p>
        ) : actions.length === 0 ? (
          <p className="qa-empty-access" role="status" data-testid="qa-empty-access">
            Kein Zugriff auf diese Charge.
          </p>
        ) : (
          <ul className="qa-action-list" data-testid="qa-action-list">
            {actions.map((action) => (
              <li key={action.id} className="qa-action-row">
                <Button
                  variant={action.primary ? 'primary' : 'secondary'}
                  size="lg"
                  block
                  icon={iconForAction(action.id)}
                  className={action.primary ? 'qa-action--primary' : 'qa-action--secondary'}
                  data-testid={`qa-action-${action.id}`}
                  data-primary={action.primary ? 'true' : 'false'}
                  loading={pendingActionId === action.id}
                  disabled={pendingActionId !== null && pendingActionId !== action.id}
                  onClick={() => void handleAction(action.id)}
                >
                  {action.label}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Sheet>
  );
};

export default QuickActionModalV2;
