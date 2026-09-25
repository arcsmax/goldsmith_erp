// Scan-Verlauf of one piece (order or repair): who scanned it, when, where
// and what they did — newest first (scan tracking, 2026-09 audit, SC-02).
//
// Data: pieceScansQuery (GET /orders/{id}/scans | /repairs/{id}/scans),
// refreshed live by the `scan_updates` hint (lib/realtimeInvalidation.ts).
// VIEWER may read it: rows carry no prices or customer data.
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { pieceScansQuery, type PieceScan, type ScanPieceType } from '../../api/scanner';
import { getErrorMessage } from '../../lib/errors';
import { Button, EmptyState, PageState, type PageStateValue } from '../../ui';
import '../../styles/components/ScanTracking.css';
import { describeActionId, formatScanTime } from './scanHistory';

const PAGE_SIZE = 20;
/** Backend cap on `limit` (scan_history_service.MAX_HISTORY_LIMIT). */
const MAX_LIMIT = 100;

const SOURCE_LABELS: Readonly<Record<string, string>> = {
  camera: 'Kamera',
  usb_hid: 'Handscanner',
  manual: 'eingetippt',
};

export interface PieceScanHistoryProps {
  entityType: ScanPieceType;
  entityId: number;
}

const ScanRow: React.FC<{ scan: PieceScan }> = ({ scan }) => {
  const source = scan.input_source ? SOURCE_LABELS[scan.input_source] : undefined;
  return (
    <li className="piece-scan-row" data-testid={`piece-scan-${scan.id}`}>
      <span className="piece-scan-row__action">
        {describeActionId(scan.action_taken, scan.action_result)}
      </span>
      <span className="piece-scan-row__meta">
        <time dateTime={scan.scanned_at} className="piece-scan-row__time">
          {formatScanTime(scan.scanned_at)}
        </time>
        {' · '}
        {scan.user_name}
        {' · '}
        {scan.location ?? 'Standort unbekannt'}
        {source !== undefined && ` · ${source}`}
      </span>
    </li>
  );
};

export const PieceScanHistory: React.FC<PieceScanHistoryProps> = ({ entityType, entityId }) => {
  const [limit, setLimit] = useState(PAGE_SIZE);
  const query = useQuery(pieceScansQuery(entityType, entityId, limit));

  if (!query.data) {
    const state: PageStateValue = query.isError
      ? {
          status: 'error',
          error: getErrorMessage(query.error, 'Scan-Verlauf konnte nicht geladen werden.'),
          retry: () => void query.refetch(),
        }
      : { status: 'loading' };
    return <PageState state={state} skeleton="list" skeletonCount={2} />;
  }

  const page = query.data;
  if (page.items.length === 0) {
    return (
      <div data-testid="piece-scan-empty">
        <EmptyState
          icon="scan"
          title="Noch nicht gescannt"
          body="Jeder Scan des QR-Codes auf der Tüte erscheint hier: wer, wann, wo und was."
          headingLevel={3}
        />
      </div>
    );
  }

  return (
    <div data-testid="piece-scan-history">
      <ul className="piece-scan-list">
        {page.items.map((scan) => (
          <ScanRow key={scan.id} scan={scan} />
        ))}
      </ul>
      {page.next_offset !== null && page.next_offset !== undefined && limit < MAX_LIMIT && (
        <Button variant="secondary" onClick={() => setLimit((current) => Math.min(current + PAGE_SIZE, MAX_LIMIT))}>
          Ältere Scans laden
        </Button>
      )}
    </div>
  );
};

export default PieceScanHistory;
