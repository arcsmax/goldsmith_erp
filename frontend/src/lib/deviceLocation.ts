/**
 * Device-remembered Standort for the timer start form (W8/timer-locations).
 *
 * The workbench stays put, the person moves between shifts: preselecting
 * the last-used Standort id for this device means the goldsmith usually
 * just confirms it instead of repicking it on every timer start. Like
 * `benchMode.ts`, this is a device setting (per browser, via localStorage),
 * not a user setting -- it deliberately survives logout.
 */
const DEVICE_LOCATION_STORAGE_KEY = 'device_location_id';

/** The remembered Standort id for this device, or `null` if none / unreadable. */
export function getDeviceLocationId(): number | null {
  try {
    const raw = localStorage.getItem(DEVICE_LOCATION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = Number(raw);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  } catch (err) {
    console.warn('Standort (Gerät): localStorage nicht lesbar', err);
    return null;
  }
}

/** Remembers (or, with `null`, forgets) the Standort id for this device. */
export function setDeviceLocationId(locationId: number | null): void {
  try {
    if (locationId === null) {
      localStorage.removeItem(DEVICE_LOCATION_STORAGE_KEY);
    } else {
      localStorage.setItem(DEVICE_LOCATION_STORAGE_KEY, String(locationId));
    }
  } catch (err) {
    // Private mode / quota: the form still works, it just won't remember.
    console.warn('Standort (Gerät): localStorage nicht schreibbar', err);
  }
}
