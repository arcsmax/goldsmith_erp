import { useEffect, useState } from 'react';

/** Search inputs wait this long after the last keystroke before querying. */
export const SEARCH_DEBOUNCE_MS = 300;

/** `value`, but only after it stopped changing for `delayMs`. */
export function useDebouncedValue<T>(value: T, delayMs: number = SEARCH_DEBOUNCE_MS): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
