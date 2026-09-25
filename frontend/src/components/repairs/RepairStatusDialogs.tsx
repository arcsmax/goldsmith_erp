// The two status steps that need a form first (W4-03): "Diagnose stellen"
// (Befund, Kostenvoranschlag, Termin) and "Fertigmelden" (tatsächliche
// Kosten). react-hook-form + zod on the Modal primitive: dirty forms ask
// before closing, the backdrop never closes them, and a failed request keeps
// the form open with the backend's message.
import React, { useId } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { Button, Field, Icon, Modal } from '../../ui';
import { parsePrice } from './intakeOptions';
import {
  completeSchema,
  diagnoseSchema,
  toAmountInput,
  type CompleteValues,
  type DiagnoseValues,
} from './repairSchemas';
import type { RepairTransition } from './useRepairActions';

interface DialogBaseProps {
  open: boolean;
  isSubmitting: boolean;
  /** Message of the last failed submit, or null. */
  error: string | null;
  onSubmit: (transition: RepairTransition) => void;
  onClose: () => void;
}

const SubmitError: React.FC<{ message: string | null }> = ({ message }) =>
  message ? (
    <p className="ui-field__error" role="alert">
      <Icon name="alert-triangle" />
      <span>{message}</span>
    </p>
  ) : null;

export const DiagnoseDialog: React.FC<DialogBaseProps> = ({
  open,
  isSubmitting,
  error,
  onSubmit,
  onClose,
}) => {
  const formId = useId();
  const { register, handleSubmit, formState } = useForm<DiagnoseValues>({
    defaultValues: { diagnosisNotes: '', estimatedCost: '', estimatedCompletionDate: '' },
    resolver: zodResolver(diagnoseSchema),
  });
  const { errors, isDirty } = formState;

  const submit = handleSubmit((values) =>
    onSubmit({
      action: 'diagnose',
      diagnosis_notes: values.diagnosisNotes.trim(),
      estimated_cost: parsePrice(values.estimatedCost) ?? 0,
      estimated_completion_date: values.estimatedCompletionDate
        ? new Date(values.estimatedCompletionDate).toISOString()
        : undefined,
    }),
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Diagnose stellen"
      isDirty={isDirty}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Abbrechen
          </Button>
          <Button type="submit" form={formId} loading={isSubmitting}>
            Diagnose speichern
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="repair-dialog-form">
        <SubmitError message={error} />
        <Field label="Befundbeschreibung" name="diagnosisNotes" required error={errors.diagnosisNotes?.message}>
          <textarea
            rows={5}
            placeholder="Was wurde festgestellt? Welche Arbeiten sind erforderlich?"
            {...register('diagnosisNotes')}
          />
        </Field>
        <Field
          label="Kostenvoranschlag"
          name="estimatedCost"
          required
          inputMode="decimal"
          suffix="€"
          error={errors.estimatedCost?.message}
        >
          <input placeholder="z. B. 45,00" {...register('estimatedCost')} />
        </Field>
        <Field label="Fertigstellung bis" name="estimatedCompletionDate">
          <input type="date" {...register('estimatedCompletionDate')} />
        </Field>
      </form>
    </Modal>
  );
};

interface CompleteDialogProps extends DialogBaseProps {
  estimatedCost: number | null | undefined;
}

export const CompleteDialog: React.FC<CompleteDialogProps> = ({
  open,
  estimatedCost,
  isSubmitting,
  error,
  onSubmit,
  onClose,
}) => {
  const formId = useId();
  const { register, handleSubmit, formState } = useForm<CompleteValues>({
    defaultValues: { actualCost: toAmountInput(estimatedCost) },
    resolver: zodResolver(completeSchema),
  });
  const { errors, isDirty } = formState;

  const submit = handleSubmit((values) =>
    onSubmit({ action: 'complete', actual_cost: parsePrice(values.actualCost) ?? 0 }),
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Reparatur fertigmelden"
      description="Die Reparatur wird auf „Abholbereit“ gesetzt und alle Mitarbeiter werden benachrichtigt."
      isDirty={isDirty}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Abbrechen
          </Button>
          <Button type="submit" form={formId} icon="circle-check" loading={isSubmitting}>
            Fertigmelden
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="repair-dialog-form">
        <SubmitError message={error} />
        {estimatedCost != null && (
          <p className="repair-dialog-form__hint">
            Kostenvoranschlag: <strong className={MONEY_CLASS}>{formatEur(estimatedCost)}</strong>
          </p>
        )}
        <Field
          label="Tatsächliche Kosten"
          name="actualCost"
          required
          inputMode="decimal"
          suffix="€"
          error={errors.actualCost?.message}
        >
          <input {...register('actualCost')} />
        </Field>
      </form>
    </Modal>
  );
};
