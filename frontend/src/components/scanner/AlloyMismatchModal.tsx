// AlloyMismatchModal — Slice 11 stacked modal for conscious alloy override.
//
// Per A11.1 / A11.2 + Jason V1.1-UI-DESIGN-SPEC §3 + Thomas §3:
//
//   * Amber banner at top (var(--color-warning-500) — NOT red per A11.7).
//   * PRIMARY action = Abbrechen (gold gradient), autofocus on mount.
//   * Override is secondary (btn-warning amber) — disabled until BOTH:
//       - override_reason_category radio is selected
//       - override_reason textarea has ≥ 3 chars (<= 200 chars)
//   * B3 PII guardrail: inline hint "Keine Kundennamen eingeben";
//     client-side regex blocks submit if @ present or > 15 alphabetic
//     chars in a single token (server enforces per A14.8).
//   * navigator.vibrate(200) on override confirm — tactile acknowledgement
//     of a documented deviation (NOT a reward).
//
// German labels throughout. No English UI strings.
//
// Props come from fireModal(); resolve/reject injected by modal-stack.

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import type { ModalStackInjectedProps } from '../../lib/modal-stack';
import '../../styles/components/AlloyMismatchModal.css';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AlloyOverrideCategory =
  | 'charge_abweichung'
  | 'kleinteil'
  | 'notfall'
  | 'sonstiges';

export interface AlloyOverridePayload {
  override_reason_category: AlloyOverrideCategory;
  override_reason: string;
}

export interface AlloyMismatchModalProps {
  /** Order-declared alloy, e.g. "750" or "750 GG". */
  orderAlloy: string;
  /** Metal-inventory alloy actually scanned, e.g. "585". */
  metalAlloy: string;
  /** Weight to be consumed — shown for transparency on confirmation. */
  weightGrams: number;
  /** Optional order title for context. */
  orderTitle?: string;
}

interface CategoryOption {
  id: AlloyOverrideCategory;
  label: string;
}

const CATEGORY_OPTIONS: CategoryOption[] = [
  {
    id: 'charge_abweichung',
    label: 'Charge-Abweichung (gleiche Legierung, andere Farbe)',
  },
  { id: 'kleinteil', label: 'Kleinteil aus Restmaterial' },
  { id: 'notfall', label: 'Notfall — Kunde wartet' },
  { id: 'sonstiges', label: 'Sonstiges' },
];

const MIN_REASON = 3;
const MAX_REASON = 200;

// ---------------------------------------------------------------------------
// PII guardrail (B3) — client-side defensive check.
// ---------------------------------------------------------------------------
//
// We do NOT trust the client to catch everything. The server has the
// authoritative check per A14.8. This is a UX guardrail: fail fast so the
// goldsmith corrects the input before submit.

/** Contains an @ sign → very likely an email address → block. */
function containsEmailSign(input: string): boolean {
  return /@/.test(input);
}

/**
 * Contains a single alphabetic token longer than 15 characters → very
 * likely a customer name or proper noun → block. Regex is deliberately
 * greedy on diacritics so German names (Müller, Schröder) are matched.
 */
function containsLongAlphaToken(input: string): boolean {
  const tokens = input.split(/\s+/);
  const longAlphaRegex = /^[A-Za-zÀ-ÿ\u00DF]{16,}$/;
  return tokens.some((t) => longAlphaRegex.test(t));
}

