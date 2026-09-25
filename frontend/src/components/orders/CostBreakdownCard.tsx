// CostBreakdownCard — cost breakdown of an order (material, labour, margin,
// VAT, final price). W4-03: src/ui Card + EmptyState, formatEur with
// tabular numerals, no emoji. Financial data: the caller renders this card
// only for roles that may see pricing (OrderWorkTab).
import React from 'react';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { Button, Card, EmptyState } from '../../ui';
import './cost-change.css';

interface OrderCostData {
  // Cost Calculation
  material_cost_calculated?: number | null;
  material_cost_override?: number | null;
  labor_hours?: number | null;
  hourly_rate?: number;
  labor_cost?: number | null;

  // Pricing
  profit_margin_percent?: number;
  vat_rate?: number;
  calculated_price?: number | null;
  price?: number | null;

  // Metal info (for breakdown)
  estimated_weight_g?: number | null;
  scrap_percentage?: number;
  metal_type?: string | null;
}

interface CostBreakdownCardProps {
  order: OrderCostData;
  onEdit?: () => void;
}

const DEFAULT_HOURLY_RATE = 75;
const DEFAULT_PROFIT_MARGIN = 40;
const DEFAULT_VAT_RATE = 19;
const DEFAULT_SCRAP_PERCENT = 5;
const PRICE_TOLERANCE = 0.01;

interface CostLineProps {
  label: string;
  value: React.ReactNode;
  emphasis?: 'total' | 'muted';
}

function CostLine({ label, value, emphasis }: CostLineProps) {
  const className = emphasis ? `cost-summary__line cost-summary__line--${emphasis}` : 'cost-summary__line';
  return (
    <div className={className}>
      <dt>{label}</dt>
      <dd className={MONEY_CLASS}>{value}</dd>
    </div>
  );
}

function formatWeight(grams: number): string {
  return `${grams.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} g`;
}

export const CostBreakdownCard: React.FC<CostBreakdownCardProps> = ({ order, onEdit }) => {
  const hasCostData =
    order.material_cost_calculated ||
    order.material_cost_override ||
    order.labor_cost ||
    order.calculated_price;

  if (!hasCostData) {
    return (
      <Card title="Kostenaufstellung" headingLevel={3}>
        <EmptyState
          icon="calculator"
          title="Kosten noch nicht berechnet"
          body="Kosten werden automatisch berechnet, wenn Metall und Arbeitsstunden angegeben sind."
          headingLevel={3}
          action={
            onEdit ? (
              <Button variant="secondary" icon="pencil" onClick={onEdit}>
                Kosten bearbeiten
              </Button>
            ) : undefined
          }
        />
      </Card>
    );
  }

  const hourlyRate = order.hourly_rate ?? DEFAULT_HOURLY_RATE;
  const materialCost = order.material_cost_override ?? order.material_cost_calculated ?? 0;
  const laborCost = order.labor_cost ?? (order.labor_hours ?? 0) * hourlyRate;
  const subtotal = materialCost + laborCost;
  const profitMargin = order.profit_margin_percent ?? DEFAULT_PROFIT_MARGIN;
  const profitAmount = subtotal * (profitMargin / 100);
  const preTaxTotal = subtotal + profitAmount;
  const vatRate = order.vat_rate ?? DEFAULT_VAT_RATE;
  const vatAmount = preTaxTotal * (vatRate / 100);
  const finalPrice = preTaxTotal + vatAmount;

  const estimatedWeight = order.estimated_weight_g ?? 0;
  const scrapPercent = order.scrap_percentage ?? DEFAULT_SCRAP_PERCENT;
  const totalWeight = estimatedWeight + estimatedWeight * (scrapPercent / 100);

  const hasLaborHours = order.labor_hours !== null && order.labor_hours !== undefined;
  const hasManualPrice =
    Boolean(order.price) && Math.abs((order.price ?? 0) - finalPrice) > PRICE_TOLERANCE;

  return (
    <Card
      title="Kostenaufstellung"
      headingLevel={3}
      className="cost-summary"
      action={
        onEdit ? (
          <Button variant="secondary" icon="pencil" onClick={onEdit}>
            Kosten bearbeiten
          </Button>
        ) : undefined
      }
    >
      <section className="cost-summary__group" aria-labelledby="cost-summary-material">
        <h4 id="cost-summary-material" className="cost-summary__heading">
          Materialkosten
        </h4>
        {order.material_cost_override ? (
          <p className="cost-summary__note">Manuell überschrieben</p>
        ) : null}
        <dl>
          <CostLine label="Materialkosten" value={formatEur(materialCost)} />
        </dl>
        {order.metal_type && estimatedWeight > 0 && (
          <p className="cost-summary__note">
            {formatWeight(totalWeight)} inkl. {scrapPercent} % Verschnitt
          </p>
        )}
      </section>

      <section className="cost-summary__group" aria-labelledby="cost-summary-labor">
        <h4 id="cost-summary-labor" className="cost-summary__heading">
          Arbeitskosten
        </h4>
        <dl>
          {hasLaborHours ? (
            <>
              <CostLine
                label="Arbeitsstunden"
                value={`${order.labor_hours} h × ${formatEur(hourlyRate)}/h`}
              />
              <CostLine label="Arbeitskosten" value={formatEur(laborCost)} />
            </>
          ) : (
            <CostLine label="Arbeitskosten" value="Nicht angegeben" emphasis="muted" />
          )}
        </dl>
      </section>

      <section className="cost-summary__group" aria-label="Zwischensumme und Marge">
        <dl>
          <CostLine label="Zwischensumme" value={formatEur(subtotal)} />
          <CostLine label={`Gewinnmarge (${profitMargin} %)`} value={formatEur(profitAmount)} />
        </dl>
      </section>

      <section className="cost-summary__group" aria-label="Summe mit MwSt.">
        <dl>
          <CostLine label="Summe vor MwSt." value={formatEur(preTaxTotal)} />
          <CostLine label={`MwSt. (${vatRate} %)`} value={formatEur(vatAmount)} />
          <CostLine label="Endpreis (kalkuliert)" value={formatEur(finalPrice)} emphasis="total" />
          {hasManualPrice && (
            <CostLine label="Manueller Preis" value={formatEur(order.price)} emphasis="total" />
          )}
        </dl>
        {hasManualPrice && (
          <p className="cost-summary__note cost-summary__note--warning">
            Abweichung vom kalkulierten Preis:{' '}
            <span className={MONEY_CLASS}>{formatEur((order.price ?? 0) - finalPrice)}</span>
          </p>
        )}
      </section>
    </Card>
  );
};
