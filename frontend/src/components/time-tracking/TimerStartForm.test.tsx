// TimerStartForm (W8/timer-locations): the Standort dropdown preselects the
// device's remembered location_id (lib/deviceLocation.ts) and sends it on
// start; a successful start remembers the chosen Standort for next time.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockStart = vi.fn();
const mockGetOrders = vi.fn();
const mockGetActivities = vi.fn();
const mockGetActiveLocations = vi.fn();

vi.mock('../../api/time-tracking', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/time-tracking')>();
  return {
    ...actual,
    timeTrackingApi: { ...actual.timeTrackingApi, start: (...args: unknown[]) => mockStart(...args) },
  };
});

vi.mock('../../api/orders', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/orders')>();
  return { ...actual, ordersApi: { ...actual.ordersApi, getAll: (...args: unknown[]) => mockGetOrders(...args) } };
});

vi.mock('../../api/activities', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/activities')>();
  return {
    ...actual,
    activitiesApi: { ...actual.activitiesApi, getAll: (...args: unknown[]) => mockGetActivities(...args) },
  };
});

vi.mock('../../api/locations', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/locations')>();
  return { ...actual, getActiveLocations: (...args: unknown[]) => mockGetActiveLocations(...args) };
});

import { renderWithQuery } from '../../test/queryWrapper';
import { getDeviceLocationId } from '../../lib/deviceLocation';
import { TimerStartForm } from './TimerStartForm';

const locations = [
  { id: 1, name: 'Werkbank 1', kind: 'bench' as const, is_active: true, sort_order: 10, created_at: '2026-09-25T10:00:00Z' },
  { id: 2, name: 'Tresor', kind: 'other' as const, is_active: true, sort_order: 20, created_at: '2026-09-25T10:00:00Z' },
];

const DEVICE_LOCATION_KEY = 'device_location_id';

beforeEach(() => {
  mockStart.mockReset();
  mockGetOrders.mockReset().mockResolvedValue([{ id: 42, title: 'Ring weiten' }]);
  mockGetActivities.mockReset().mockResolvedValue([{ id: 1, name: 'Polieren', usage_count: 0, is_billable: true }]);
  mockGetActiveLocations.mockReset().mockResolvedValue(locations);
  localStorage.clear();
});

afterEach(() => vi.clearAllMocks());

describe('TimerStartForm', () => {
  it('preselects the device-remembered Standort', async () => {
    localStorage.setItem(DEVICE_LOCATION_KEY, '2');
    renderWithQuery(<TimerStartForm onClose={vi.fn()} onStarted={vi.fn()} />, { route: null });

    await screen.findByRole('option', { name: 'Tresor' });
    const select = screen.getByLabelText('Standort') as HTMLSelectElement;
    expect(select.value).toBe('2');
  });

  it('sends the chosen location_id and remembers it for next time', async () => {
    const user = userEvent.setup();
    mockStart.mockResolvedValue({ id: 'entry-1' });
    const onStarted = vi.fn();
    renderWithQuery(<TimerStartForm onClose={vi.fn()} onStarted={onStarted} />, { route: null });

    await screen.findByRole('option', { name: '#42 – Ring weiten' });
    await screen.findByRole('option', { name: 'Polieren' });
    await screen.findByRole('option', { name: 'Werkbank 1' });

    await user.selectOptions(screen.getByLabelText('Auftrag'), '42');
    await user.selectOptions(screen.getByLabelText('Aktivität'), '1');
    await user.selectOptions(screen.getByLabelText('Standort'), '1');
    await user.click(screen.getByRole('button', { name: 'Timer starten' }));

    await waitFor(() => expect(mockStart).toHaveBeenCalledTimes(1));
    expect(mockStart).toHaveBeenCalledWith({ order_id: 42, activity_id: 1, location_id: 1 });
    await waitFor(() => expect(onStarted).toHaveBeenCalled());
    expect(getDeviceLocationId()).toBe(1);
  });

  it('starts without a Standort when none is picked, forgetting any previous one', async () => {
    localStorage.setItem(DEVICE_LOCATION_KEY, '2');
    const user = userEvent.setup();
    mockStart.mockResolvedValue({ id: 'entry-1' });
    renderWithQuery(<TimerStartForm onClose={vi.fn()} onStarted={vi.fn()} />, { route: null });

    await screen.findByRole('option', { name: '#42 – Ring weiten' });
    await screen.findByRole('option', { name: 'Polieren' });
    await screen.findByRole('option', { name: 'Kein Standort' });

    await user.selectOptions(screen.getByLabelText('Auftrag'), '42');
    await user.selectOptions(screen.getByLabelText('Aktivität'), '1');
    await user.selectOptions(screen.getByLabelText('Standort'), '');
    await user.click(screen.getByRole('button', { name: 'Timer starten' }));

    await waitFor(() => expect(mockStart).toHaveBeenCalledTimes(1));
    expect(mockStart).toHaveBeenCalledWith({ order_id: 42, activity_id: 1, location_id: undefined });
    expect(getDeviceLocationId()).toBeNull();
  });
});
