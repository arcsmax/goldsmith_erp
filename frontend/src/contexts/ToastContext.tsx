// Toast & ConfirmDialog Context
// Provides showToast() and showConfirm() globally throughout the app.
import React, { createContext, useCallback, useContext, useRef, useState } from 'react';

// ─── Types ────────────────────────────────────────────────────────────────────

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: number;
  message: string;
  type: ToastType;
  /** duration in ms before auto-dismiss; 0 = no auto-dismiss */
  duration: number;
  /** true while the exit animation is playing */
  dismissing: boolean;
}

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'default';
}

interface ConfirmState extends ConfirmOptions {
  resolve: (confirmed: boolean) => void;
}

interface ToastContextValue {
  toasts: Toast[];
  showToast: (message: string, type?: ToastType, duration?: number) => void;
  dismissToast: (id: number) => void;
  showConfirm: (options: ConfirmOptions) => Promise<boolean>;
  confirmState: ConfirmState | null;
  resolveConfirm: (confirmed: boolean) => void;
}

// ─── Context ─────────────────────────────────────────────────────────────────

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

let nextId = 1;

// ─── Provider ────────────────────────────────────────────────────────────────

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);
  // Keep timers so we can clear them on early dismiss
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismissToast = useCallback((id: number) => {
    // Clear auto-dismiss timer if still pending
    const timer = timersRef.current.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }

    // Mark as dismissing to trigger exit animation
    setToasts(prev =>
      prev.map(t => (t.id === id ? { ...t, dismissing: true } : t))
    );

    // Remove from DOM after animation completes
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 260);
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = 'info', duration = 4000) => {
      const id = nextId++;
      const toast: Toast = { id, message, type, duration, dismissing: false };

      setToasts(prev => [...prev, toast]);

      if (duration > 0) {
        const timer = setTimeout(() => {
          dismissToast(id);
        }, duration);
        timersRef.current.set(id, timer);
      }
    },
    [dismissToast]
  );

  const showConfirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise(resolve => {
      setConfirmState({ ...options, resolve });
    });
  }, []);

  const resolveConfirm = useCallback((confirmed: boolean) => {
    if (confirmState) {
      confirmState.resolve(confirmed);
      setConfirmState(null);
    }
  }, [confirmState]);

  return (
    <ToastContext.Provider
      value={{ toasts, showToast, dismissToast, showConfirm, confirmState, resolveConfirm }}
    >
      {children}
    </ToastContext.Provider>
  );
};

// ─── Hooks ───────────────────────────────────────────────────────────────────

export const useToast = (): Pick<ToastContextValue, 'toasts' | 'showToast' | 'dismissToast'> => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return { toasts: ctx.toasts, showToast: ctx.showToast, dismissToast: ctx.dismissToast };
};

export const useConfirm = (): Pick<ToastContextValue, 'showConfirm'> => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useConfirm must be used within ToastProvider');
  return { showConfirm: ctx.showConfirm };
};

/** Internal hook — used only by the ToastContainer and ConfirmDialog renderers */
export const useToastContext = (): ToastContextValue => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToastContext must be used within ToastProvider');
  return ctx;
};
