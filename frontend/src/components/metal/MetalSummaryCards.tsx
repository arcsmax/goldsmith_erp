// Metal Inventory Summary Cards Component
// Displays per-metal inventory totals alongside live spot prices from /metal-prices.
// Color coding: green when average purchase price is below current spot (good deal),
// red when above spot (purchased above market). Spot price failures degrade gracefully.
import React, { useEffect, useState } from 'react';
import { metalInventoryApi } from '../../api';
import { MetalInventorySummary, InventoryStatistics, MetalPriceResponse, MetalType } from '../../types';
import '../../styles/metal-inventory.css';

interface MetalConfig {
  label: string;
  icon: string;
  className: string;
  purity?: string;
}

const METAL_TYPE_CONFIG: Record<MetalType, MetalConfig> = {
  gold_24k: { label: 'Gold 24K', icon: '🥇', className: 'metal-gold-24k', purity: '999.9' },
  gold_22k: { label: 'Gold 22K', icon: '🥇', className: 'metal-gold-22k', purity: '916' },
  gold_18k: { label: 'Gold 18K', icon: '🥇', className: 'metal-gold-18k', purity: '750' },
  gold_14k: { label: 'Gold 14K', icon: '🥇', className: 'metal-gold-14k', purity: '585' },
  gold_9k: { label: 'Gold 9K', icon: '🥇', className: 'metal-gold-9k', purity: '375' },
  silver_999: { label: 'Silber 999', icon: '⚪', className: 'metal-silver-999', purity: '999' },
  silver_925: { label: 'Silber 925', icon: '⚪', className: 'metal-silver-925', purity: '925' },
  silver_800: { label: 'Silber 800', icon: '⚪', className: 'metal-silver-800', purity: '800' },
  platinum_950: { label: 'Platin 950', icon: '💎', className: 'metal-platinum-950', purity: '950' },
  platinum_900: { label: 'Platin 900', icon: '💎', className: 'metal-platinum-900', purity: '900' },
  palladium: { label: 'Palladium', icon: '💎', className: 'metal-palladium', purity: '999' },
  white_gold_18k: { label: 'Weißgold 18K', icon: '🤍', className: 'metal-white-gold-18k', purity: '750' },
  white_gold_14k: { label: 'Weißgold 14K', icon: '🤍', className: 'metal-white-gold-14k', purity: '585' },
  rose_gold_18k: { label: 'Rotgold 18K', icon: '🌹', className: 'metal-rose-gold-18k', purity: '750' },
  rose_gold_14k: { label: 'Rotgold 14K', icon: '🌹', className: 'metal-rose-gold-14k', purity: '585' },
};

