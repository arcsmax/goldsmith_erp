// Scan tracking (2026-09 audit, SC-01): every decode is logged BEFORE the
// action sheet opens, every picked action writes a second row with its
// result, unknown codes are logged as "unrecognised", and the device's
// bench location travels with every row.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@yudiel/react-qr-scanner', () => ({
  Scanner: () => <div data-testid="mock-yudiel-scanner" />,
}));

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('../api/client', () => ({
  default: { get: mocks.apiGet, post: mocks.apiPost, patch: vi.fn() },
}));

vi.mock('react-router-dom', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock('../contexts/TimeTrackingContext', () => ({
  useTimeTracking: () => ({
    runningEntry: null,
    activities: [],
    isLoading: false,
    error: null,
    refreshRunningEntry: vi.fn(async () => {}),
  }),
}));

import { ScannerPage } from '../pages/ScannerPage';
import { ScanOverlay } from '../components/scanner/ScanOverlay';
import { ScannerProvider } from '../contexts/ScannerContext';
import { MemoryRouter } from 'react-router-dom';
import { QueryWrapper, createTestQueryClient } from './queryWrapper';
import { classifyPayload, KNOWN_SCAN_PREFIXES } from '../lib/scanPayload';
import {
  __resetDeviceIdForTests,
  getDeviceId,
  getDeviceLocation,
  setDeviceLocation,
} from '../lib/deviceId';
import {
  buildScanEvent,
  flushScanQueue,
  pendingScanCount,
  recordAction,
  recordScan,
} from '../components/scanner/scanTracking';
import type { ResolveResponse, ScanContext } from '../types/scanner';

const UUID_RE = /^[0-9a-f-]{36}$/;

function orderResolve(id = 42): ResolveResponse {
  return {
    resolved: true,
    resolution_path: 'prefix',
    entity_type: 'order',
    entity_id: id,
    entity: { entity_type: 'order', entity_id: id, data: { id, title: 'Trauring', status: 'in_progress' } },
    actions: [
      { id: 'start_timer', label: 'Timer starten', icon: 'play', primary: true },
      { id: 'take_photo', label: 'Foto', icon: 'camera', primary: false },
      { id: 'change_status', label: 'Status weiter', icon: 'clipboard', primary: false },
      { id: 'handover', label: 'Übergabe', icon: 'handoff', primary: false },
      { id: 'change_location', label: 'Standort setzen', icon: 'pin', primary: false },
      { id: 'open_entity', label: 'Öffnen', icon: 'link', primary: false },
      { id: 'add_note', label: 'Notiz', icon: 'note', primary: false },
      { id: 'log_only', label: 'Nur erfassen', icon: 'check', primary: false },
    ],
    status_hint: null,
  };
}

const UNKNOWN: ResolveResponse = {
  resolved: false,
  resolution_path: 'unknown',
  entity_type: null,
  entity_id: null,
  entity: null,
  actions: [],
  status_hint: null,
};

const LOCATIONS = [
  { id: 1, name: 'Werkbank 3', kind: 'bench', is_active: true, sort_order: 0, created_at: '2026-09-01T00:00:00Z' },
  { id: 2, name: 'Tresor', kind: 'safe', is_active: true, sort_order: 1, created_at: '2026-09-01T00:00:00Z' },
];

let resolveResult: ResolveResponse | Error = orderResolve();
let locationError: Error | null = null;
let rowCounter = 0;

type Posted = { url: string; body: Record<string, unknown> };

function posts(url: string): Posted[] {
  return mocks.apiPost.mock.calls
    .filter((call: unknown[]) => call[0] === url)
    .map((call: unknown[]) => ({ url: String(call[0]), body: call[1] as Record<string, unknown> }));
}

function logRows(): Record<string, unknown>[] {
  return posts('/scan/log').map((p) => p.body);
}

beforeEach(() => {
  localStorage.clear();
  __resetDeviceIdForTests();
  resolveResult = orderResolve();
  locationError = null;
  rowCounter = 0;
  mocks.apiGet.mockReset().mockImplementation(async (url: string) =>
    url === '/locations' ? { data: LOCATIONS } : { data: [] },
  );
  mocks.apiPost.mockReset().mockImplementation(async (url: string, body: Record<string, unknown>) => {
    if (url === '/scan/resolve') {
      if (resolveResult instanceof Error) throw resolveResult;
      return { data: resolveResult };
    }
    if (url === '/scan/log') {
      rowCounter += 1;
      return { data: { id: `00000000-0000-4000-8000-00000000000${rowCounter}`, ...body } };
    }
    if (url === '/scan/log/batch') return { data: { ingested: 1 } };
    if (url === '/orders/42/location') {
      if (locationError) throw locationError;
      return { data: {} };
    }
    return { data: {} };
  });
  mocks.navigate.mockReset();
});

afterEach(() => {
  localStorage.clear();
});

function renderScanner(): void {
  render(
    <QueryWrapper client={createTestQueryClient()}>
      <MemoryRouter>
        <ScannerProvider>
          <ScannerPage />
          <ScanOverlay />
        </ScannerProvider>
      </MemoryRouter>
    </QueryWrapper>,
  );
}

async function typeCode(code: string): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByTestId('scanner-manual-input'), code);
  await user.click(screen.getByTestId('scanner-manual-submit'));
}

