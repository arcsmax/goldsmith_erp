// StatusChangeDialog — reason (and resume date) for Pausiert / Storniert
// (W2-08, DOM-18; backend order_workflow.REASON_REQUIRED).
//
// Built on the src/ui Modal (W4-03): focus trap, Escape, focus return, no
// backdrop close, "Änderungen verwerfen?" once a reason is typed, full-screen
// sheet below 600px. Field gives the label, the Pflichtfeld marker and the
// error text.
import { useId, useRef, useState, type FormEvent } from 'react';
import type { OrderStatus } from '../../types';
import { Button, Field, Modal } from '../../ui';

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
  const formId = useId();
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const [reason, setReason] = useState('');
  const [resumeDate, setResumeDate] = useState('');
  const [reasonError, setReasonError] = useState<string | null>(null);

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

  const isDirty = reason.trim() !== '' || resumeDate !== '';
  const footer = (
    <>
      <Button variant="secondary" onClick={onCancel} disabled={isSubmitting}>
        Abbrechen
      </Button>
      <Button
        type="submit"
        form={formId}
        variant={target === 'cancelled' ? 'danger' : 'primary'}
        loading={isSubmitting}
      >
        {copy.confirmLabel}
      </Button>
    </>
  );

  return (
    <Modal
      open
      onClose={onCancel}
      title={copy.title}
      description={copy.message}
      size="sm"
      initialFocusRef={reasonRef}
      isDirty={isDirty && !isSubmitting}
      footer={footer}
    >
      <form id={formId} onSubmit={handleSubmit} noValidate className="status-change-form">
        <Field label={copy.reasonLabel} name="reason" required error={reasonError ?? undefined}>
          <textarea
            ref={reasonRef}
            rows={3}
            maxLength={REASON_MAX_LENGTH}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={isSubmitting}
          />
        </Field>
        {target === 'on_hold' && (
          <Field label="Weiter am (optional)" name="resume_date">
            <input
              type="date"
              min={todayIso()}
              value={resumeDate}
              onChange={(e) => setResumeDate(e.target.value)}
              disabled={isSubmitting}
            />
          </Field>
        )}
        {errorMessage && (
          <p className="status-change-error" role="alert">
            {errorMessage}
          </p>
        )}
      </form>
    </Modal>
  );
}

export default StatusChangeDialog;
