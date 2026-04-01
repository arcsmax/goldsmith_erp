// ConfirmDialog — styled modal replacement for window.confirm()
// Rendered by the ToastProvider; do not mount directly.
// Use the showConfirm() function from useConfirm() hook instead.
import React, { useEffect, useRef } from 'react';
import { useToastContext } from '../contexts/ToastContext';
import '../styles/toast.css';

// ─── Icons ───────────────────────────────────────────────────────────────────

const TrashIcon: React.FC = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    width={20}
    height={20}
    aria-hidden="true"
  >
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
    <path d="M10 11v6M14 11v6" />
    <path d="M9 6V4h6v2" />
  </svg>
);

const QuestionIcon: React.FC = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    width={20}
    height={20}
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="10" />
    <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
    <circle cx="12" cy="17" r=".5" fill="currentColor" />
  </svg>
);

// ─── ConfirmDialog ────────────────────────────────────────────────────────────

export const ConfirmDialog: React.FC = () => {
  const { confirmState, resolveConfirm } = useToastContext();
  const cancelBtnRef = useRef<HTMLButtonElement>(null);

  // Focus the cancel button when the dialog opens (safer default for destructive actions)
  useEffect(() => {
    if (confirmState) {
      // Small delay so the animation has started before we steal focus
      const t = setTimeout(() => cancelBtnRef.current?.focus(), 30);
      return () => clearTimeout(t);
    }
  }, [confirmState]);

  // Close on Escape
  useEffect(() => {
    if (!confirmState) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') resolveConfirm(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [confirmState, resolveConfirm]);

  if (!confirmState) return null;

  const {
    title,
    message,
    confirmLabel,
    cancelLabel = 'Abbrechen',
    variant = 'default',
  } = confirmState;

  const isDanger = variant === 'danger';
  const resolvedConfirmLabel = confirmLabel ?? (isDanger ? 'Loschen' : 'Bestatigen');
  const Icon = isDanger ? TrashIcon : QuestionIcon;

  return (
    <div
      className="confirm-dialog-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-message"
      onClick={e => {
        // Close on backdrop click
        if (e.target === e.currentTarget) resolveConfirm(false);
      }}
    >
      <div className="confirm-dialog">
        {/* Header */}
        <div className="confirm-dialog-header">
          <span className={`confirm-dialog-icon confirm-dialog-icon--${variant}`}>
            <Icon />
          </span>
          <h2 id="confirm-dialog-title" className="confirm-dialog-title">
            {title}
          </h2>
        </div>

        {/* Message */}
        <p id="confirm-dialog-message" className="confirm-dialog-message">
          {message}
        </p>

        {/* Actions */}
        <div className="confirm-dialog-actions">
          <button
            ref={cancelBtnRef}
            type="button"
            className="confirm-dialog-cancel"
            onClick={() => resolveConfirm(false)}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`confirm-dialog-confirm confirm-dialog-confirm--${variant}`}
            onClick={() => resolveConfirm(true)}
            autoFocus={!isDanger}
          >
            {resolvedConfirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
