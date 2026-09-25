// Scan-Verlauf views (2026-09 audit, SC-02/SC-03): the per-piece list, the
// "Zuletzt gescannt" line, the admin search and the realtime hint mapping.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

const mocks = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock('../api/client', () => ({ default: { get: mocks.apiGet, post: vi.fn() } }));

import { PieceScanHistory } from '../components/scanner/PieceScanHistory';
import { LastScanLine } from '../components/scanner/LastScanLine';
import { ScanHistoryPanel } from '../pages/admin/ScanHistoryPanel';
import { scanPieceKeys } from '../lib/realtimeInvalidation';
import { queryKeys } from '../api/queryKeys';
import { QueryWrapper, createTestQueryClient } from './queryWrapper';

const SCAN = {
  id: 'a1',
  scanned_at: '2026-09-25T08:30:00Z',
  user_id: 3,
  user_name: 'Anne Goldschmied',
  location: 'Werkbank 2',
  action_taken: 'start_timer',
  action_result: 'ok',
  input_source: 'camera',
  parent_scan_id: 'a0',
};

function wrap(node: React.ReactNode) {
  return render(
    <QueryWrapper client={createTestQueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryWrapper>,
  );
}

beforeEach(() => {
  mocks.apiGet.mockReset();
});

describe('PieceScanHistory', () => {
  it('lists who, when, where and what for an order', async () => {
    mocks.apiGet.mockResolvedValue({
      data: { items: [SCAN], total: 1, limit: 20, offset: 0, next_offset: null },
    });
    wrap(<PieceScanHistory entityType="order" entityId={42} />);
    const row = await screen.findByTestId('piece-scan-a1');
    expect(row).toHaveTextContent('Timer gestartet');
    expect(row).toHaveTextContent('Anne Goldschmied');
    expect(row).toHaveTextContent('Werkbank 2');
    expect(row).toHaveTextContent('Kamera');
    expect(mocks.apiGet).toHaveBeenCalledWith('/orders/42/scans', { params: { limit: 20, offset: 0 } });
  });

  it('uses the repair endpoint and shows an empty state', async () => {
    mocks.apiGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 20, offset: 0, next_offset: null },
    });
    wrap(<PieceScanHistory entityType="repair" entityId={7} />);
    expect(await screen.findByTestId('piece-scan-empty')).toHaveTextContent('Noch nicht gescannt');
    expect(mocks.apiGet).toHaveBeenCalledWith('/repairs/7/scans', expect.anything());
  });

  it('marks failed actions', async () => {
    mocks.apiGet.mockResolvedValue({
      data: {
        items: [{ ...SCAN, action_taken: 'switch_timer', action_result: 'failed' }],
        total: 1,
        limit: 20,
        offset: 0,
        next_offset: null,
      },
    });
    wrap(<PieceScanHistory entityType="order" entityId={42} />);
    expect(await screen.findByTestId('piece-scan-a1')).toHaveTextContent('Timer gewechselt – fehlgeschlagen');
  });
});

describe('LastScanLine', () => {
  it('says who scanned last, when and where', () => {
    wrap(
      <LastScanLine
        lastScan={{
          scanned_at: '2026-09-25T08:30:00Z',
          user_id: 3,
          user_name: 'Anne Goldschmied',
          location: 'Tresor',
          action_taken: 'scan_only',
        }}
      />,
    );
    const line = screen.getByTestId('last-scan-line');
    expect(line).toHaveTextContent('Zuletzt gescannt von Anne Goldschmied um');
    expect(line).toHaveTextContent('in Tresor');
    expect(line).toHaveTextContent('Nur gescannt');
  });

  it('says when a piece was never scanned', () => {
    wrap(<LastScanLine lastScan={null} />);
    expect(screen.getByTestId('last-scan-line')).toHaveTextContent('Noch nicht gescannt.');
  });
});

describe('ScanHistoryPanel', () => {
  it('searches by code and links rows to the piece', async () => {
    mocks.apiGet.mockResolvedValue({
      data: {
        items: [
          { ...SCAN, raw_payload: 'ORDER:42', resolved_type: 'order', resolved_id: '42', resolution_path: 'prefix', device_id: null },
        ],
        total: 1,
        limit: 25,
        offset: 0,
        next_offset: null,
      },
    });
    wrap(<ScanHistoryPanel />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/Nummer oder Code/), 'ORDER:42');
    await user.click(screen.getByRole('button', { name: 'Scans suchen' }));
    await waitFor(() =>
      expect(mocks.apiGet).toHaveBeenLastCalledWith('/scan/history', {
        params: { q: 'ORDER:42', limit: 25, offset: 0 },
      }),
    );
    const link = await screen.findByRole('link', { name: 'ORDER:42' });
    expect(link).toHaveAttribute('href', '/orders/42');
  });
});

describe('scan_updates realtime hint', () => {
  it('maps to the scanned piece detail only', () => {
    expect(scanPieceKeys({ entity_type: 'order', entity_id: '42' })).toEqual([queryKeys.orders.detail(42)]);
    expect(scanPieceKeys({ entity_type: 'repair', entity_id: '7' })).toEqual([queryKeys.repairs.detail(7)]);
    expect(scanPieceKeys({ entity_type: null, entity_id: null })).toEqual([]);
  });
});
