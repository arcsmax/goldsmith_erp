// Modal, Dialog and Sheet (UI-UX-PLAYBOOK 4.3; review 04 section F item 5).
//
// The behaviour layer for every overlay:
// - role="dialog" (or "alertdialog"), aria-modal, labelled by the h2 title,
//   described by the optional description;
// - focus moves in on open (initialFocusRef, else the first control in the
//   body, else the footer, else the dialog) and returns to the trigger on close;
// - Tab and Shift+Tab stay inside; Escape closes; only the top-most open
//   modal reacts, so a Dialog opened from a Modal closes alone;
// - no backdrop close unless dismissOnBackdrop (read-only content only);
// - isDirty asks "Änderungen verwerfen?" before any close (useDirtyGuard);
// - below 600px the modal is a full-screen sheet with the footer pinned
//   (ui.css); Sheet is the bottom-sheet variant at every width.
//
// Built as a portal plus a tested focus trap rather than native <dialog>,
// because happy-dom (the Vitest environment) does not implement showModal().
import React, { useCallback, useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';

import { useDirtyGuard } from '../lib/useDirtyGuard';
import { Button, IconButton, type ButtonVariant } from './Button';
import { cx } from './devAssert';
import { getFocusable, trapTab } from './focus';

export type ModalSize = 'sm' | 'md' | 'lg';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Rendered as h2, wired to aria-labelledby. */
  title: string;
  /** aria-describedby. */
  description?: string;
  size?: ModalSize;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  /** Default false; true only for read-only content. */
  dismissOnBackdrop?: boolean;
  /** Asks "Änderungen verwerfen?" before closing. */
  isDirty?: boolean;
  /** Primary action right on desktop, full-width bottom on phone. */
  footer?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}

interface ModalFrameProps extends ModalProps {
  role?: 'dialog' | 'alertdialog';
  variant?: 'center' | 'sheet';
  hideCloseButton?: boolean;
}

// Open modals, oldest first. Only the last one handles keys.
const openStack: symbol[] = [];
let scrollLocks = 0;

function lockScroll(): void {
  scrollLocks += 1;
  document.body.classList.add('ui-scroll-lock');
}

function unlockScroll(): void {
  scrollLocks = Math.max(0, scrollLocks - 1);
  if (scrollLocks === 0) document.body.classList.remove('ui-scroll-lock');
}

function focusInitial(
  dialog: HTMLElement,
  body: HTMLElement | null,
  footer: HTMLElement | null,
  initialFocusRef?: React.RefObject<HTMLElement | null>,
): void {
  const target =
    initialFocusRef?.current ??
    (body && getFocusable(body)[0]) ??
    (footer && getFocusable(footer)[0]) ??
    dialog;
  target.focus();
}

