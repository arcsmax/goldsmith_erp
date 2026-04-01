// Toast notification component
// Renders the stacked toast list in the bottom-right corner.
// Import and place <ToastContainer /> once at the app root level.
import React from 'react';
import { useToastContext, Toast, ToastType } from '../contexts/ToastContext';
import '../styles/toast.css';

// ─── Icon helpers ─────────────────────────────────────────────────────────────

const CheckIcon: React.FC = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
    <path
      fillRule="evenodd"
      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
      clipRule="evenodd"
    />
  </svg>
);

const ErrorIcon: React.FC = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
    <path
      fillRule="evenodd"
      d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
      clipRule="evenodd"
    />
  </svg>
);

const WarningIcon: React.FC = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
    <path
      fillRule="evenodd"
      d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
      clipRule="evenodd"
    />
  </svg>
);

const InfoIcon: React.FC = () => (
  <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
    <path
      fillRule="evenodd"
      d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
      clipRule="evenodd"
    />
  </svg>
);

const CloseIcon: React.FC = () => (
  <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
    <path d="M1 1l12 12M13 1L1 13" strokeLinecap="round" />
  </svg>
);

const ICONS: Record<ToastType, React.FC> = {
  success: CheckIcon,
  error: ErrorIcon,
  warning: WarningIcon,
  info: InfoIcon,
};

// ─── Single Toast Item ────────────────────────────────────────────────────────

interface ToastItemProps {
  toast: Toast;
  onDismiss: (id: number) => void;
}

const ToastItem: React.FC<ToastItemProps> = ({ toast, onDismiss }) => {
  const Icon = ICONS[toast.type];

  return (
    <div
      role="alert"
      aria-live={toast.type === 'error' ? 'assertive' : 'polite'}
      aria-atomic="true"
      className={`toast toast-${toast.type}${toast.dismissing ? ' toast-dismissing' : ''}`}
    >
      <span className="toast-icon">
        <Icon />
      </span>

      <div className="toast-body">
        <p className="toast-message">{toast.message}</p>
      </div>

      <button
        className="toast-dismiss"
        onClick={() => onDismiss(toast.id)}
        aria-label="Benachrichtigung schliessen"
        type="button"
      >
        <CloseIcon />
      </button>

      {toast.duration > 0 && (
        <span
          className="toast-progress"
          style={{ animationDuration: `${toast.duration}ms` }}
        />
      )}
    </div>
  );
};

// ─── Toast Container ──────────────────────────────────────────────────────────

export const ToastContainer: React.FC = () => {
  const { toasts, dismissToast } = useToastContext();

  if (toasts.length === 0) return null;

  return (
    <div
      className="toast-container"
      role="region"
      aria-label="Benachrichtigungen"
      aria-live="polite"
    >
      {toasts.map(toast => (
        <ToastItem key={toast.id} toast={toast} onDismiss={dismissToast} />
      ))}
    </div>
  );
};