describe('scan tracking: decode → log → sheet', () => {
  it('logs a scan_only row with device + location, then opens the action sheet', async () => {
    setDeviceLocation('Werkbank 2');
    renderScanner();
    await typeCode('order:42');

    await screen.findByTestId('qa-modal-v2');
    expect(posts('/scan/resolve')[0].body.raw_payload).toBe('ORDER:42');
    const [row] = logRows();
    expect(row.action_taken).toBe('scan_only');
    expect(row.resolved_type).toBe('order');
    expect(row.resolved_id).toBe('42');
    const ctx = row.context as ScanContext;
    expect(ctx.device_id).toMatch(UUID_RE);
    expect(ctx.current_location).toBe('Werkbank 2');
    expect(ctx.input_source).toBe('manual');
    // The log call happened before the sheet: exactly one row so far.
    expect(logRows()).toHaveLength(1);
    // Only executable actions are offered; "add_note" had no handler.
    expect(screen.getByTestId('qa-action-log_only')).toBeInTheDocument();
    expect(screen.queryByTestId('qa-action-add_note')).toBeNull();
  });

  it('"Nur erfassen" closes without a second row', async () => {
    renderScanner();
    await typeCode('42');
    const user = userEvent.setup();
    await user.click(await screen.findByTestId('qa-action-log_only'));
    await waitFor(() => expect(screen.queryByTestId('qa-modal-v2')).toBeNull());
    expect(logRows().map((r) => r.action_taken)).toEqual(['scan_only']);
  });

  it('an action writes a second row linked to the scan, with its result', async () => {
    renderScanner();
    await typeCode('42');
    const user = userEvent.setup();
    await user.click(await screen.findByTestId('qa-action-take_photo'));
    await waitFor(() => expect(logRows()).toHaveLength(2));
    const [scan, action] = logRows();
    expect(action.action_taken).toBe('take_photo');
    const ctx = action.context as ScanContext;
    expect(ctx.parent_scan_id).toBe('00000000-0000-4000-8000-000000000001');
    expect(ctx.action_result).toBe('ok');
    expect(action.idempotency_key).not.toBe(scan.idempotency_key);
    expect(mocks.navigate).toHaveBeenCalledWith('/orders/42?tab=fotos&capture=1');
  });

  it('"Übergabe" and "Status weiter" navigate and are logged', async () => {
    renderScanner();
    await typeCode('42');
    const user = userEvent.setup();
    await user.click(await screen.findByTestId('qa-action-handover'));
    await waitFor(() => expect(logRows()).toHaveLength(2));
    expect(mocks.navigate).toHaveBeenCalledWith('/orders/42?tab=handoff');
    expect(logRows()[1].action_taken).toBe('handover');
  });

  it('"Standort setzen" stores the location on the order and logs it', async () => {
    renderScanner();
    await typeCode('42');
    const user = userEvent.setup();
    await user.click(await screen.findByTestId('qa-action-change_location'));
    const dialog = await screen.findByRole('dialog', { name: 'Standort setzen' });
    const select = within(dialog).getByLabelText(/Standort/);
    await within(dialog).findByRole('option', { name: 'Tresor' });
    await user.selectOptions(select, '2');
    await user.click(within(dialog).getByRole('button', { name: 'Standort setzen' }));

    await waitFor(() => expect(logRows()).toHaveLength(2));
    expect(posts('/orders/42/location')[0].body).toEqual({ location: 'Tresor', location_id: 2 });
    const action = logRows()[1];
    expect(action.action_taken).toBe('change_location');
    expect((action.context as ScanContext).current_location).toBe('Tresor');
    expect((action.context as ScanContext).location_id).toBe(2);
    expect((action.context as ScanContext).action_result).toBe('ok');
  });

  it('a failed action is logged as failed and the error stays on the sheet', async () => {
    locationError = new Error('Standort konnte nicht gespeichert werden.');
    renderScanner();
    await typeCode('42');
    const user = userEvent.setup();
    await user.click(await screen.findByTestId('qa-action-change_location'));
    const dialog = await screen.findByRole('dialog', { name: 'Standort setzen' });
    await within(dialog).findByRole('option', { name: 'Tresor' });
    await user.selectOptions(within(dialog).getByLabelText(/Standort/), '2');
    await user.click(within(dialog).getByRole('button', { name: 'Standort setzen' }));

    expect(await screen.findByTestId('qa-error')).toHaveTextContent('nicht gespeichert');
    await waitFor(() => expect(logRows()).toHaveLength(2));
    expect((logRows()[1].context as ScanContext).action_result).toBe('failed');
  });

  it('an unknown code is logged as unrecognised and explained in German', async () => {
    resolveResult = UNKNOWN;
    renderScanner();
    await typeCode('ALT-0815');
    expect(await screen.findByTestId('qa-unrecognised')).toHaveTextContent('nicht erkannt');
    const [row] = logRows();
    expect(row.action_taken).toBe('unrecognised');
    expect(row.resolution_path).toBe('unknown');
    expect(row.raw_payload).toBe('ALT-0815');
  });

  it('a failed resolve is still logged (resolve_failed)', async () => {
    resolveResult = new Error('Netzwerkfehler');
    renderScanner();
    await typeCode('42');
    expect(await screen.findByTestId('scanner-error')).toBeInTheDocument();
    await waitFor(() => expect(logRows()).toHaveLength(1));
    expect(logRows()[0].action_taken).toBe('resolve_failed');
  });
});

