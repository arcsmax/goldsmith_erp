// CostBreakdownCard - Display comprehensive cost breakdown for orders
import React from 'react';

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

export const CostBreakdownCard: React.FC<CostBreakdownCardProps> = ({ order, onEdit }) => {
  // Check if any cost data exists
  const hasCostData =
    order.material_cost_calculated ||
    order.material_cost_override ||
    order.labor_cost ||
    order.calculated_price;

  if (!hasCostData) {
    return (
      <div className="cost-breakdown empty">
        <div className="empty-state">
          <p>💰 Kosten noch nicht berechnet</p>
          <p className="empty-hint">
            Kosten werden automatisch berechnet, wenn Metall und Arbeitsstunden angegeben sind.
          </p>
        </div>
      </div>
    );
  }

  // Calculate costs
  const materialCost = order.material_cost_override ?? order.material_cost_calculated ?? 0;
  const laborCost = order.labor_cost ?? (order.labor_hours ?? 0) * (order.hourly_rate ?? 75);
  const subtotal = materialCost + laborCost;
  const profitMargin = order.profit_margin_percent ?? 40;
  const profitAmount = subtotal * (profitMargin / 100);
  const preTaxTotal = subtotal + profitAmount;
  const vatRate = order.vat_rate ?? 19;
  const vatAmount = preTaxTotal * (vatRate / 100);
  const finalPrice = preTaxTotal + vatAmount;

  // Calculate total weight for display
  const estimatedWeight = order.estimated_weight_g ?? 0;
  const scrapPercent = order.scrap_percentage ?? 5;
  const totalWeight = estimatedWeight + estimatedWeight * (scrapPercent / 100);

  // Format currency
  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  };

  // Format weight
  const formatWeight = (grams: number): string => {
    return `${grams.toFixed(1)}g`;
  };

  // Check if there's a price override
  const hasManualPrice = order.price && Math.abs(order.price - finalPrice) > 0.01;

  return (
    <div className="cost-breakdown">
      {/* Material Costs */}
      <section className="cost-section">
        <h3>💎 Materialkosten</h3>
        {order.material_cost_override && (
          <div className="cost-override-badge">✏️ Manuell überschrieben</div>
        )}
        <div className="cost-line">
          <span>Materialkosten:</span>
          <span className="cost-amount">{formatCurrency(materialCost)}</span>
        </div>
        {order.metal_type && estimatedWeight > 0 && (
          <div className="cost-detail">
            ({formatWeight(totalWeight)} inkl. {scrapPercent}% Verschnitt)
          </div>
        )}
      </section>

      {/* Labor Costs */}
      <section className="cost-section">
        <h3>⏱️ Arbeitskosten</h3>
        {order.labor_hours !== null && order.labor_hours !== undefined ? (
          <>
            <div className="cost-line">
              <span>Arbeitsstunden:</span>
              <span>
                {order.labor_hours}h × {formatCurrency(order.hourly_rate ?? 75)}/h
              </span>
            </div>
            <div className="cost-line">
              <span>Arbeitskosten:</span>
              <span className="cost-amount">{formatCurrency(laborCost)}</span>
            </div>
          </>
        ) : (
          <div className="cost-line">
            <span>Arbeitskosten:</span>
            <span className="cost-amount-empty">Nicht angegeben</span>
          </div>
        )}
      </section>

      {/* Subtotal & Profit */}
      <section className="cost-section">
        <div className="cost-line">
          <span>Zwischensumme:</span>
          <span className="cost-amount">{formatCurrency(subtotal)}</span>
        </div>
        <div className="cost-line">
          <span>Gewinnmarge ({profitMargin}%):</span>
          <span className="cost-amount profit">{formatCurrency(profitAmount)}</span>
        </div>
      </section>

      {/* Total with VAT */}
      <section className="cost-section cost-total">
        <div className="cost-line">
          <span>Summe vor MwSt:</span>
          <span className="cost-amount">{formatCurrency(preTaxTotal)}</span>
        </div>
        <div className="cost-line">
          <span>MwSt. ({vatRate}%):</span>
          <span className="cost-amount">{formatCurrency(vatAmount)}</span>
        </div>
        <div className="cost-line cost-final">
          <span>Endpreis (kalkuliert):</span>
          <span className="cost-amount-large">{formatCurrency(finalPrice)}</span>
        </div>

        {hasManualPrice && (
          <div className="cost-manual-price">
            <div className="cost-line">
              <span>Manueller Preis:</span>
              <span className="cost-amount-large manual">
                {formatCurrency(order.price ?? 0)}
              </span>
            </div>
            <div className="cost-override-note">
              ⚠️ Abweichung vom kalkulierten Preis:{' '}
              {formatCurrency((order.price ?? 0) - finalPrice)}
            </div>
          </div>
        )}
      </section>

      {/* Optional Edit Button */}
      {onEdit && (
        <div className="cost-actions">
          <button onClick={onEdit} className="btn-edit-costs">
            ✏️ Kosten bearbeiten
          </button>
        </div>
      )}
    </div>
  );
};
