// Per-device identity and bench location for scan tracking (2026-09 audit).
//
// Every scan log row says which tablet scanned and where it stands:
//   * device id: a random UUID created once per browser profile and kept in
//     localStorage. It identifies the bench tablet, not the person (the
//     person comes from the JWT on the server).
//   * device location: the bench / station this tablet stands at
//     ("Werkbank 2"), chosen once per device on the scanner page. Unlike
//     ScannerContext.currentLocation (12h TTL, a station scan) it does not
//     expire.
//
// Storage can throw (private mode, quota): every access is guarded and falls
// back to an in-memory value, so scanning never breaks on storage errors.

const DEVICE_ID_KEY = 'scan_device_id';
const DEVICE_LOCATION_KEY = 'scan_device_location';
export const MAX_LOCATION_LENGTH = 100;

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

let memoryDeviceId: string | null = null;

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Private browsing / quota: keep working with the in-memory value.
  }
}

/** This device's scan id; created on first use. */
export function getDeviceId(): string {
  const stored = readStorage(DEVICE_ID_KEY);
  if (stored !== null && UUID_RE.test(stored)) return stored;
  if (memoryDeviceId !== null) return memoryDeviceId;
  const created = crypto.randomUUID();
  memoryDeviceId = created;
  writeStorage(DEVICE_ID_KEY, created);
  return created;
}

/** Normalise a typed location label; empty means "no location". */
export function normaliseLocation(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  const trimmed = value.trim().slice(0, MAX_LOCATION_LENGTH);
  return trimmed.length > 0 ? trimmed : null;
}

/** The bench location chosen for this device, or null. */
export function getDeviceLocation(): string | null {
  return normaliseLocation(readStorage(DEVICE_LOCATION_KEY));
}

/** Remember (or with null / empty: forget) this device's bench location. */
export function setDeviceLocation(value: string | null): string | null {
  const next = normaliseLocation(value);
  writeStorage(DEVICE_LOCATION_KEY, next);
  return next;
}

/** Test helper: forget the in-memory fallback id. */
export function __resetDeviceIdForTests(): void {
  memoryDeviceId = null;
}
