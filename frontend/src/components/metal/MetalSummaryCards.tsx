// Metal inventory summary (W4-03): per-metal totals next to live spot prices
// and the depletion forecast. Statistics are required; spot prices and the
// forecast are optional extras, so their failures leave the cards intact
// (no badge) instead of blocking the view.
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import type { InventoryStatistics, MetalInventorySummary, MetalPriceResponse } from '../../types';
import { getErrorMessage } from '../../lib/errors';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { Card, PageState, type CardTone, type PageStateValue } from '../../ui';
import { formatDate, formatWeight, METAL_TYPE_LABELS } from './metalLabels';
import { forecastQuery, spotPricesQuery, statisticsQuery, type ForecastItem } from './metalQueries';

const PRICE_EPSILON = 0.001;
const WEEKS_CRITICAL = 2;
const WEEKS_WARNING = 4;

interface ForecastBadge {
  tone: 'done' | 'waiting' | 'danger';
  label: string;
}

function forecastBadge(forecast: ForecastItem): ForecastBadge {
  if (forecast.reorder_is_overdue) return { tone: 'danger', label: 'Nachbestellung überfällig' };
  const weeks = forecast.weeks_until_depletion;
  if (weeks === null) return { tone: 'done', label: 'Kein Verbrauch erfasst' };
  const label = `Aufgebraucht in ${weeks.toFixed(1).replace('.', ',')} Wochen`;
  if (weeks < WEEKS_CRITICAL) return { tone: 'danger', label };
  if (weeks <= WEEKS_WARNING) return { tone: 'waiting', label };
  return { tone: 'done', label };
}

function spotComparison(summary: MetalInventorySummary, spot: MetalPriceResponse): string {
  const diff = summary.average_price_per_gram - spot.price_per_gram;
  const pct = ((Math.abs(diff) / spot.price_per_gram) * 100).toFixed(1).replace('.', ',');
  if (diff < -PRICE_EPSILON) return `${pct} % unter Kurs`;
  if (diff > PRICE_EPSILON) return `${pct} % über Kurs`;
  return 'Am Kurs';
}

function toMap<T extends { metal_type: string }>(items: T[] | undefined): Record<string, T> {
  return Object.fromEntries((items ?? []).map((item) => [item.metal_type, item]));
}

interface MetalCardProps {
  summary: MetalInventorySummary;
  spot: MetalPriceResponse | undefined;
  forecast: ForecastItem | undefined;
}

const MetalCard: React.FC<MetalCardProps> = ({ summary, spot, forecast }) => {
  const config = METAL_TYPE_LABELS[summary.metal_type];
  const badge = forecast ? forecastBadge(forecast) : null;
  const tone: CardTone | undefined = badge?.tone === 'danger' ? 'danger' : undefined;
  const range =
    summary.oldest_batch_date &&
    (summary.newest_batch_date && summary.newest_batch_date !== summary.oldest_batch_date
      ? `${formatDate(summary.oldest_batch_date)} – ${formatDate(summary.newest_batch_date)}`
      : formatDate(summary.oldest_batch_date));

  return (
    <Card title={config ? `${config.label} (${config.purity})` : summary.metal_type} headingLevel={3} tone={tone}>
      <dl className="metal-stats">
        <div>
          <dt>Bestand</dt>
          <dd className="ui-num">{formatWeight(summary.total_weight_g)}</dd>
        </div>
        <div>
          <dt>Wert</dt>
          <dd className={MONEY_CLASS}>{formatEur(summary.total_value)}</dd>
        </div>
        <div>
          <dt>Ø Einkauf/g</dt>
          <dd className={MONEY_CLASS}>{formatEur(summary.average_price_per_gram)}</dd>
        </div>
        {spot && (
          <div>
            <dt>Aktueller Kurs</dt>
            <dd>
              <span className={MONEY_CLASS}>{formatEur(spot.price_per_gram)}/g</span>
              <span className="metal-stats__note" title={`Quelle: ${spot.source} · Stand: ${formatDate(spot.updated_at)}`}>
                {spotComparison(summary, spot)}
              </span>
            </dd>
          </div>
        )}
      </dl>
      <p className="metal-card__meta">
        {summary.batch_count} {summary.batch_count === 1 ? 'Charge' : 'Chargen'}
        {range && <> · {range}</>}
      </p>
      {badge && forecast && (
        <p className={`metal-forecast metal-forecast--${badge.tone}`} title={forecast.confidence_note}>
          <span className="metal-forecast__label">{badge.label}</span>
          {forecast.depletion_date && (
            <span className="metal-forecast__date">
              Voraussichtlich aufgebraucht: {formatDate(forecast.depletion_date)}
            </span>
          )}
          {forecast.reorder_is_overdue && <strong>Sofort nachbestellen.</strong>}
        </p>
      )}
    </Card>
  );
};

function summaryState(query: { isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown }, stats?: InventoryStatistics): PageStateValue {
  if (query.isPending) return { status: 'loading' };
  if (query.isError) {
    return {
      status: 'error',
      error: getErrorMessage(query.error, 'Inventar-Übersicht konnte nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }
  return { status: stats?.metal_types.length ? 'ready' : 'empty' };
}

export const MetalSummaryCards: React.FC = () => {
  const stats = useQuery(statisticsQuery());
  const spot = useQuery(spotPricesQuery());
  const forecast = useQuery(forecastQuery());

  const summaries = stats.data?.metal_types ?? [];
  const spotByMetal = toMap(spot.data?.prices);
  const forecastByMetal = toMap(forecast.data?.forecasts);
  const totalValue = stats.data?.total_value ?? summaries.reduce((sum, s) => sum + s.total_value, 0);
  const totalWeight = stats.data?.total_weight_g ?? summaries.reduce((sum, s) => sum + s.total_weight_g, 0);
  const lowStock = stats.data?.low_stock_alerts ?? [];

  return (
    <section className="metal-summary" aria-labelledby="metal-summary-title">
      <div className="metal-summary__header">
        <h2 id="metal-summary-title">Metall-Inventar Übersicht</h2>
        {stats.data && (
          <p className="metal-summary__totals">
            Gesamtwert: <span className={MONEY_CLASS}>{formatEur(totalValue)}</span> · Gesamtbestand:{' '}
            <span className="ui-num">{formatWeight(totalWeight)}</span>
          </p>
        )}
      </div>
      {lowStock.length > 0 && (
        <Card tone="waiting" className="metal-summary__alert">
          <strong>Niedriger Bestand:</strong> {lowStock.join(' · ')}
        </Card>
      )}
      <PageState
        state={summaryState(stats, stats.data)}
        skeleton="cards"
        empty={{ icon: 'inbox', title: 'Noch keine Metalleinkäufe', body: 'Legen Sie den ersten Einkauf an.' }}
      >
        <div className="metal-summary__cards">
          {summaries.map((summary) => (
            <MetalCard
              key={summary.metal_type}
              summary={summary}
              spot={spotByMetal[summary.metal_type]}
              forecast={forecastByMetal[summary.metal_type]}
            />
          ))}
        </div>
      </PageState>
    </section>
  );
};
