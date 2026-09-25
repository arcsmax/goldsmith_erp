// StatusChangeDialog — reason (and resume date) for Pausiert / Storniert
// (W2-08, DOM-18; backend order_workflow.REASON_REQUIRED).
//
// ConfirmDialog-style modal, reusing its `confirm-dialog-*` look from
// toast.css so no new modal styles are added before the Wave 4 <Modal>.
// Form modal rules: no close on backdrop click, Escape and "Abbrechen"
// close, focus goes to the reason field and returns to the trigger.
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import type { OrderStatus } from '../../types';
import '../../styles/toast.css';

export const REASON_MAX_LENGTH = 500;

export interface StatusChangeRequest {
  status: OrderStatus;
  reason?: string;
  resume_date?: string;
}

interface DialogCopy {
  title: string;
  message: string;
  confirmLabel: string;
  reasonLabel: string;
}

const COPY: Partial<Record<OrderStatus, DialogCopy>> = {
  on_hold: {
    title: 'Auftrag pausieren',
    message: 'Der Auftrag zählt dann nicht mehr für Fristen und Überfällig-Hinweise.',
    confirmLabel: 'Auftrag pausieren',
    reasonLabel: 'Grund der Pause',
  },
  cancelled: {
    title: 'Auftrag stornieren',
    message: 'Ein stornierter Auftrag kann nur als Entwurf wieder geöffnet werden.',
    confirmLabel: 'Auftrag stornieren',
    reasonLabel: 'Grund der Stornierung',
  },
};

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

interface StatusChangeDialogProps {
  target: OrderStatus;
  isSubmitting: boolean;
  /** Backend message of a failed attempt, shown inside the dialog. */
  errorMessage?: string | null;
  onConfirm: (request: StatusChangeRequest) => void;
  onCancel: () => void;
}

export function StatusChangeDialog({
  target,
  isSubmitting,
  errorMessage,
  onConfirm,
  onCancel,
}: StatusChangeDialogProps) {
  const copy = COPY[target];
  const titleId = useId();
  const messageId = useId();
  const reasonId = useId();
  const reasonErrorId = useId();
  const resumeId = useId();
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const [reason, setReason] = useState('');
  const [resumeDate, setResumeDate] = useState('');
  const [reasonError, setReasonError] = useState<string | null>(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    reasonRef.current?.focus();
    return () => previouslyFocused?.focus?.();
  }, []);

  // Escape closes; Tab stays inside the dialog. Bound to `document` (not a
  // JSX onKeyDown on the overlay div) so the overlay stays a non-interactive
  // static element for jsx-a11y — matches ui/Modal.tsx's focus-trap pattern.
  // Must run unconditionally (before the `!copy` early return) per the Rules
  // of Hooks.
  useEffect(() => {
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCancel();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>('textarea, input, button:not([disabled])')
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onCancel]);

  if (!copy) return null;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = reason.trim();
    if (!trimmed) {
      setReasonError('Grund fehlt. Bitte kurz angeben, warum.');
      reasonRef.current?.focus();
      return;
    }
    setReasonError(null);
    const request: StatusChangeRequest = { status: target, reason: trimmed };
    onConfirm(target === 'on_hold' && resumeDate ? { ...request, resume_date: resumeDate } : request);
  };

  const isDanger = target === 'cancelled';
  return (
    <div className="confirm-dialog-overlay">
      <div
        ref={dialogRef}
        className="confirm-dialog status-change-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={messageId}
      >
        <div className="confirm-dialog-header">
          <h2 id={titleId} className="confirm-dialog-title">
            {copy.title}
          </h2>
        </div>
        <p id={messageId} className="confirm-dialog-message">
          {copy.message}
        </p>
        <form onSubmit={handleSubmit} noValidate>
          <div className="status-change-field">
            <label htmlFor={reasonId}>
              {copy.reasonLabel} <span className="status-change-required">(Pflichtfeld)</span>
            </label>
            <textarea
              ref={reasonRef}
              id={reasonId}
              rows={3}
              maxLength={REASON_MAX_LENGTH}
              value={reason}
              aria-required="true"
              aria-invalid={reasonError ? 'true' : undefined}
              aria-describedby={reasonError ? reasonErrorId : undefined}
              onChange={(e) => setReason(e.target.value)}
              disabled={isSubmitting}
            />
            {reasonError && (
              <p id={reasonErrorId} className="status-change-error">
                {reasonError}
              </p>
            )}
          </div>
          {target === 'on_hold' && (
            <div className="status-change-field">
              <label htmlFor={resumeId}>Weiter am (optional)</label>
              <input
                id={resumeId}
                type="date"
                min={todayIso()}
                value={resumeDate}
                onChange={(e) => setResumeDate(e.target.value)}
                disabled={isSubmitting}
              />
            </div>
          )}
          {errorMessage && (
            <p className="status-change-error" role="alert">
              {errorMessage}
            </p>
          )}
          <div className="confirm-dialog-actions">
            <button
              type="button"
              className="confirm-dialog-cancel"
              onClick={onCancel}
              disabled={isSubmitting}
            >
              Abbrechen
            </button>
            <button
              type="submit"
              className={`confirm-dialog-confirm confirm-dialog-confirm--${isDanger ? 'danger' : 'default'}`}
              disabled={isSubmitting}
              aria-busy={isSubmitting || undefined}
            >
              {copy.confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default StatusChangeDialog;