export function reasonHasPiiSignal(input: string): boolean {
  return containsEmailSign(input) || containsLongAlphaToken(input);
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

type InjectedProps = ModalStackInjectedProps<AlloyOverridePayload>;

export const AlloyMismatchModal: React.FC<
  AlloyMismatchModalProps & InjectedProps
> = ({
  orderAlloy,
  metalAlloy,
  weightGrams,
  orderTitle,
  resolve,
  reject,
}) => {
  const [category, setCategory] = useState<AlloyOverrideCategory | null>(null);
  const [reason, setReason] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const rootRef = useRef<HTMLDivElement | null>(null);
  const cancelBtnRef = useRef<HTMLButtonElement | null>(null);

  // Autofocus Cancel on mount (A11.1 — default intent is to back out).
  useEffect(() => {
    const rafId = window.requestAnimationFrame(() => {
      cancelBtnRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(rafId);
  }, []);

  // Focus trap + Esc = cancel.
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

  const trimmedReason = reason.trim();
  const reasonValid =
    trimmedReason.length >= MIN_REASON && trimmedReason.length <= MAX_REASON;
  const categoryValid = category !== null;
  const piiSignal = reasonHasPiiSignal(reason);
  const canSubmit =
    categoryValid && reasonValid && !piiSignal && !submitting;

  const handleReasonChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const next = e.target.value;
      if (next.length > MAX_REASON) {
        // Block typing past the max.
        return;
      }
      setReason(next);
    },
    [],
  );

  const handleConfirm = useCallback((): void => {
    if (!canSubmit || category === null) return;
    if (piiSignal) {
      setSubmitError(
        'Begruendung enthält Kundennamen oder Kontakt. Bitte nur sachliche Angabe.',
      );
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    // Tactile acknowledgement of conscious deviation (A11.1 spirit).
    if (
      typeof navigator !== 'undefined' &&
      typeof navigator.vibrate === 'function'
    ) {
      navigator.vibrate(200);
    }
    resolve({
      override_reason_category: category,
      override_reason: trimmedReason,
    });
  }, [canSubmit, category, piiSignal, resolve, trimmedReason]);

  const handleCancel = useCallback((): void => {
    reject(new Error('cancelled'));
  }, [reject]);

  const counterClass = useMemo<string>(() => {
    const len = reason.length;
    if (len >= MAX_REASON) return 'alloy-counter alloy-counter--at-max';
    if (len >= 180) return 'alloy-counter alloy-counter--near-max';
    return 'alloy-counter';
  }, [reason.length]);

  return (
    <div className="alloy-mismatch-overlay" aria-hidden="false">
      <div
        className="alloy-mismatch-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="alloy-title"
        data-testid="alloy-mismatch-modal"
        ref={rootRef}
      >
        <div
          className="alloy-banner"
          role="alert"
          aria-live="assertive"
          data-testid="alloy-banner"
        >
          <span className="alloy-banner__icon" aria-hidden="true">
            ⚠
          </span>
          <span className="alloy-banner__text" id="alloy-title">
            Legierungsabweichung
          </span>
        </div>

        <div className="alloy-flow">
          <div className="alloy-flow__row">
            <span className="alloy-flow__label">Auftrag verlangt</span>
            <span
              className="alloy-flow__value"
              data-testid="alloy-order-alloy"
            >
              {orderAlloy}
            </span>
          </div>
          <div className="alloy-flow__arrow" aria-hidden="true">
            ↓
          </div>
          <div className="alloy-flow__row">
            <span className="alloy-flow__label">Entnahme erfolgt aus</span>
            <span
              className="alloy-flow__value"
              data-testid="alloy-metal-alloy"
            >
              {metalAlloy}
            </span>
          </div>
          <div className="alloy-flow__meta">
            {orderTitle ? <span>{orderTitle}</span> : null}
            <span data-testid="alloy-weight">
              Entnahme-Gewicht: {weightGrams.toFixed(2)} g
            </span>
          </div>
        </div>

        <fieldset
          className="alloy-fieldset"
          aria-required="true"
          data-testid="alloy-category-fieldset"
        >
          <legend className="alloy-fieldset__legend">
            Grund-Kategorie (Pflicht)
          </legend>
          {CATEGORY_OPTIONS.map((option) => (
            <label
              key={option.id}
              className="alloy-radio"
              data-testid={`alloy-category-${option.id}`}
            >
              <input
                type="radio"
                name="override-category"
                value={option.id}
                checked={category === option.id}
                onChange={() => setCategory(option.id)}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </fieldset>

        <div className="alloy-reason">
          <label
            htmlFor="alloy-reason-textarea"
            className="alloy-reason__label"
          >
            Begruendung (3–200 Zeichen, Pflicht)
          </label>
          <textarea
            id="alloy-reason-textarea"
            data-testid="alloy-reason-textarea"
            className="alloy-textarea"
            value={reason}
            onChange={handleReasonChange}
            rows={3}
            maxLength={MAX_REASON}
            aria-required="true"
            aria-describedby="alloy-pii-hint alloy-reason-counter"
            placeholder="Warum weicht die Legierung ab? Diese Angabe erscheint in der Nachkalkulation."
          />
          <div className="alloy-reason__footer">
            <p
              id="alloy-pii-hint"
              className="alloy-reason__pii-hint"
              data-testid="alloy-pii-hint"
            >
              Keine Kundennamen eingeben — nur sachliche Begruendung.
            </p>
            <span
              id="alloy-reason-counter"
              className={counterClass}
              data-testid="alloy-reason-counter"
              aria-live="polite"
            >
              {reason.length}/{MAX_REASON}
            </span>
          </div>
          {piiSignal && reason.length > 0 ? (
            <p
              className="alloy-reason__pii-warn"
              role="alert"
              data-testid="alloy-pii-warn"
            >
              Eingabe enthält möglicherweise Kundennamen oder Kontakt. Bitte
              nur sachliche Begruendung.
            </p>
          ) : null}
        </div>

        {submitError !== null ? (
          <div
            className="alloy-submit-error"
            role="alert"
            data-testid="alloy-submit-error"
          >
            {submitError}
          </div>
        ) : null}

        <div className="alloy-actions">
          <button
            type="button"
            className="btn-primary alloy-btn-cancel"
            onClick={handleCancel}
            ref={cancelBtnRef}
            data-testid="alloy-cancel"
            aria-label="Abbrechen"
          >
            Abbrechen
          </button>
          <button
            type="button"
            className="btn-warning alloy-btn-override"
            onClick={handleConfirm}
            disabled={!canSubmit}
            data-testid="alloy-override"
            aria-label="Trotzdem uebernehmen"
            aria-describedby={
              !canSubmit ? 'alloy-override-help' : undefined
            }
          >
            {submitting ? 'Senden…' : 'Trotzdem uebernehmen'}
          </button>
        </div>
        {!canSubmit ? (
          <p
            id="alloy-override-help"
            className="alloy-override-help"
            data-testid="alloy-override-help"
          >
            Bitte Kategorie und Begruendung auswaehlen, um fortzufahren.
          </p>
        ) : null}
      </div>
    </div>
  );
};

export default AlloyMismatchModal;
