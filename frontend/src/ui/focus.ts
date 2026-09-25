// Focus helpers shared by Modal and Tabs.

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function getFocusable(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => !el.hasAttribute('inert') && el.getAttribute('aria-hidden') !== 'true',
  );
}

/**
 * Keep Tab / Shift+Tab inside `container`. Returns true when it moved focus
 * (the caller then prevents the default).
 */
export function trapTab(event: KeyboardEvent, container: HTMLElement): boolean {
  const focusable = getFocusable(container);
  if (focusable.length === 0) {
    container.focus();
    return true;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const active = document.activeElement as HTMLElement | null;
  const isInside = active !== null && container.contains(active);

  if (event.shiftKey && (!isInside || active === first || active === container)) {
    last.focus();
    return true;
  }
  if (!event.shiftKey && (!isInside || active === last)) {
    first.focus();
    return true;
  }
  return false;
}
