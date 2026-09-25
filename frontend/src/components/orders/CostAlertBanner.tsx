// CostAlertBanner — §649 cost-alert banner for the order-detail header
// (V1.2 Task 4; W4-03 on TanStack Query + src/ui).
//
// Reads the projected net cost for an order and, when the projected total
// exceeds the baseline threshold, shows a waiting-tone alert card with the
// delta and a CTA into the §649 cost-change flow. `getProjectedCost` is
// COST_CHANGE_VIEW (ADMIN + GOLDSMITH only) — a VIEWER 403s, so the query
// itself is disabled for that role, not just the rendered UI. A failed
// fetch must never crash the order-detail page: it is logged and the banner
// renders nothing.
//
// The key sits under queryKeys.orders.detail(orderId), so a cost-change
// mutation (invalidateOrder) or an order_updates hint refreshes it; no
// manual refresh counter is needed.
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../contexts';
import { customerUpdatesApi, ProjectedCost } from '../../api/customer-updates';
import { queryKeys } from '../../api/queryKeys';
import { logError } from '../../lib/logError';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { formatPercentage } from '../../utils/formatters';
import { Button, Card } from '../../ui';
import './cost-alert-banner.css';

export interface CostAlertBannerProps {
  orderId: number;
  onCreateCostChange: () => void;
  /** @deprecated W4-03: the query refreshes via invalidation; ignored. */
  refreshKey?: number;
}

const BASELINE_LABELS: Record<string, string> = {
  quote: 'gegenüber dem Kostenvoranschlag',
  approved_change: 'gegenüber der bereits genehmigten Kostenänderung',
};
const DEFAULT_BASELINE_LABEL = 'gegenüber der Kalkulationsbasis';

function baselineLabel(source: ProjectedCost['baseline_source']): string {
  if (source && BASELINE_LABELS[source]) {
    return BASELINE_LABELS[source];
  }
  return DEFAULT_BASELINE_LABEL;
}

async function fetchProjectedCost(orderId: number): Promise<ProjectedCost> {
  try {
    return await customerUpdatesApi.getProjectedCost(orderId);
  } catch (err) {
    logError('CostAlertBanner.load', err);
    throw err;
  }
}

export function CostAlertBanner({ orderId, onCreateCostChange }: CostAlertBannerProps) {
  const { hasRole } = useAuth();
  const canView = hasRole(['ADMIN', 'GOLDSMITH']);

  const { data: projected } = useQuery({
    queryKey: queryKeys.orders.projectedCost(orderId),
    queryFn: () => fetchProjectedCost(orderId),
    enabled: canView,
  });

  if (!canView || !projected || !projected.over_threshold) return null;

  const deltaAbs = projected.delta_abs ?? 0;
  const deltaPercent = projected.delta_percent ?? 0;

  return (
    <div className="cost-alert-banner" role="alert">
      <Card
        tone="waiting"
        action={
          <Button variant="primary" icon="receipt" onClick={onCreateCostChange}>
            §649 Kostenänderung anlegen
          </Button>
        }
      >
        <p className="cost-alert-banner__headline">
          §649 Hinweis: Kalkulierte Kosten überschreiten die Freigabegrenze
        </p>
        <p className="cost-alert-banner__detail">
          Projizierter Gesamtpreis (netto):{' '}
          <span className={MONEY_CLASS}>{formatEur(projected.projected_total)}</span> — das sind{' '}
          <span className={MONEY_CLASS}>{formatEur(deltaAbs)}</span> (netto) bzw.{' '}
          {formatPercentage(deltaPercent)} mehr {baselineLabel(projected.baseline_source)}.
        </p>
      </Card>
    </div>
  );
}

export default CostAlertBanner;
