// Soll/Ist Vergleich — Estimated vs. Actual comparison tab for completed orders
import React, { useEffect, useState } from 'react';
import { ordersApi, invoicesApi } from '../../api';
import { useToast } from '../../contexts';
import { OrderComparison, ComparisonMetric, ActivityBreakdownComparison } from '../../types';

interface SollIstTabProps {
  orderId: number;
  orderStatus: string;
}

// Deviation colour thresholds (Jason: green <10%, amber 10-20%, red >20%)
function deviationClass(pct: number | null): string {
  if (pct === null) return 'deviation-neutral';
  const abs = Math.abs(pct);
  if (abs < 10) return 'deviation-green';
  if (abs < 20) return 'deviation-amber';
  return 'deviation-red';
}

function deviationArrow(pct: number | null): string {
  if (pct === null) return '';
  if (pct > 0) return ' ↑';
  if (pct < 0) return ' ↓';
  return '';
}

function formatPct(pct: number | null): string {
  if (pct === null) return '—';
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)} %`;
}

function formatValue(value: number | null, unit: string, decimals = 1): string {
  if (value === null) return '—';
  return `${value.toFixed(decimals)} ${unit}`;
}

// ---- MetricRow ---------------------------------------------------------------

interface MetricRowProps {
  label: string;
  metric: ComparisonMetric;
  unit: string;
  decimals?: number;
}

const MetricRow: React.FC<MetricRowProps> = ({ label, metric, unit, decimals = 1 }) => {
  const cls = deviationClass(metric.deviation_percent);
  const arrow = deviationArrow(metric.deviation_percent);

  return (
    <div className="soll-ist-metric-row">
      <div className="soll-ist-metric-label">{label}</div>
      <div className="soll-ist-metric-values">
        <span className="soll-ist-soll">
          <span className="soll-ist-value-label">Soll</span>
          {formatValue(metric.soll, unit, decimals)}
        </span>
        <span className="soll-ist-arrow-sep">→</span>
        <span className="soll-ist-ist">
          <span className="soll-ist-value-label">Ist</span>
          {formatValue(metric.ist, unit, decimals)}
        </span>
        <span className={`soll-ist-deviation ${cls}`} title="Abweichung">
          {formatPct(metric.deviation_percent)}{arrow}
        </span>
      </div>
    </div>
  );
};

// ---- ActivityTable -----------------------------------------------------------

interface ActivityTableProps {
  rows: ActivityBreakdownComparison[];
}

const ActivityTable: React.FC<ActivityTableProps> = ({ rows }) => {
  if (rows.length === 0) {
    return (
      <p className="empty-message">Keine Aktivitätsdaten vorhanden.</p>
    );
  }

  return (
    <table className="soll-ist-activity-table">
      <thead>
        <tr>
          <th>Aktivität</th>
          <th>Kategorie</th>
          <th className="text-right">Soll (min)</th>
          <th className="text-right">Ist (min)</th>
          <th className="text-right">Abweichung</th>
          <th className="text-right">Einträge</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const cls = deviationClass(row.deviation_percent);
          const arrow = deviationArrow(row.deviation_percent);
          return (
            <tr key={row.activity_id} className={row.is_significant ? 'soll-ist-row-significant' : ''}>
              <td>{row.activity_name}</td>
              <td>
                <span className={`activity-category-badge category-${row.activity_category}`}>
                  {row.activity_category}
                </span>
              </td>
              <td className="text-right">
                {row.estimated_minutes !== null ? row.estimated_minutes.toFixed(0) : '—'}
              </td>
              <td className="text-right">{row.actual_minutes.toFixed(0)}</td>
              <td className={`text-right soll-ist-deviation ${cls}`}>
                {formatPct(row.deviation_percent)}{arrow}
              </td>
              <td className="text-right">{row.entry_count}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
};

// ---- AccuracyBadge -----------------------------------------------------------

const AccuracyBadge: React.FC<{ score: number | null }> = ({ score }) => {
  if (score === null) return null;

  let cls = 'accuracy-badge-green';
  if (score < 80) cls = 'accuracy-badge-amber';
  if (score < 60) cls = 'accuracy-badge-red';

  return (
    <div className="soll-ist-accuracy">
      <span className="soll-ist-accuracy-label">Genauigkeitsscore</span>
      <span className={`accuracy-badge ${cls}`}>{score.toFixed(0)} %</span>
    </div>
  );
};

// ---- Main component ----------------------------------------------------------

const COMPLETED_STATUSES = ['completed', 'delivered'];

export const SollIstTab: React.FC<SollIstTabProps> = ({ orderId, orderStatus }) => {
  const { showToast } = useToast();
  const [data, setData] = useState<OrderComparison | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [existingInvoiceId, setExistingInvoiceId] = useState<number | null | undefined>(undefined);
  const [isCreatingInvoice, setIsCreatingInvoice] = useState(false);

  const isEligible = COMPLETED_STATUSES.includes(orderStatus);

  useEffect(() => {
    if (!isEligible || hasLoaded) return;

    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const [result, invoiceResp] = await Promise.all([
          ordersApi.getComparison(orderId),
          invoicesApi.getInvoices({ limit: 5 }).catch(() => null),
        ]);
        setData(result);
        // Check if any invoice already belongs to this order
        if (invoiceResp) {
          const items = Array.isArray(invoiceResp) ? invoiceResp : (invoiceResp as any).items ?? [];
          const match = items.find((inv: any) => inv.order_id === orderId);
          setExistingInvoiceId(match ? match.id : null);
        } else {
          setExistingInvoiceId(null);
        }
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Fehler beim Laden der Vergleichsdaten');
      } finally {
        setIsLoading(false);
        setHasLoaded(true);
      }
    };

    load();
  }, [orderId, isEligible, hasLoaded]);

  const handleCreateInvoice = async () => {
    setIsCreatingInvoice(true);
    try {
      // Due date 30 days from today
      const due = new Date();
      due.setDate(due.getDate() + 30);
      const invoice = await invoicesApi.createFromOrder({
        order_id: orderId,
        due_date: due.toISOString(),
      });
      setExistingInvoiceId(invoice.id);
      showToast(
        `Rechnung ${invoice.invoice_number} wurde erstellt. Jetzt unter Rechnungen sichtbar.`,
        'success'
      );
    } catch (err: any) {
      showToast(
        err.response?.data?.detail || 'Fehler beim Erstellen der Rechnung',
        'error'
      );
    } finally {
      setIsCreatingInvoice(false);
    }
  };

  if (!isEligible) {
    return (
      <div className="tab-panel">
        <h2>Soll/Ist-Vergleich</h2>
        <div className="soll-ist-unavailable">
          <p className="soll-ist-unavailable-icon">&#9432;</p>
          <p>
            Der Soll/Ist-Vergleich ist nur für abgeschlossene Aufträge verfügbar.
          </p>
          <p className="soll-ist-unavailable-hint">
            Setze den Status auf <strong>Fertiggestellt</strong> oder{' '}
            <strong>Ausgeliefert</strong>, um den Vergleich zu aktivieren.
          </p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="tab-panel">
        <h2>Soll/Ist-Vergleich</h2>
        <p className="page-loading">Lade Vergleichsdaten...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="tab-panel">
        <h2>Soll/Ist-Vergleich</h2>
        <p className="soll-ist-error">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="tab-panel">
        <h2>Soll/Ist-Vergleich</h2>
        <p className="empty-message">Keine Vergleichsdaten verfügbar.</p>
      </div>
    );
  }

  return (
    <div className="tab-panel">
      <div className="soll-ist-header">
        <h2>Soll/Ist-Vergleich</h2>
        <AccuracyBadge score={data.overall_accuracy_score} />
      </div>

      {data.has_significant_deviation && (
        <div className="soll-ist-alert">
          Mindestens eine Kennzahl weicht um mehr als 20&nbsp;% ab.
        </div>
      )}

      {/* Core metrics */}
      <section className="soll-ist-section">
        <h3>Kennzahlen</h3>
        <div className="soll-ist-metrics">
          <MetricRow
            label="Arbeitsstunden"
            metric={data.hours}
            unit="h"
            decimals={1}
          />
          <MetricRow
            label="Materialgewicht"
            metric={data.material_weight}
            unit="g"
            decimals={1}
          />
          <MetricRow
            label="Materialkosten"
            metric={data.material_cost}
            unit="€"
            decimals={2}
          />
          <MetricRow
            label="Gesamtpreis"
            metric={data.total_price}
            unit="€"
            decimals={2}
          />
        </div>
      </section>

      {/* Activity breakdown */}
      <section className="soll-ist-section">
        <h3>Aufschlüsselung nach Aktivität</h3>
        <ActivityTable rows={data.activity_breakdown} />
      </section>

      {/* Invoice shortcut — visible once invoice status is known */}
      {existingInvoiceId === null && (
        <div className="soll-ist-invoice-action">
          <button
            className="btn-primary soll-ist-invoice-btn"
            onClick={handleCreateInvoice}
            disabled={isCreatingInvoice}
          >
            {isCreatingInvoice ? 'Rechnung wird erstellt...' : 'Rechnung erstellen'}
          </button>
        </div>
      )}
      {existingInvoiceId !== null && existingInvoiceId !== undefined && (
        <div className="soll-ist-invoice-action">
          <span className="soll-ist-invoice-exists">
            Rechnung vorhanden (ID&nbsp;{existingInvoiceId})
          </span>
        </div>
      )}
    </div>
  );
};

export default SollIstTab;
