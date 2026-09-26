// PunzierungsCheckModal — Slice 11 stacked modal for hallmark verification,
// widened to a soft gate in W2-09 (DOM-22, DOM-23, DOM-44; decision D-10).
//
// Per A11.3 + V1.1-UI-DESIGN-SPEC §4 + Thomas §3 + DIN 8238:
//
//   * Two visual groups (A11.9): Feingehalt marks (one required) vs.
//     additional marks (optional multi-select).
//   * At-least-one-Feingehalt required (Jason's tightening of A11.3;
//     Thomas §3 "Meisterzeichen alleine ist kein Reinheits-Audit") —
//     UNLESS the goldsmith documents "nicht punziert: <Grund>" instead
//     (D-10 soft gate: the mirror-image rule on the backend guard, see
//     services/order_workflow._check_punzierung_requirement).
//   * Confirm = btn-primary (happy path). Cancel = btn-secondary.
//   * German labels exactly per A11.3 spec.
//
// Backend contract: PATCH /orders/{id} accepts
// punzierung_verified_marks: string[] (min_length=1) and sets
// punzierung_verified_at server-side (Slice 5 OrderUpdate).
//
// Hallmark vocabulary matches the server field_validator allow-list
// (services/hallmark_vocabulary.py — the same table, mirrored here so the
// modal never drifts from what the backend will accept):
//   feingehalt_{333,375,585,750,900,999} (Gold), feingehalt_925/800/999_ag
//   (Silber), feingehalt_950_pt (Platin), meisterzeichen, herstellerzeichen,
//   laenderzeichen, or "nicht punziert: <Grund>".
//
// The Feingehalt option matching the order's alloy is not pre-checked —
// this check exists so the goldsmith confirms what they physically read
// off the piece, not what the database already believes (D-10 keeps this
// a QC step, not a rubber stamp). It is instead flagged as the suggested
// match so the right checkbox is easy to find.