export const MetalSummaryCards: React.FC = () => {
  const [summaries, setSummaries] = useState<MetalInventorySummary[]>([]);
  const [statistics, setStatistics] = useState<InventoryStatistics | null>(null);
  // Spot prices keyed by metal_type string value
  const [spotPrices, setSpotPrices] = useState<Record<string, MetalPriceResponse>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Fetch inventory statistics and spot prices in parallel.
      // Spot price failure does not block the inventory view.
      const [statsResult, spotResult] = await Promise.allSettled([
        metalInventoryApi.getStatistics(),
        metalInventoryApi.getSpotPrices(),
      ]);

      if (statsResult.status === 'fulfilled') {
        setStatistics(statsResult.value);
        setSummaries(statsResult.value.metal_types);
      } else {
        throw new Error(
          (statsResult.reason as any)?.response?.data?.detail ||
            'Fehler beim Laden der Statistiken'
        );
      }

      if (spotResult.status === 'fulfilled') {
        const priceMap: Record<string, MetalPriceResponse> = {};
        for (const entry of spotResult.value.prices) {
          priceMap[entry.metal_type] = entry;
        }
        setSpotPrices(priceMap);
      }
      // Spot price failures are intentionally silent — partial data is acceptable.
    } catch (err: any) {
      setError(err.message || 'Fehler beim Laden der Zusammenfassung');
    } finally {
      setIsLoading(false);
    }
  };

  const formatCurrency = (amount: number): string =>
    new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(amount);

  const formatWeight = (grams: number): string => {
    if (grams >= 1000) return `${(grams / 1000).toFixed(2)} kg`;
    return `${grams.toFixed(2)} g`;
  };

  const formatDate = (dateStr?: string | null): string => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('de-DE', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  if (isLoading) {
    return <div className="metal-summary-loading">Lade Inventar-Zusammenfassung...</div>;
  }

  if (error) {
    return <div className="metal-summary-error">Fehler: {error}</div>;
  }

  if (summaries.length === 0) {
    return (
      <div className="metal-summary-empty">
        <p>Keine Metalleinkäufe vorhanden.</p>
      </div>
    );
  }

  const totalInventoryValue =
    statistics?.total_value ?? summaries.reduce((sum, s) => sum + s.total_value, 0);
  const totalRemainingWeight =
    statistics?.total_weight_g ?? summaries.reduce((sum, s) => sum + s.total_weight_g, 0);

  return (
    <div className="metal-summary-container">
      <div className="metal-summary-header">
        <h2>Metall-Inventar Übersicht</h2>
        <div className="metal-summary-totals">
          <div className="total-value">
            <span className="total-label">Gesamtwert:</span>
            <span className="total-amount">{formatCurrency(totalInventoryValue)}</span>
          </div>
          <div className="total-weight">
            <span className="total-label">Gesamtbestand:</span>
            <span className="total-amount">{formatWeight(totalRemainingWeight)}</span>
          </div>
        </div>
      </div>

      {statistics && statistics.low_stock_alerts.length > 0 && (
        <div className="metal-low-stock-banner" role="alert">
          <strong>Niedriger Bestand:</strong>{' '}
          {statistics.low_stock_alerts.join(' · ')}
        </div>
      )}

      <div className="metal-summary-cards">
        {summaries.map((summary) => {
          const config = METAL_TYPE_CONFIG[summary.metal_type];
          const spot = spotPrices[summary.metal_type] ?? null;

          // Determine whether the average purchase price is above or below spot.
          let spotClass = '';
          let spotBadge: string | null = null;
          if (spot) {
            const diff = summary.average_price_per_gram - spot.price_per_gram;
            const pct = (Math.abs(diff) / spot.price_per_gram) * 100;
            if (diff < -0.001) {
              spotClass = 'spot-below';
              spotBadge = `${pct.toFixed(1)} % unter Kurs`;
            } else if (diff > 0.001) {
              spotClass = 'spot-above';
              spotBadge = `${pct.toFixed(1)} % über Kurs`;
            } else {
              spotBadge = 'Am Kurs';
            }
          }

          return (
            <div key={summary.metal_type} className={`metal-card ${config.className}`}>
              <div className="metal-card-header">
                <span className="metal-icon">{config.icon}</span>
                <div className="metal-title">
                  <h3>{config.label}</h3>
                  {config.purity && <span className="metal-purity">{config.purity}</span>}
                </div>
              </div>

              <div className="metal-card-stats">
                <div className="stat-row">
                  <span className="stat-label">Bestand:</span>
                  <span className="stat-value primary">
                    {formatWeight(summary.total_weight_g)}
                  </span>
                </div>

                <div className="stat-row">
                  <span className="stat-label">Wert:</span>
                  <span className="stat-value highlight">
                    {formatCurrency(summary.total_value)}
                  </span>
                </div>

                <div className="stat-row">
                  <span className="stat-label">Ø Einkauf/g:</span>
                  <span className="stat-value">
                    {formatCurrency(summary.average_price_per_gram)}
                  </span>
                </div>

                {/* Live spot price row — only rendered when data is available */}
                {spot && (
                  <div className="stat-row stat-row--spot">
                    <span className="stat-label">Aktueller Kurs:</span>
                    <div className="spot-price-cell">
                      <span className="stat-value">
                        {formatCurrency(spot.price_per_gram)}/g
                      </span>
                      {spotBadge && (
                        <span
                          className={`spot-comparison-badge ${spotClass}`}
                          title={`Quelle: ${spot.source} · Stand: ${formatDate(spot.updated_at)}`}
                        >
                          {spotBadge}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div className="metal-card-details">
                <div className="detail-item">
                  <span className="detail-icon">📦</span>
                  <span className="detail-text">{summary.batch_count} Charge(n)</span>
                </div>
                {summary.oldest_batch_date && (
                  <div className="detail-item">
                    <span className="detail-icon">📅</span>
                    <span className="detail-text">
                      {formatDate(summary.oldest_batch_date)}
                      {summary.newest_batch_date &&
                        summary.newest_batch_date !== summary.oldest_batch_date
                        ? ` – ${formatDate(summary.newest_batch_date)}`
                        : ''}
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
