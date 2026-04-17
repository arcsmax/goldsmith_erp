// QuickActionModalV2 — Slice 11 of V1.1 QR/Barcode workflow.
//
// Replaces the legacy `QuickActionModal.tsx` (which stayed ORDER-only and
// embedded Activity/Location pickers as nested views — A11.13 deprecates
// that pattern).
//
// Responsibilities:
//   * Render a Kurzbezeichnung header disambiguating the entity (A11.4).
//   * Render role-filtered, backend-sorted Quick Actions (primary first).
//   * Status-hint line is tappable (A11.12) — tap opens the entity detail.
//   * Empty-projection handling (VIEWER/METAL): render "Kein Zugriff"
//     placeholder with Schliessen only — no actions rendered.
//   * Auto-dismiss cooperation with ScanOverlay (A10.3): the overlay owns
//     the `lastResolveResponse` → QuickActionModalV2 is a pure render of
//     the current response and re-renders when props change. No internal
//     cache beyond React state needed for animations.
//   * Keyboard accessibility: role=dialog, aria-modal, focus trap, Esc to
//     close, Enter activates focused action.
//   * `prefers-reduced-motion` honoured via CSS.
//
// All copy is German. No English UI strings.
//
// References:
//   docs/superpowers/plans/qr-barcode-workflow/V1.1-IMPLEMENTATION-PLAN.md Slice 11
//   docs/superpowers/plans/qr-barcode-workflow/V1.1-UI-DESIGN-SPEC.md §2
//   docs/superpowers/plans/qr-barcode-workflow/V1.1-AMENDMENTS.md A11.4, A11.12, A11.13

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import type { ActionItem, ResolveResponse } from '../../types/scanner';
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
  const data = (response.entity?.data ?? {}) as Record<string, unknown>;

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
// Icon map (A11.8 Lucide mapping — minimal inline SVGs to avoid new dep)
// ---------------------------------------------------------------------------
//
// Slice 11 uses small inline SVGs to keep the bundle lean (M7). Adding
// `lucide-react` is an optional V1.2 upgrade — the placeholder mapping here
// covers the actions emitted by the backend scanner service.

const ACTION_ICONS: Record<string, string> = {
  start_timer: '▶',
  stop_timer: '■',
  switch_timer: '↻',
  change_status: '✎',
  change_location: '📍',
  take_photo: '📷',
  add_material: '💎',
  add_note: '📝',
  contact_customer: '📞',
  print_label: '🏷',
  open_entity: '↗',
  consume_material: '⚖',
  check_stock: '📊',
  reorder: '🛒',
  advance_repair: '➤',
  repair_diagnosis: '🔍',
  punzierung_check: '🔖',
};

function iconForAction(id: string): string {
  return ACTION_ICONS[id] ?? '•';
}

