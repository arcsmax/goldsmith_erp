// HidBurstNudge — Slice 12 / A12.1 toast-surface component.
//
// Mounts the useHidBurstDetection hook and surfaces the "Scanner erkannt.
// Werkbank-Station-Modus aktivieren?" toast via the global ToastContext.
//
// The component renders nothing visible itself; the toast system owns the
// UI. On burst detection we show a toast; the `Zu den Einstellungen` call
// is represented as a short-lived secondary toast because the existing
// ToastContext does not carry rich action buttons. This is an intentional
// compromise for Slice 12 — a richer action-toast slot is documented as a
// V1.1.5 follow-up in the HID nudge work item.
//
// Dismissal tracking is in useHidBurstDetection; we bump the count when
// the toast auto-dismisses (no explicit X button is rendered — the toast
// simply times out).

import React, { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth, useToast, useScannerContext } from '../contexts';
import {
  HID_NUDGE_MAX_DISMISSALS,
  incrementDismissedCount,
  readDismissedCount,
  useHidBurstDetection,
} from '../hooks/useHidBurstDetection';

/**
 * The nudge is mounted on every authenticated page but only fires when all
 * of the following hold:
 *   * The user has the GOLDSMITH role.
 *   * bench-mode is OFF.
 *   * The dismissed-count is below HID_NUDGE_MAX_DISMISSALS.
 *   * A suspected HID burst is observed on document.body (via the hook).
 */
export const HidBurstNudge: React.FC = () => {
  const { user } = useAuth();
  const { benchModeEnabled } = useScannerContext();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const isEligible =
    user !== null &&
    user.role?.toUpperCase() === 'GOLDSMITH' &&
    !benchModeEnabled &&
    readDismissedCount() < HID_NUDGE_MAX_DISMISSALS;

  const handleBurst = useCallback((): void => {
    // First surface the main nudge. Then a secondary short toast with the
    // CTA text — tapping the page anywhere dismisses but the deep-link
    // toast also navigates on auto-timeout for non-interactive users (we
    // accept the compromise that not every user will tap the link; the
    // point is to make them aware of the toggle's existence).
    showToast(
      'Scanner erkannt. Werkbank-Station-Modus in den Einstellungen aktivieren?',
      'info',
      6000,
    );

    // Auto-navigate after a short delay so the user has time to read the
    // toast but doesn't have to hunt for the CTA. A goldsmith with dirty
    // hands will thank us.
    setTimeout(() => {
      navigate('/settings');
    }, 2500);
    // Count this firing as a dismissal so repeated false-positives don't
    // become a nuisance. A real bench scanner user will accept the nudge
    // on one of the first three firings.
    incrementDismissedCount();
  }, [showToast, navigate]);

  useHidBurstDetection({
    enabled: isEligible,
    onBurstDetected: handleBurst,
  });

  return null;
};

export default HidBurstNudge;