const ModalFrame: React.FC<ModalFrameProps> = ({
  open,
  onClose,
  title,
  description,
  size = 'md',
  initialFocusRef,
  dismissOnBackdrop = false,
  isDirty = false,
  footer,
  className,
  children,
  role = 'dialog',
  variant = 'center',
  hideCloseButton = false,
}) => {
  const titleId = useId();
  const descriptionId = useId();
  const discardId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const footerRef = useRef<HTMLDivElement>(null);
  const keepEditingRef = useRef<HTMLButtonElement>(null);
  const guard = useDirtyGuard(open && isDirty, onClose);
  const { isConfirming, requestClose, keepEditing } = guard;

  const onEscape = useCallback(() => {
    if (isConfirming) keepEditing();
    else requestClose();
  }, [isConfirming, keepEditing, requestClose]);
  // Read by the document key listener, so it always sees the latest state.
  const handlersRef = useRef({ onEscape });
  handlersRef.current = { onEscape };

  // Open / close lifecycle: stack, scroll lock, initial focus, focus return.
  useEffect(() => {
    if (!open) return undefined;
    const token = Symbol('ui-modal');
    const trigger = document.activeElement as HTMLElement | null;
    openStack.push(token);
    lockScroll();
    const dialog = dialogRef.current;
    if (dialog) focusInitial(dialog, bodyRef.current, footerRef.current, initialFocusRef);

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (openStack[openStack.length - 1] !== token || !dialogRef.current) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        handlersRef.current.onEscape();
        return;
      }
      if (event.key === 'Tab' && trapTab(event, dialogRef.current)) {
        event.preventDefault();
      }
    };
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      const index = openStack.indexOf(token);
      if (index !== -1) openStack.splice(index, 1);
      unlockScroll();
      if (trigger && trigger.isConnected) trigger.focus();
    };
    // Depends on `open` only: initialFocusRef is read once on open by design,
    // and the key handler reads the latest state through handlersRef.
  }, [open]);

  // The discard question takes focus on its safe choice.
  useEffect(() => {
    if (isConfirming) keepEditingRef.current?.focus();
  }, [isConfirming]);

  if (!open) return null;

  return createPortal(
    <div className="ui-modal-root">
      <div
        className="ui-modal-backdrop"
        data-testid="ui-modal-backdrop"
        aria-hidden="true"
        onClick={dismissOnBackdrop ? requestClose : undefined}
      />
      <div
        ref={dialogRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cx(
          'ui-modal',
          `ui-modal--${size}`,
          variant === 'sheet' && 'ui-modal--sheet',
          className,
        )}
      >
        <div className="ui-modal__header">
          <h2 id={titleId} className="ui-modal__title">
            {title}
          </h2>
          {!hideCloseButton && (
            <IconButton icon="close" label="Schließen" onClick={requestClose} />
          )}
        </div>
        <div ref={bodyRef} className="ui-modal__body">
          {description && (
            <p id={descriptionId} className="ui-modal__description">
              {description}
            </p>
          )}
          {children}
        </div>
        {isConfirming ? (
          <div
            className="ui-modal__footer ui-modal__discard"
            role="group"
            aria-labelledby={discardId}
          >
            <p id={discardId} className="ui-modal__discard-text">
              Änderungen verwerfen?
            </p>
            <Button ref={keepEditingRef} variant="secondary" onClick={keepEditing}>
              Weiter bearbeiten
            </Button>
            <Button variant="danger" onClick={guard.discard}>
              Verwerfen
            </Button>
          </div>
        ) : (
          footer && (
            <div ref={footerRef} className="ui-modal__footer">
              {footer}
            </div>
          )
        )}
      </div>
    </div>,
    document.body,
  );
};

/** Every overlay with content: forms, details, pickers. */
export const Modal: React.FC<ModalProps> = (props) => <ModalFrame {...props} />;

/** Bottom sheet at every width (scan results, quick actions). */
export const Sheet: React.FC<ModalProps> = (props) => <ModalFrame {...props} variant="sheet" />;

export interface DialogProps {
  open: boolean;
  title: string;
  message: string;
  /** Default "Löschen" for danger, "Bestätigen" otherwise. */
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'danger';
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * A short question with two answers (role="alertdialog"). Focus starts on the
 * cancel button, the safer default for destructive actions. For the promise
 * API keep using useConfirm(); this is the declarative form.
 */
export const Dialog: React.FC<DialogProps> = ({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel = 'Abbrechen',
  variant = 'default',
  loading = false,
  onConfirm,
  onCancel,
}) => {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmVariant: ButtonVariant = variant === 'danger' ? 'danger' : 'primary';
  const resolvedConfirmLabel = confirmLabel ?? (variant === 'danger' ? 'Löschen' : 'Bestätigen');
  return (
    <ModalFrame
      open={open}
      onClose={onCancel}
      title={title}
      description={message}
      size="sm"
      role="alertdialog"
      hideCloseButton
      initialFocusRef={cancelRef}
      footer={
        <>
          <Button ref={cancelRef} variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant={confirmVariant} loading={loading} onClick={onConfirm}>
            {resolvedConfirmLabel}
          </Button>
        </>
      }
    />
  );
};
