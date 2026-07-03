// CostAlertBanner — §649 cost-alert banner for the order-detail header
// (V1.2 Task 4).
//
// Fetches the projected net cost for an order and, when the projected total
// exceeds the baseline threshold, shows an amber/red alert with the delta and
// a CTA into the §649 cost-change flow. `getProjectedCost` is
// COST_CHANGE_VIEW (ADMIN + GOLDSMITH only) — a VIEWER 403s, so the fetch
// itself is gated on the role, not just the rendered UI (mirrors
// KundeninfoTab's canManage gate). A failed fetch must never crash the
// order-detail page — it is swallowed + logged and the banner renders
// nothing, mirroring NoGoWarning's swallow+log pattern (see
// src/components/consultation/NoGoWarning.tsx).
import React, { useEffect, useState } from 'react';
import { useAuth } from '../../contexts';
import { customerUpdatesApi, ProjectedCost } from '../../api/customer-updates';
import { logError } from '../../lib/logError';
import { formatCurrency, formatPercentage } from '../../utils/formatters';
import './cost-alert-banner.css';

export interface CostAlertBannerProps {
  orderId: number;
  onCreateCostChange: () => void;
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

export function CostAlertBanner({ orderId, onCreateCostChange }: CostAlertBannerProps) {
  const { hasRole } = useAuth();
  const canView = hasRole(['ADMIN', 'GOLDSMITH']);

  const [projected, setProjected] = useState<ProjectedCost | null>(null);

  // Skip the GET entirely for a user without COST_CHANGE_VIEW — the backend
  // 403s that role, and we must never even attempt it. Guards against
  // out-of-order responses + setState-after-unmount with a `cancelled` flag,
  // mirroring NoGoWarning.
  useEffect(() => {
    if (!canView) {
      setProjected(null);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const data = await customerUpdatesApi.getProjectedCost(orderId);
        if (!cancelled) setProjected(data);
      } catch (err) {
        logError('CostAlertBanner.load', err);
        if (!cancelled) setProjected(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [orderId, canView]);

  if (!projected || !projected.over_threshold) return null;

  const deltaAbs = projected.delta_abs ?? 0;
  const deltaPercent = projected.delta_percent ?? 0;

  return (
    <div className="cost-alert-banner" role="alert">
      <div className="cost-alert-banner-body">
        <p className="cost-alert-banner-headline">
          §649 Hinweis: Kalkulierte Kosten überschreiten die Freigabegrenze
        </p>
        <p className="cost-alert-banner-detail">
          Projizierter Gesamtpreis (netto): {formatCurrency(projected.projected_total)} — das
          sind {formatCurrency(deltaAbs)} (netto) bzw. {formatPercentage(deltaPercent)} mehr{' '}
          {baselineLabel(projected.baseline_source)}.
        </p>
      </div>
      {canView && (
        <button
          type="button"
          className="cost-alert-banner-cta"
          onClick={onCreateCostChange}
        >
          §649 Kostenänderung anlegen
        </button>
      )}
    </div>
  );
}

export default CostAlertBanner;
