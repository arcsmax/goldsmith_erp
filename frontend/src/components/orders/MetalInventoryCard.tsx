// MetalInventoryCard: the order's metal (type, weights, costing method) in
// the Arbeit tab. W4-03: plain definition lists inside the parent section,
// router links instead of window.location, no emoji icons.
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { CostingMethod, MetalType } from '../../types';
import { ButtonLink } from '../../ui';

interface OrderMetalData {
  metal_type?: MetalType | null;
  estimated_weight_g?: number | null;
  actual_weight_g?: number | null;
  scrap_percentage?: number;
  costing_method_used?: CostingMethod;
  specific_metal_purchase_id?: number | null;
  status?: string;
}

interface MetalInventoryCardProps {
  order: OrderMetalData;
}

const DEFAULT_SCRAP_PERCENT = 5;

const METAL_TYPE_LABELS: Partial<Record<MetalType, string>> = {
  gold_24k: 'Gold 24 Karat (999)',
  gold_18k: 'Gold 18 Karat (750)',
  gold_14k: 'Gold 14 Karat (585)',
  silver_925: 'Silber 925',
  silver_999: 'Silber 999',
  platinum_950: 'Platin 950',
  platinum_900: 'Platin 900',
};

const COSTING_METHODS: Record<CostingMethod, { label: string; description: string }> = {
  fifo: { label: 'FIFO', description: 'Älteste Charge zuerst' },
  lifo: { label: 'LIFO', description: 'Neueste Charge zuerst' },
  average: { label: 'Durchschnitt', description: 'Durchschnittspreis aller Chargen' },
  specific: { label: 'Bestimmte Charge', description: 'Eine bestimmte Charge ist ausgewählt' },
};

const WEIGHT_FORMAT = new Intl.NumberFormat('de-DE', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function formatWeight(grams: number): string {
  return `${WEIGHT_FORMAT.format(grams)} g`;
}

function Line({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="metal-line">
      <dt className="metal-label">{label}</dt>
      <dd className="metal-value tabular-nums">{value}</dd>
    </div>
  );
}

export function MetalInventoryCard({ order }: MetalInventoryCardProps) {
  if (!order.metal_type) return null;

  const metalLabel = METAL_TYPE_LABELS[order.metal_type] ?? order.metal_type;
  const estimatedWeight = order.estimated_weight_g ?? 0;
  const scrapPercent = order.scrap_percentage ?? DEFAULT_SCRAP_PERCENT;
  const scrapWeight = estimatedWeight * (scrapPercent / 100);
  const actualWeight = order.actual_weight_g ?? null;
  const isFinished = order.status === 'completed' || order.status === 'delivered';
  const showActual = actualWeight !== null && (isFinished || actualWeight > 0);
  const deviation = actualWeight !== null ? actualWeight - estimatedWeight : 0;
  const method = COSTING_METHODS[order.costing_method_used ?? 'fifo'];
  const batchId =
    order.costing_method_used === 'specific' ? order.specific_metal_purchase_id : null;

  return (
    <div className="metal-inventory-card">
      <dl className="metal-weight-grid">
        <Line label="Metallart" value={metalLabel} />
        <Line label="Geschätztes Gewicht" value={formatWeight(estimatedWeight)} />
        <Line label={`Verschnitt (${scrapPercent} %)`} value={`+${formatWeight(scrapWeight)}`} />
        <Line label="Gesamtbedarf" value={formatWeight(estimatedWeight + scrapWeight)} />
        {showActual && actualWeight !== null && (
          <Line label="Tatsächliches Gewicht" value={formatWeight(actualWeight)} />
        )}
        {showActual && deviation !== 0 && (
          <Line
            label="Abweichung"
            value={`${deviation > 0 ? '+' : ''}${formatWeight(deviation)}`}
          />
        )}
        <Line label="Kalkulationsmethode" value={`${method.label}: ${method.description}`} />
        <Line
          label="Zuweisung"
          value={
            batchId ? (
              <Link to={`/metal-inventory/${batchId}`} className="batch-link">
                Charge #{batchId}
              </Link>
            ) : (
              'Automatisch'
            )
          }
        />
      </dl>
      <ButtonLink to="/metal-inventory" variant="secondary">
        Metallinventar öffnen
      </ButtonLink>
    </div>
  );
}
