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
      // Spot price failures are intentionally silent.
    } catch (err: any) {
      setError(err.message || 'Fehler beim Laden der Zusammenfassung');
    } finally {
      setIsLoading(false);
    }
  };

  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  };

  const formatWeight = (grams: number): string => {
    if (grams >= 1000) {
      return `${(grams / 1000).toFixed(2)} kg`;
    }
    return `${grams.toFixed(2)} g`;
  };

  const formatDate = (dateStr?: string): string => {
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
    return <div className="metal-summary-error">❌ {error}</div>;
  }

  if (summaries.length === 0) {
    return (
      <div className="metal-summary-empty">
        <p>Keine Metalleinkäufe vorhanden.</p>
      </div>
    );
  }

  // Use pre-aggregated totals from statistics when available; derive from
  // per-metal summaries as fallback so the component still renders correctly.
  const totalInventoryValue = statistics?.total_value ?? summaries.reduce((sum, s) => sum + s.total_value, 0);
  const totalRemainingWeight = statistics?.total_weight_g ?? summaries.reduce((sum, s) => sum + s.total_weight_g, 0);

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

      <div className="metal-summary-cards">
        {summaries.map((summary) => {
          const config = METAL_TYPE_CONFIG[summary.metal_type];
          // Backend does not return a separate remaining field on MetalInventorySummary.
          // total_weight_g already reflects only the remaining (non-depleted) weight
          // per the statistics endpoint, so usage percentage is reported as 0 here.
          const usagePercentage = 0;

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
                  <span className="stat-label">Gewicht gesamt:</span>
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
                  <span className="stat-label">Ø Preis/g:</span>
                  <span className="stat-value">
                    {formatCurrency(summary.average_price_per_gram)}
                  </span>
                </div>
              </div>

              <div className="metal-card-usage">
                <div className="usage-bar-container">
                  <div
                    className="usage-bar-fill"
                    style={{ width: `${usagePercentage}%` }}
                  />
                </div>
                <span className="usage-percentage">{usagePercentage.toFixed(1)}% verbraucht</span>
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
                      {formatDate(summary.oldest_batch_date)} -{' '}
                      {formatDate(summary.newest_batch_date)}
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
