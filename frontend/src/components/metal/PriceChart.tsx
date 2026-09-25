// PriceChart.tsx
// Inline SVG line chart showing metal spot price over time.
// No external chart library — keeps the bundle lean and avoids licence issues.
// Supports gold_24k, silver_999, platinum_950 (the three base metals that have
// dedicated history rows in metal_price_history).

import React, { useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { MetalType } from '../../types';
import { getErrorMessage } from '../../lib/errors';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { Card, Field, PageState, type PageStateValue } from '../../ui';
import { priceHistoryQuery, type PricePoint } from './metalQueries';

// ─── Constants ──────────────────────────────────────────────────────────────

const SUPPORTED_METALS: { value: MetalType; label: string }[] = [
  { value: 'gold_24k' as MetalType, label: 'Gold 24K (Feingold)' },
  { value: 'silver_999' as MetalType, label: 'Silber 999' },
  { value: 'platinum_950' as MetalType, label: 'Platin 950' },
];

// Chart dimensions (SVG viewport — scales via CSS)
const SVG_WIDTH = 600;
const SVG_HEIGHT = 220;
const PADDING = { top: 16, right: 20, bottom: 32, left: 56 };
const DEFAULT_DAYS = 30;
const DAY_OPTIONS = [7, 30, 90] as const;

const CHART_W = SVG_WIDTH - PADDING.left - PADDING.right;
const CHART_H = SVG_HEIGHT - PADDING.top - PADDING.bottom;

// ─── Helper functions ────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: 'short' });
}

// Map a value from [domainMin, domainMax] to [rangeMin, rangeMax].
function scale(value: number, domainMin: number, domainMax: number, rangeMin: number, rangeMax: number): number {
  if (domainMax === domainMin) return (rangeMin + rangeMax) / 2;
  return rangeMin + ((value - domainMin) / (domainMax - domainMin)) * (rangeMax - rangeMin);
}

// ─── SVG Chart ──────────────────────────────────────────────────────────────

interface ChartProps {
  points: PricePoint[];
  avg7d: number;
  avg30d: number;
}

const LineChart: React.FC<ChartProps> = ({ points, avg7d, avg30d }) => {
  if (points.length === 0) {
    return <p className="price-chart__note">Keine historischen Daten verfügbar.</p>;
  }

  const prices = points.map((p) => p.price_per_gram_eur);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);

  // Add 3 % padding to y-axis so the line does not clip the borders.
  const yPad = (maxPrice - minPrice) * 0.03 || maxPrice * 0.03 || 1;
  const yMin = minPrice - yPad;
  const yMax = maxPrice + yPad;

  const toX = (i: number) => scale(i, 0, Math.max(points.length - 1, 1), 0, CHART_W);
  const toY = (v: number) => scale(v, yMin, yMax, CHART_H, 0);

  // Build SVG polyline points string.
  const linePath = points
    .map((p, i) => `${toX(i).toFixed(1)},${toY(p.price_per_gram_eur).toFixed(1)}`)
    .join(' ');

  // Area fill path (close below the x-axis).
  const areaPath =
    `M${toX(0).toFixed(1)},${CHART_H} ` +
    points.map((p, i) => `L${toX(i).toFixed(1)},${toY(p.price_per_gram_eur).toFixed(1)}`).join(' ') +
    ` L${toX(points.length - 1).toFixed(1)},${CHART_H} Z`;

  // Y-axis ticks: 4 evenly spaced values.
  const yTicks = Array.from({ length: 4 }, (_, i) => yMin + ((yMax - yMin) * i) / 3);

  // X-axis ticks: at most 6 date labels evenly spaced.
  const xTickCount = Math.min(6, points.length);
  const xTickIndices = Array.from({ length: xTickCount }, (_, i) =>
    Math.round((i / Math.max(xTickCount - 1, 1)) * (points.length - 1))
  );

  // Average line Y positions.
  const y7d = toY(avg7d);
  const y30d = toY(avg30d);

  return (
    <svg
      viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
      className="price-chart__svg"
      role="img"
      aria-label="Preisverlauf Linienchart"
    >
      <defs>
        <linearGradient id="chartAreaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--color-chart-primary)" stopOpacity="0.25" />
          <stop offset="100%" stopColor="var(--color-chart-primary)" stopOpacity="0.02" />
        </linearGradient>
      </defs>

      <g transform={`translate(${PADDING.left},${PADDING.top})`}>
        {/* Grid lines + Y-axis labels */}
        {yTicks.map((tick) => {
          const y = toY(tick).toFixed(1);
          return (
            <g key={tick}>
              <line
                x1={0}
                y1={y}
                x2={CHART_W}
                y2={y}
                stroke="var(--color-border)"
                strokeWidth={1}
              />
              <text
                x={-6}
                y={parseFloat(y) + 4}
                textAnchor="end"
                fontSize={10}
                fill="var(--color-text-muted)"
              >
                {formatEur(tick)}
              </text>
            </g>
          );
        })}

        {/* X-axis labels */}
        {xTickIndices.map((idx) => (
          <text
            key={idx}
            x={toX(idx).toFixed(1)}
            y={CHART_H + 20}
            textAnchor="middle"
            fontSize={10}
            fill="var(--color-text-muted)"
          >
            {formatDate(points[idx].fetched_at)}
          </text>
        ))}

        {/* Area fill */}
        <path d={areaPath} fill="url(#chartAreaGrad)" />

        {/* 30-day average line */}
        <line
          x1={0}
          y1={y30d.toFixed(1)}
          x2={CHART_W}
          y2={y30d.toFixed(1)}
          stroke="var(--color-text-muted)"
          strokeWidth={1}
          strokeDasharray="4 3"
          opacity={0.8}
        />

        {/* 7-day average line */}
        <line
          x1={0}
          y1={y7d.toFixed(1)}
          x2={CHART_W}
          y2={y7d.toFixed(1)}
          stroke="var(--color-info)"
          strokeWidth={1}
          strokeDasharray="4 3"
          opacity={0.8}
        />

        {/* Price line */}
        <polyline
          points={linePath}
          fill="none"
          stroke="var(--color-chart-primary)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Axis borders */}
        <line x1={0} y1={0} x2={0} y2={CHART_H} stroke="var(--color-border-strong)" strokeWidth={1} />
        <line x1={0} y1={CHART_H} x2={CHART_W} y2={CHART_H} stroke="var(--color-border-strong)" strokeWidth={1} />
      </g>
    </svg>
  );
};

