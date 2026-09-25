// TimerStopDialog — "Zeiterfassung beenden" on the src/ui Modal (W4-03).
//
// Ratings are 1-to-5 tap targets (56px on the bench), rework is one big
// checkbox, notes are optional. The parent owns the stop call; this dialog
// only collects the input.
import React, { useState } from 'react';

import { Button, Field, Modal } from '../../ui';
import type { TimeEntryStopInput } from '../../types';

const RATING_VALUES = [1, 2, 3, 4, 5] as const;
const DEFAULT_COMPLEXITY = 3;
const DEFAULT_QUALITY = 4;

interface StopFormState {
  complexity_rating: number;
  quality_rating: number;
  rework_required: boolean;
  notes: string;
}

const INITIAL_STATE: StopFormState = {
  complexity_rating: DEFAULT_COMPLEXITY,
  quality_rating: DEFAULT_QUALITY,
  rework_required: false,
  notes: '',
};

interface RatingProps {
  label: string;
  hint: string;
  value: number;
  onChange: (value: number) => void;
}

const RatingField: React.FC<RatingProps> = ({ label, hint, value, onChange }) => (
  <div className="stop-dialog-field" role="group" aria-label={label}>
    <span className="stop-dialog-field__label">{label}</span>
    <div className="star-rating">
      {RATING_VALUES.map((star) => (
        <button
          key={star}
          type="button"
          onClick={() => onChange(star)}
          className={`star ${star <= value ? 'active' : ''}`}
          aria-pressed={star === value}
          aria-label={`${star} von 5`}
        >
          ★
        </button>
      ))}
    </div>
    <span className="rating-hint">{hint}</span>
  </div>
);

export interface TimerStopDialogProps {
  open: boolean;
  elapsedLabel: string;
  isSaving: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: (input: TimeEntryStopInput) => void;
}

export const TimerStopDialog: React.FC<TimerStopDialogProps> = ({
  open,
  elapsedLabel,
  isSaving,
  error,
  onCancel,
  onConfirm,
}) => {
  const [form, setForm] = useState<StopFormState>(INITIAL_STATE);
  const update = (patch: Partial<StopFormState>) => setForm((prev) => ({ ...prev, ...patch }));

  const close = () => {
    setForm(INITIAL_STATE);
    onCancel();
  };
  const confirm = () =>
    onConfirm({
      complexity_rating: form.complexity_rating,
      quality_rating: form.quality_rating,
      rework_required: form.rework_required,
      notes: form.notes || undefined,
    });

  return (
    <Modal
      open={open}
      onClose={close}
      title="Zeiterfassung beenden"
      size="md"
      footer={
        <>
          <Button variant="secondary" size="lg" onClick={close} disabled={isSaving}>
            Abbrechen
          </Button>
          <Button size="lg" icon="check" loading={isSaving} onClick={confirm}>
            Stoppen &amp; speichern
          </Button>
        </>
      }
    >
      <div className="stop-dialog-content">
        <RatingField
          label="Komplexität (1-5)"
          hint="Wie schwierig war die Aufgabe?"
          value={form.complexity_rating}
          onChange={(value) => update({ complexity_rating: value })}
        />
        <RatingField
          label="Qualität (1-5)"
          hint="Wie zufrieden sind Sie mit dem Ergebnis?"
          value={form.quality_rating}
          onChange={(value) => update({ quality_rating: value })}
        />
        <label className="stop-dialog-check">
          <input
            type="checkbox"
            checked={form.rework_required}
            onChange={(e) => update({ rework_required: e.target.checked })}
          />
          Nacharbeit erforderlich
        </label>
        <Field label="Notizen (optional)" name="timer-stop-notes">
          <textarea
            id="timer-stop-notes"
            value={form.notes}
            onChange={(e) => update({ notes: e.target.value })}
            placeholder="Zusätzliche Notizen…"
            rows={3}
          />
        </Field>
        <p className="stop-dialog-summary">
          <strong>Zeit:</strong> <span className="stop-dialog-summary__time">{elapsedLabel}</span>
        </p>
        {error && (
          <p className="stop-dialog-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
};

export default TimerStopDialog;