describe('device location on the scanner page', () => {
  it('is chosen once and persisted per device', async () => {
    renderScanner();
    const user = userEvent.setup();
    expect(screen.getByTestId('scanner-device-location-value')).toHaveTextContent('nicht festgelegt');
    await user.click(screen.getByTestId('scanner-device-location-edit'));
    const dialog = await screen.findByRole('dialog', { name: 'Standort dieses Geräts' });
    await within(dialog).findByRole('option', { name: 'Werkbank 3' });
    await user.selectOptions(within(dialog).getByLabelText(/Standort/), '1');
    await user.click(within(dialog).getByRole('button', { name: 'Standort speichern' }));

    expect(screen.getByTestId('scanner-device-location-value')).toHaveTextContent('Werkbank 3');
    expect(getDeviceLocation()).toBe('Werkbank 3');
    expect(JSON.parse(localStorage.getItem('scan_device_location') ?? 'null')).toEqual({
      id: 1,
      name: 'Werkbank 3',
    });
  });

  it('sends the device location id with every scan', async () => {
    setDeviceLocation({ id: 1, name: 'Werkbank 3' });
    renderScanner();
    await typeCode('42');
    await screen.findByTestId('qa-modal-v2');
    const ctx = logRows()[0].context as ScanContext;
    expect(ctx.location_id).toBe(1);
    expect(ctx.current_location).toBe('Werkbank 3');
  });
});

describe('scanTracking units', () => {
  const ctx: ScanContext = {
    running_timer_id: null,
    current_order_id: null,
    current_location: null,
    device_type: 'tablet',
    input_source: 'camera',
  };

  it('builds scan_only / unrecognised / resolve_failed first rows', () => {
    expect(buildScanEvent('ORDER:42', orderResolve(), ctx).action_taken).toBe('scan_only');
    expect(buildScanEvent('X', UNKNOWN, ctx).action_taken).toBe('unrecognised');
    const failed = buildScanEvent('42', null, ctx);
    expect(failed.action_taken).toBe('resolve_failed');
    expect(failed.resolved_type).toBeUndefined();
  });

  it('queues a row that could not be sent and flushes it as a batch', async () => {
    mocks.apiPost.mockRejectedValueOnce(new Error('offline'));
    const tracked = await recordScan('ORDER:42', orderResolve(), ctx);
    expect(tracked.scanId).toBeNull();
    expect(pendingScanCount()).toBe(1);

    await flushScanQueue();
    const [batch] = posts('/scan/log/batch');
    const events = (batch.body as { events: Record<string, unknown>[] }).events;
    expect(events[0].offline_queued).toBe(true);
    expect(pendingScanCount()).toBe(0);
  });

  it('an action after an offline scan is still logged, without a parent id', async () => {
    mocks.apiPost.mockRejectedValueOnce(new Error('offline'));
    const tracked = await recordScan('ORDER:42', orderResolve(), ctx);
    await recordAction(tracked, 'start_timer', 'ok');
    const rows = logRows();
    const row = rows[rows.length - 1];
    expect(row.action_taken).toBe('start_timer');
    expect((row.context as ScanContext).parent_scan_id).toBeUndefined();
  });

  it('keeps one device id per device', () => {
    const first = getDeviceId();
    __resetDeviceIdForTests();
    expect(getDeviceId()).toBe(first);
    expect(first).toMatch(UUID_RE);
  });
});

describe('scan payload grammar (SC-06/SC-07)', () => {
  it('recognises label codes case-insensitively and bare order numbers', () => {
    expect(classifyPayload('ORDER:42')).toEqual({ kind: 'prefix', canonical: 'ORDER:42' });
    expect(classifyPayload(' repair : 17 ')).toEqual({ kind: 'prefix', canonical: 'REPAIR:17' });
    expect(classifyPayload('42')).toEqual({ kind: 'numeric', canonical: 'ORDER:42' });
  });

  it('never guesses unknown prefixes or free text', () => {
    expect(classifyPayload('FOO:42').kind).toBe('unrecognised');
    expect(classifyPayload('ALT-0815').kind).toBe('unrecognised');
  });

  it('lists the backend prefix set', () => {
    expect([...KNOWN_SCAN_PREFIXES].sort()).toEqual(
      ['ACTIVITY', 'INTERRUPT', 'MATERIAL', 'METAL', 'ORDER', 'REPAIR'],
    );
  });
});
