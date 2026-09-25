// Shared "toast, but optional" helper for scanner components.
//
// Some scanner components (ScanOverlay, HidScannerListener) render in
// isolated tests without a ToastProvider ancestor. The context read happens
// on every render either way (hook order stays stable across renders), but
// we catch the "must be used within a ToastProvider" throw so those tests
// don't need to wrap every render with ToastProvider. Extracted from
// ScanOverlay so HidScannerListener (2026-09 audit, SC HID fix) can reuse
// the exact same fallback instead of redefining it.
import { useToast } from '../../contexts/ToastContext';

export type ShowToast = ReturnType<typeof useToast>['showToast'];

export function useOptionalToast(): ShowToast | null {
  try {
    return useToast().showToast;
  } catch {
    return null;
  }
}