// ─── Main component ──────────────────────────────────────────────────────────

export const PriceChart: React.FC = () => {
  const [selectedMetal, setSelectedMetal] = useState<MetalType>('gold_24k' as MetalType);
  const [selectedDays, setSelectedDays] = useState<number>(DEFAULT_DAYS);
  const query = useQuery({ ...priceHistoryQuery(selectedMetal, selectedDays), placeholderData: keepPreviousData });
  const data = query.data;

  const metalLabel = useMemo(
    () => SUPPORTED_METALS.find((m) => m.value === selectedMetal)?.label ?? selectedMetal,
    [selectedMetal]
  );

  const state: PageStateValue = query.isPending
    ? { status: 'loading' }
    : query.isError && !data
      ? {
          status: 'error',
          error: getErrorMessage(query.error, 'Preishistorie konnte nicht geladen werden.'),
          retry: () => void query.refetch(),
        }
      : { status: 'ready' };

  return (
    <Card title="Kursverlauf" className="price-chart">
      <div className="price-chart__controls">
        <Field label="Metall" name="price-chart-metal">
          <select value={selectedMetal} onChange={(e) => setSelectedMetal(e.target.value as MetalType)}>
            {SUPPORTED_METALS.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Zeitraum" name="price-chart-days">
          <select value={selectedDays} onChange={(e) => setSelectedDays(Number(e.target.value))}>
            {DAY_OPTIONS.map((days) => (
              <option key={days} value={days}>{days} Tage</option>
            ))}
          </select>
        </Field>
      </div>

      <PageState state={state} skeleton="detail">
        {data && (
          <>
            <dl className="price-chart__stats">
              <div>
                <dt>Aktuell</dt>
                <dd className={MONEY_CLASS}>{formatEur(data.current_price)}/g</dd>
              </div>
              <div>
                <dt>7-Tage-Ø</dt>
                <dd className={MONEY_CLASS}>{formatEur(data.avg_7d)}/g</dd>
              </div>
              <div>
                <dt>30-Tage-Ø</dt>
                <dd className={MONEY_CLASS}>{formatEur(data.avg_30d)}/g</dd>
              </div>
            </dl>

            <LineChart points={data.points} avg7d={data.avg_7d} avg30d={data.avg_30d} />

            <ul className="price-chart__legend">
              <li className="price-chart__legend-item price-chart__legend-item--line">Kursverlauf {metalLabel}</li>
              <li className="price-chart__legend-item price-chart__legend-item--avg7">7-Tage-Durchschnitt</li>
              <li className="price-chart__legend-item price-chart__legend-item--avg30">30-Tage-Durchschnitt</li>
            </ul>

            <p className="price-chart__note">
              {data.points.length} Datenpunkte · {data.days} Tage
            </p>
          </>
        )}
      </PageState>
    </Card>
  );
};