import React, {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';

import type { ModalStackInjectedProps } from '../../lib/modal-stack';
import '../../styles/components/PunzierungsCheckModal.css';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A punzierung_verified_marks entry: a Feingehalt/additional mark code, or
 * a free-text "nicht punziert: <Grund>" entry (D-10). */
export type PunzierungMark = string;

export interface PunzierungsCheckPayload {
  marks: PunzierungMark[];
}

export type PunzierungsCheckModalProps = {
  orderId: number;
  /** Order alloy, e.g. "750" — informational subline and suggested-mark hint. */
  orderAlloy?: string;
  /** Optional order title for context line. */
  orderTitle?: string;
}

interface MarkOption {
  id: PunzierungMark;
  label: string;
}

// Alloy strings as OrderFormModal.ALLOY_OPTIONS sends them (case-insensitive
// match), mapped to the Feingehalt option they suggest.
const ALLOY_TO_FEINGEHALT_ID: Readonly<Record<string, PunzierungMark>> = {
  '999': 'feingehalt_999',
  '900': 'feingehalt_900',
  '750': 'feingehalt_750',
  '585': 'feingehalt_585',
  '375': 'feingehalt_375',
  '333': 'feingehalt_333',
  ag999: 'feingehalt_999_ag',
  ag925: 'feingehalt_925',
  ag800: 'feingehalt_800',
  pt950: 'feingehalt_950_pt',
};

function suggestedFeingehaltId(alloy?: string): PunzierungMark | undefined {
  if (!alloy) return undefined;
  return ALLOY_TO_FEINGEHALT_ID[alloy.trim().toLowerCase()];
}

// DOM-22: the original vocabulary covered only 585/750/925/950pt, forcing a
// false record for any other alloy the order form actually offers. Order
// is deliberately stable (not alloy-sorted) so an existing selection's
// resulting payload order never changes underfoot.
const FEINGEHALT_OPTIONS: readonly MarkOption[] = [
  { id: 'feingehalt_585', label: 'Feingehaltspunze 585' },
  { id: 'feingehalt_750', label: 'Feingehaltspunze 750' },
  { id: 'feingehalt_925', label: 'Feingehaltspunze 925' },
  { id: 'feingehalt_950_pt', label: 'Feingehaltspunze Pt 950' },
  { id: 'feingehalt_333', label: 'Feingehaltspunze 333' },
  { id: 'feingehalt_375', label: 'Feingehaltspunze 375' },
  { id: 'feingehalt_900', label: 'Feingehaltspunze 900' },
  { id: 'feingehalt_999', label: 'Feingehaltspunze 999' },
  { id: 'feingehalt_800', label: 'Feingehaltspunze Ag 800' },
  { id: 'feingehalt_999_ag', label: 'Feingehaltspunze Ag 999' },
];

const ADDITIONAL_OPTIONS: readonly MarkOption[] = [
  { id: 'meisterzeichen', label: 'Meisterzeichen' },
  { id: 'herstellerzeichen', label: 'Herstellerzeichen' },
  { id: 'laenderzeichen', label: 'Länderzeichen (Export)' },
];

const FEINGEHALT_IDS: ReadonlySet<PunzierungMark> = new Set(
  FEINGEHALT_OPTIONS.map((o) => o.id),
);

/** D-10: the piece was deliberately left unhallmarked — matches the
 * backend's services/hallmark_vocabulary.NICHT_PUNZIERT_PREFIX exactly. */
const NICHT_PUNZIERT_PREFIX = 'nicht punziert: ';

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

type InjectedProps = ModalStackInjectedProps<PunzierungsCheckPayload>;

export const PunzierungsCheckModal: React.FC<
  PunzierungsCheckModalProps & InjectedProps
> = ({ orderId, orderAlloy, orderTitle, resolve, reject }) => {
  const [selected, setSelected] = useState<Set<PunzierungMark>>(
    () => new Set(),
  );
  const [isNichtPunziert, setIsNichtPunziert] = useState(false);
  const [reason, setReason] = useState('');
  const rootRef = useRef<HTMLDivElement | null>(null);
  const firstCheckboxRef = useRef<HTMLInputElement | null>(null);
  const reasonFieldId = useId();

  const suggestedId = suggestedFeingehaltId(orderAlloy);

  useEffect(() => {
    const rafId = window.requestAnimationFrame(() => {
      firstCheckboxRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(rafId);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        reject(new Error('cancelled'));
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
  }, [reject]);

  const toggle = useCallback((id: PunzierungMark): void => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleToggleNichtPunziert = useCallback((checked: boolean): void => {
    setIsNichtPunziert(checked);
    if (checked) {
      // Claiming "not hallmarked" while a Feingehalt box stays checked is
      // contradictory — clear any Feingehalt selection, keep additional
      // marks (a Meisterzeichen can be present without a Feingehaltspunze).
      setSelected((prev) => {
        const next = new Set(prev);
        for (const id of FEINGEHALT_IDS) next.delete(id);
        return next;
      });
    } else {
      setReason('');
    }
  }, []);

  const hasFeingehalt = Array.from(selected).some((m) =>
    FEINGEHALT_IDS.has(m),
  );
  const hasDocumentedReason = isNichtPunziert && reason.trim().length > 0;
  const canSubmit = hasFeingehalt || hasDocumentedReason;

  const handleConfirm = useCallback((): void => {
    if (!canSubmit) return;
    const marks: PunzierungMark[] = [];
    if (isNichtPunziert) {
      marks.push(`${NICHT_PUNZIERT_PREFIX}${reason.trim()}`);
    } else {
      for (const opt of FEINGEHALT_OPTIONS) {
        if (selected.has(opt.id)) marks.push(opt.id);
      }
    }
    for (const opt of ADDITIONAL_OPTIONS) {
      if (selected.has(opt.id)) marks.push(opt.id);
    }
    // Short tactile tick acknowledging the write — per Jason §7.3.
    if (
      typeof navigator !== 'undefined' &&
      typeof navigator.vibrate === 'function'
    ) {
      navigator.vibrate(50);
    }
    resolve({ marks });
  }, [canSubmit, isNichtPunziert, reason, resolve, selected]);

  const handleCancel = useCallback((): void => {
    reject(new Error('cancelled'));
  }, [reject]);

  const renderOption = (
    opt: MarkOption,
    index: number,
    group: 'feingehalt' | 'additional',
  ): React.ReactNode => {
    const isChecked = selected.has(opt.id);
    const isSuggested = group === 'feingehalt' && opt.id === suggestedId;
    const ref =
      group === 'feingehalt' && index === 0 ? firstCheckboxRef : undefined;
    return (
      <label
        key={opt.id}
        className={
          isSuggested ? 'punz-checkbox punz-checkbox--suggested' : 'punz-checkbox'
        }
        data-testid={`punz-option-${opt.id}`}
      >
        <input
          type="checkbox"
          checked={isChecked}
          onChange={() => toggle(opt.id)}
          disabled={group === 'feingehalt' && isNichtPunziert}
          ref={ref}
          aria-label={
            isSuggested ? `${opt.label} (passend zur Legierung)` : opt.label
          }
        />
        <span>
          {opt.label}
          {isSuggested ? (
            <span className="punz-suggested-hint"> (passend zur Legierung)</span>
          ) : null}
        </span>
      </label>
    );
  };

  return (
    <div className="punz-overlay" aria-hidden="false">
      <div
        className="punz-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="punz-title"
        aria-describedby="punz-help"
        data-testid="punz-modal"
        ref={rootRef}
      >
        <div className="punz-header">
          <h2 id="punz-title" className="punz-title">
            Punzierungs-Check
          </h2>
          <button
            type="button"
            className="punz-close"
            onClick={handleCancel}
            aria-label="Schliessen"
            data-testid="punz-close"
          >
            ✕
          </button>
        </div>
        <p className="punz-sub" data-testid="punz-sub">
          Auftrag ORDER:{orderId}
          {orderTitle ? ` · ${orderTitle}` : ''}
          {orderAlloy ? ` · ${orderAlloy}` : ''}
        </p>

        <fieldset
          className="punz-group punz-group--feingehalt"
          aria-required="true"
          aria-disabled={isNichtPunziert || undefined}
          data-testid="punz-group-feingehalt"
        >
          <legend className="punz-group__legend">
            Feingehaltspunze (mindestens eine erforderlich)
          </legend>
          {FEINGEHALT_OPTIONS.map((opt, i) => renderOption(opt, i, 'feingehalt'))}
        </fieldset>

        <div className="punz-divider" aria-hidden="true" />

        <fieldset
          className="punz-group punz-group--other"
          data-testid="punz-group-other"
        >
          <legend className="punz-group__legend">Zusaetzliche Punzen</legend>
          {ADDITIONAL_OPTIONS.map((opt, i) => renderOption(opt, i, 'additional'))}
        </fieldset>

        <div className="punz-divider" aria-hidden="true" />

        <fieldset
          className="punz-group punz-group--nicht-punziert"
          data-testid="punz-group-nicht-punziert"
        >
          <legend className="punz-group__legend">Nicht punziert</legend>
          <label className="punz-checkbox" data-testid="punz-nicht-punziert-toggle">
            <input
              type="checkbox"
              checked={isNichtPunziert}
              onChange={(e) => handleToggleNichtPunziert(e.target.checked)}
              aria-label="Nicht punziert (Grund angeben)"
            />
            <span>Nicht punziert (Grund angeben)</span>
          </label>
          {isNichtPunziert ? (
            <div className="punz-reason-field">
              <label htmlFor={reasonFieldId}>Grund</label>
              <textarea
                id={reasonFieldId}
                data-testid="punz-nicht-punziert-reason"
                rows={2}
                value={reason}
                aria-required="true"
                onChange={(e) => setReason(e.target.value)}
              />
            </div>
          ) : null}
        </fieldset>

        <p id="punz-help" className="punz-help" data-testid="punz-help">
          Hinweis: Mindestens eine Feingehaltspunze muss bestätigt werden —
          oder ein Grund für „nicht punziert“. Zeitstempel und Prüfer
          werden gespeichert.
        </p>
        {!canSubmit ? (
          <p
            className="punz-validation"
            role="status"
            aria-live="polite"
            data-testid="punz-validation"
          >
            {isNichtPunziert
              ? 'Bitte einen Grund angeben.'
              : 'Bitte mindestens eine Feingehaltspunze auswählen.'}
          </p>
        ) : null}

        <div className="punz-actions">
          <button
            type="button"
            className="btn-secondary punz-btn-cancel"
            onClick={handleCancel}
            data-testid="punz-cancel"
            aria-label="Abbrechen"
          >
            Abbrechen
          </button>
          <button
            type="button"
            className="btn-primary punz-btn-confirm"
            onClick={handleConfirm}
            disabled={!canSubmit}
            data-testid="punz-confirm"
            aria-label="Bestaetigen"
          >
            Bestaetigen
          </button>
        </div>
      </div>
    </div>
  );
};

export default PunzierungsCheckModal;
