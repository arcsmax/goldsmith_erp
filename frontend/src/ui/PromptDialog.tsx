// PromptDialog (review 04 section F item 5): the accessible replacement for
// window.prompt(). A Modal with one Field, Enter submits, Escape cancels,
// optional required check and custom German validator.
//
// Declarative: <PromptDialog open ... onSubmit onCancel />.
// Imperative:  const { prompt, dialog } = usePromptDialog();
//              const reason = await prompt({ title, label }); // string | null
//              ...render {dialog} once in the component.
// For yes/no questions keep using useConfirm() (ConfirmDialog) or <Dialog>.
import React, { useCallback, useEffect, useId, useRef, useState } from 'react';

import { Button } from './Button';
import { Field, type FieldInputMode } from './Field';
import { Modal } from './Modal';

export interface PromptOptions {
  title: string;
  label: string;
  description?: string;
  help?: string;
  defaultValue?: string;
  placeholder?: string;
  /** Default "Übernehmen". Prefer verb + noun ("Ablehnung senden"). */
  confirmLabel?: string;
  cancelLabel?: string;
  required?: boolean;
  /** Return a German error message, or null when the value is fine. */
  validate?: (value: string) => string | null;
  inputMode?: FieldInputMode;
  multiline?: boolean;
  maxLength?: number;
}

export interface PromptDialogProps extends PromptOptions {
  open: boolean;
  /** Receives the trimmed value. */
  onSubmit: (value: string) => void;
  onCancel: () => void;
}

export const PromptDialog: React.FC<PromptDialogProps> = ({
  open,
  title,
  label,
  description,
  help,
  defaultValue = '',
  placeholder,
  confirmLabel = 'Übernehmen',
  cancelLabel = 'Abbrechen',
  required = false,
  validate,
  inputMode,
  multiline = false,
  maxLength,
  onSubmit,
  onCancel,
}) => {
  const formId = useId();
  const inputRef = useRef<HTMLInputElement & HTMLTextAreaElement>(null);
  const [value, setValue] = useState(defaultValue);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setValue(defaultValue);
      setError(null);
    }
  }, [open, defaultValue]);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const trimmed = value.trim();
    const problem =
      required && trimmed.length === 0 ? `${label} fehlt. Bitte ausfüllen.` : validate?.(trimmed) ?? null;
    if (problem) {
      setError(problem);
      inputRef.current?.focus();
      return;
    }
    onSubmit(trimmed);
  };

  const handleChange = (
    event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ): void => {
    setValue(event.target.value);
    if (error) setError(null);
  };

  const controlProps = {
    ref: inputRef,
    value,
    placeholder,
    maxLength,
    onChange: handleChange,
  };

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      description={description}
      size="sm"
      initialFocusRef={inputRef}
      isDirty={multiline && value.trim() !== defaultValue.trim()}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button type="submit" form={formId}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={handleSubmit} noValidate>
        <Field
          label={label}
          name="prompt-value"
          required={required}
          help={help}
          error={error ?? undefined}
          inputMode={inputMode}
        >
          {multiline ? <textarea rows={4} {...controlProps} /> : <input type="text" {...controlProps} />}
        </Field>
      </form>
    </Modal>
  );
};

const CLOSED_OPTIONS: PromptOptions = { title: '', label: '' };

interface PendingPrompt {
  options: PromptOptions;
  resolve: (value: string | null) => void;
}

/** Promise-based prompt: resolves with the value, or null when cancelled. */
export function usePromptDialog(): {
  prompt: (options: PromptOptions) => Promise<string | null>;
  dialog: React.ReactElement;
} {
  const [pending, setPending] = useState<PendingPrompt | null>(null);

  const prompt = useCallback(
    (options: PromptOptions) =>
      new Promise<string | null>((resolve) => {
        setPending({ options, resolve });
      }),
    [],
  );

  const settle = useCallback(
    (value: string | null) => {
      pending?.resolve(value);
      setPending(null);
    },
    [pending],
  );

  const dialog = (
    <PromptDialog
      {...(pending?.options ?? CLOSED_OPTIONS)}
      open={pending !== null}
      onSubmit={(value) => settle(value)}
      onCancel={() => settle(null)}
    />
  );

  return { prompt, dialog };
}
