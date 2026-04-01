// UsageHistoryPanel.tsx
// Shows material consumption history from GET /metal-inventory/usage.
// Filterable by metal type. Order IDs link to the order detail page.
import React, { useEffect, useState } from 'react';
import { metalInventoryApi } from '../../api';
import { MaterialUsageRead, MetalType } from '../../types';

interface UsageHistoryPanelProps {
  /** Set to a timestamp to trigger a reload after a new consumption is booked. */
  refreshKey?: number;
}

const METAL_TYPE_LABELS: Record<MetalType, string> = {
  gold_24k: 'Gold 24K',
  gold_22k: 'Gold 22K',
  gold_18k: 'Gold 18K',
  gold_14k: 'Gold 14K',
  gold_9k: 'Gold 9K',
  silver_999: 'Silber 999',
  silver_925: 'Silber 925',
  silver_800: 'Silber 800',
  platinum_950: 'Platin 950',
  platinum_900: 'Platin 900',
  palladium: 'Palladium',
  white_gold_18k: 'Weißgold 18K',
  white_gold_14k: 'Weißgold 14K',
  rose_gold_18k: 'Rotgold 18K',
  rose_gold_14k: 'Rotgold 14K',
};

const COSTING_METHOD_LABELS: Record<string, string> = {
  fifo: 'FIFO',
  lifo: 'LIFO',
  average: 'Durchschnitt',
  specific: 'Spezifisch',
};

const formatCurrency = (amount: number): string =>
  new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(amount);

const formatDate = (dateStr: string): string =>
  new Date(dateStr).toLocaleDateString('de-DE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

export const UsageHistoryPanel: React.FC<UsageHistoryPanelProps> = ({ refreshKey }) => {
  const [usageRecords, setUsageRecords] = useState<MaterialUsageRead[]>([]);
  const [filterMetalType, setFilterMetalType] = useState<MetalType | ''>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchUsage();
  }, [filterMetalType, refreshKey]);

  const fetchUsage = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const records = await metalInventoryApi.getUsageHistory({
        metal_type: filterMetalType || undefined,
        limit: 100,
      });
      setUsageRecords(records);
    } catch (err: any) {
      setError(
        err.response?.data?.detail || 'Fehler beim Laden der Verbrauchshistorie.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="usage-history-panel">
      <div className="usage-history-header">
        <h3>Verbrauchshistorie</h3>
        <div className="usage-history-filter">
          <label htmlFor="usage-filter-metal">Metalltyp:</label>
          <select
            id="usage-filter-metal"
            value={filterMetalType}
            onChange={(e) => setFilterMetalType(e.target.value as MetalType | '')}
          >
            <option value="">Alle Metalle</option>
            {(Object.entries(METAL_TYPE_LABELS) as [MetalType, string][]).map(
              ([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              )
            )}
          </select>
        </div>
      </div>

      {isLoading && (
        <div className="usage-history-loading">Lade Verbrauchshistorie...</div>
      )}

      {error && (
        <div className="usage-history-error" role="alert">
          {error}
        </div>
      )}

      {!isLoading && !error && usageRecords.length === 0 && (
        <div className="usage-history-empty">
          <p>Keine Verbrauchsdaten vorhanden{filterMetalType ? ' für diesen Metalltyp' : ''}.</p>
        </div>
      )}

      {!isLoading && !error && usageRecords.length > 0 && (
        <div className="table-container">
          <table className="usage-history-table">
            <thead>
              <tr>
                <th>Datum</th>
                <th>Auftrag</th>
                <th>Metalltyp</th>
                <th>Gewicht</th>
                <th>Preis/g</th>
                <th>Kosten</th>
                <th>Methode</th>
                <th>Charge</th>
                <th>Notiz</th>
              </tr>
            </thead>
            <tbody>
              {usageRecords.map((record) => (
                <tr key={record.id}>
                  <td className="usage-date">{formatDate(record.used_at)}</td>
                  <td>
                    <a
                      href={`/orders/${record.order_id}`}
                      className="order-link"
                      title={`Auftrag #${record.order_id} öffnen`}
                    >
                      #{record.order_id}
                    </a>
                  </td>
                  <td>
                    {record.metal_type
                      ? METAL_TYPE_LABELS[record.metal_type] ?? record.metal_type
                      : '-'}
                  </td>
                  <td className="usage-weight">{record.weight_used_g.toFixed(3)} g</td>
                  <td>{formatCurrency(record.price_per_gram_at_time)}/g</td>
                  <td className="usage-cost">{formatCurrency(record.cost_at_time)}</td>
                  <td>
                    <span className="method-badge">
                      {COSTING_METHOD_LABELS[record.costing_method] ?? record.costing_method}
                    </span>
                  </td>
                  <td className="usage-batch">#{record.metal_purchase_id}</td>
                  <td className="usage-notes">{record.notes ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
