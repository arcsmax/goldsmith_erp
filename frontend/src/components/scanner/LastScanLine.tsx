// "Zuletzt gescannt von … um … in …" on the Übersicht of an order or repair
// (scan tracking, 2026-09 audit). Reads `last_scan` from the detail read;
// the `scan_updates` hint refreshes that read after every scan.
import React from 'react';

import type { LastScan } from '../../api/scanner';
import { Icon } from '../../ui';
import '../../styles/components/ScanTracking.css';
import { describeActionId, formatScanTime } from './scanHistory';

export interface LastScanLineProps {
  lastScan: LastScan | null | undefined;
}

export const LastScanLine: React.FC<LastScanLineProps> = ({ lastScan }) => {
  if (!lastScan) {
    return (
      <p className="last-scan-line" data-testid="last-scan-line">
        <Icon name="scan" />
        <span>Noch nicht gescannt.</span>
      </p>
    );
  }
  const where = lastScan.location ? ` in ${lastScan.location}` : '';
  return (
    <p className="last-scan-line" data-testid="last-scan-line">
      <Icon name="scan" />
      <span>
        Zuletzt gescannt von <strong>{lastScan.user_name}</strong> um{' '}
        <time dateTime={lastScan.scanned_at} className="last-scan-line__time">
          {formatScanTime(lastScan.scanned_at)}
        </time>
        {where}
        {' · '}
        {describeActionId(lastScan.action_taken)}
      </span>
    </p>
  );
};

export default LastScanLine;