// ---------------------------------------------------------------------------
// Focus trap helpers
// ---------------------------------------------------------------------------

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function getFocusable(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const QuickActionModalV2: React.FC<QuickActionModalV2Props> = ({
  resolveResponse,
  onAction,
  onClose,
  onContinueScanning,
  onStatusHintClick,
}) => {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const firstActionRef = useRef<HTMLButtonElement | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);

  const [pendingActionId, setPendingActionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const display = useMemo<EntityDisplay>(
    () => buildEntityDisplay(resolveResponse),
    [resolveResponse],
  );

  // Sort actions with `primary=true` first — ties preserve server order.
  const sortedActions = useMemo<ActionItem[]>(() => {
    const list = [...resolveResponse.actions];
    list.sort((a, b) => {
      if (a.primary === b.primary) return 0;
      return a.primary ? -1 : 1;
    });
    return list;
  }, [resolveResponse.actions]);

  const isEmptyAccess = sortedActions.length === 0;

  // ---------------------------------------------------------------------
  // Focus management — on mount move focus to first action (A11 / SC 2.4.3).
  // ---------------------------------------------------------------------

  useEffect(() => {
    const rafId = window.requestAnimationFrame(() => {
      if (firstActionRef.current) {
        firstActionRef.current.focus();
      } else if (closeBtnRef.current) {
        closeBtnRef.current.focus();
      }
    });
    return () => window.cancelAnimationFrame(rafId);
  }, []);

  // ---------------------------------------------------------------------
  // Focus trap + Esc handling.
  // ---------------------------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const root = rootRef.current;
      if (root === null) return;
      const focusable = getFocusable(root);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (e.shiftKey) {
        if (active === first || active === null || !root.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // ---------------------------------------------------------------------
  // Action dispatch
  // ---------------------------------------------------------------------

  const handleAction = useCallback(
    async (actionId: string): Promise<void> => {
      setError(null);
      setPendingActionId(actionId);
      try {
        await onAction(actionId);
      } catch (err) {
        const msg =
          err instanceof Error && err.message.length > 0
            ? err.message
            : 'Aktion fehlgeschlagen.';
        setError(msg);
      } finally {
        setPendingActionId(null);
      }
    },
    [onAction],
  );

  // ---------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------

  return (
    <div
      className="qa-modal-v2"
      role="dialog"
      aria-modal="true"
      aria-labelledby="qa-title"
      aria-describedby="qa-subtitle"
      data-testid="qa-modal-v2"
      ref={rootRef}
    >
      <div className="qa-header">
        <div className="qa-header__row qa-header__row--top">
          <span
            className="qa-id"
            data-testid="qa-id"
          >
            {display.idLabel}
          </span>
          {display.statusPill !== null ? (
            <span className="qa-status-pill" data-testid="qa-status-pill">
              {display.statusPill}
            </span>
          ) : null}
          <button
            type="button"
            className="qa-close"
            onClick={onClose}
            aria-label="Schliessen"
            ref={closeBtnRef}
            data-testid="qa-close"
          >
            ✕
          </button>
        </div>
        <h2 id="qa-title" className="qa-title" data-testid="qa-title">
          {display.title}
        </h2>
        <div
          className="qa-live"
          role="status"
          aria-live="polite"
          data-testid="qa-live"
        >
          {display.title}
          {display.statusPill !== null ? ` · ${display.statusPill}` : ''}
        </div>
        {display.statusHint !== null ? (
          onStatusHintClick ? (
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
            <p
              id="qa-subtitle"
              className="qa-status-hint"
              data-testid="qa-status-hint"
            >
              {display.statusHint}
            </p>
          )
        ) : null}
      </div>

      <div className="qa-body">
        {error !== null ? (
          <div className="qa-error" role="alert" data-testid="qa-error">
            {error}
          </div>
        ) : null}

        {isEmptyAccess ? (
          <div
            className="qa-empty-access"
            role="status"
            data-testid="qa-empty-access"
          >
            Kein Zugriff auf diese Charge.
          </div>
        ) : (
          <ul
            className="qa-action-list"
            role="list"
            data-testid="qa-action-list"
          >
            {sortedActions.map((action, index) => {
              const isPrimary = action.primary;
              const isPending = pendingActionId === action.id;
              const refProp = index === 0 ? firstActionRef : undefined;
              return (
                <li key={action.id} className="qa-action-row">
                  <button
                    type="button"
                    ref={refProp}
                    className={`qa-action ${
                      isPrimary ? 'qa-action--primary' : 'qa-action--secondary'
                    }`}
                    data-testid={`qa-action-${action.id}`}
                    data-primary={isPrimary ? 'true' : 'false'}
                    onClick={() => {
                      void handleAction(action.id);
                    }}
                    disabled={isPending || pendingActionId !== null}
                    aria-label={action.label}
                  >
                    <span className="qa-action__icon" aria-hidden="true">
                      {iconForAction(action.id)}
                    </span>
                    <span className="qa-action__label">{action.label}</span>
                    {isPending ? (
                      <span className="qa-action__spinner" aria-hidden="true">
                        …
                      </span>
                    ) : (
                      <span className="qa-action__chevron" aria-hidden="true">
                        ›
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="qa-footer">
        <button
          type="button"
          className="qa-continue"
          onClick={onContinueScanning}
          data-testid="qa-continue"
        >
          Weiterscannen
        </button>
      </div>
    </div>
  );
};

export default QuickActionModalV2;
