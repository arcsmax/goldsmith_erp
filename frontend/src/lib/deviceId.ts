// Per-device identity and bench location for scan tracking (2026-09 audit).
//
// Every scan log row says which tablet scanned and where it stands:
//   * device id: a random UUID created once per browser profile and kept in
//     localStorage. It identifies the bench tablet, not the person (the
//     person comes from the JWT on the server).
//   * device location: the bench / station this tablet stands at
//     ("Werkbank 2"), chosen once per device on the scanner page from the
//     configured workshop locations (W8; id + name). Unlike
//     ScannerContext.currentLocation (12h TTL, a station scan) it does not
//     expire. Older entries stored as plain text still read as a name.
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

export interface DeviceLocation {
  /** workshop_locations id; null for a plain-text label. */
  id: number | null;
  name: string;
}

function parseDeviceLocation(raw: string | null): DeviceLocation | null {
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed !== null && typeof parsed === 'object') {
      const { id, name } = parsed as { id?: unknown; name?: unknown };
      const cleanName = normaliseLocation(typeof name === 'string' ? name : null);
      if (cleanName === null) return null;
      const cleanId = typeof id === 'number' && Number.isInteger(id) && id > 0 ? id : null;
      return { id: cleanId, name: cleanName };
    }
  } catch {
    // Plain text from before W8: read it as a name.
  }
  const name = normaliseLocation(raw);
  return name === null ? null : { id: null, name };
}

/** The bench location chosen for this device (id + name), or null. */
export function getDeviceLocationEntry(): DeviceLocation | null {
  return parseDeviceLocation(readStorage(DEVICE_LOCATION_KEY));
}

/** The bench location name chosen for this device, or null. */
export function getDeviceLocation(): string | null {
  return getDeviceLocationEntry()?.name ?? null;
}

/** Remember (or with null / empty name: forget) this device's bench location. */
export function setDeviceLocation(
  value: DeviceLocation | string | null,
): DeviceLocation | null {
  const entry =
    value === null
      ? null
      : typeof value === 'string'
        ? parseDeviceLocation(JSON.stringify({ id: null, name: value }))
        : parseDeviceLocation(JSON.stringify(value));
  writeStorage(DEVICE_LOCATION_KEY, entry === null ? null : JSON.stringify(entry));
  return entry;
}

/** Test helper: forget the in-memory fallback id. */
export function __resetDeviceIdForTests(): void {
  memoryDeviceId = null;
}
