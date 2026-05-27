// PunzierungsCheckModal — Slice 11 stacked modal for hallmark verification.
//
// Per A11.3 + V1.1-UI-DESIGN-SPEC §4 + Thomas §3 + DIN 8238:
//
//   * Two visual groups (A11.9): Feingehalt marks (one required) vs.
//     additional marks (optional multi-select).
//   * At-least-one-Feingehalt required (Jason's tightening of A11.3;
//     Thomas §3 "Meisterzeichen alleine ist kein Reinheits-Audit").
//   * Confirm = btn-primary (happy path). Cancel = btn-secondary.
//   * German labels exactly per A11.3 spec.
//
// Backend contract: PATCH /orders/{id} accepts
// punzierung_verified_marks: string[] (min_length=1) and sets
// punzierung_verified_at server-side (Slice 5 OrderUpdate).
//
// Hallmark vocabulary matches the server field_validator allow-list:
//   feingehalt_585, feingehalt_750, feingehalt_925, feingehalt_950_pt,
//   meisterzeichen, herstellerzeichen, laenderzeichen

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';

import type { ModalStackInjectedProps } from '../../lib/modal-stack';
import '../../styles/components/PunzierungsCheckModal.css';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PunzierungMark =
  | 'feingehalt_585'
  | 'feingehalt_750'
  | 'feingehalt_925'
  | 'feingehalt_950_pt'
  | 'meisterzeichen'
  | 'herstellerzeichen'
  | 'laenderzeichen';

export interface PunzierungsCheckPayload {
  marks: PunzierungMark[];
}

export type PunzierungsCheckModalProps = {
  orderId: number;
  /** Order alloy, e.g. "750" — informational subline. */
  orderAlloy?: string;
  /** Optional order title for context line. */
  orderTitle?: string;
}

interface MarkOption {
  id: PunzierungMark;
  label: string;
  isFeingehalt: boolean;
}

const FEINGEHALT_OPTIONS: MarkOption[] = [
  { id: 'feingehalt_585', label: 'Feingehaltspunze 585', isFeingehalt: true },
  { id: 'feingehalt_750', label: 'Feingehaltspunze 750', isFeingehalt: true },
  { id: 'feingehalt_925', label: 'Feingehaltspunze 925', isFeingehalt: true },
  {
    id: 'feingehalt_950_pt',
    label: 'Feingehaltspunze Pt 950',
    isFeingehalt: true,
  },
];

const ADDITIONAL_OPTIONS: MarkOption[] = [
  { id: 'meisterzeichen', label: 'Meisterzeichen', isFeingehalt: false },
  { id: 'herstellerzeichen', label: 'Herstellerzeichen', isFeingehalt: false },
  {
    id: 'laenderzeichen',
    label: 'Laenderzeichen (Export)',
    isFeingehalt: false,
  },
];

const FEINGEHALT_IDS: ReadonlySet<PunzierungMark> = new Set(
  FEINGEHALT_OPTIONS.map((o) => o.id),
);

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
  const rootRef = useRef<HTMLDivElement | null>(null);
  const firstCheckboxRef = useRef<HTMLInputElement | null>(null);

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

  const hasFeingehalt = Array.from(selected).some((m) =>
    FEINGEHALT_IDS.has(m),
  );
  const canSubmit = hasFeingehalt;

  const handleConfirm = useCallback((): void => {
    if (!canSubmit) return;
    const marks: PunzierungMark[] = [];
    for (const opt of [...FEINGEHALT_OPTIONS, ...ADDITIONAL_OPTIONS]) {
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
  }, [canSubmit, resolve, selected]);

  const handleCancel = useCallback((): void => {
    reject(new Error('cancelled'));
  }, [reject]);

  const renderOption = (
    opt: MarkOption,
    index: number,
    group: 'feingehalt' | 'additional',
  ): React.ReactNode => {
    const isChecked = selected.has(opt.id);
    const ref =
      group === 'feingehalt' && index === 0 ? firstCheckboxRef : undefined;
    return (
      <label
        key={opt.id}
        className="punz-checkbox"
        data-testid={`punz-option-${opt.id}`}
      >
        <input
          type="checkbox"
          checked={isChecked}
          onChange={() => toggle(opt.id)}
          ref={ref}
          aria-label={opt.label}
        />
        <span>{opt.label}</span>
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

        <p id="punz-help" className="punz-help" data-testid="punz-help">
          Hinweis: Mindestens eine Feingehaltspunze muss bestaetigt werden.
          Zeitstempel und Pruefer werden gespeichert.
        </p>
        {!hasFeingehalt ? (
          <p
            className="punz-validation"
            role="status"
            aria-live="polite"
            data-testid="punz-validation"
          >
            Bitte mindestens eine Feingehaltspunze auswaehlen.
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
