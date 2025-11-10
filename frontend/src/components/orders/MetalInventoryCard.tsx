// MetalInventoryCard - Display metal inventory information for orders
import React from 'react';

type MetalType =
  | 'gold_24k'
  | 'gold_18k'
  | 'gold_14k'
  | 'silver_925'
  | 'silver_999'
  | 'platinum';

type CostingMethod = 'FIFO' | 'LIFO' | 'AVERAGE' | 'SPECIFIC';

interface OrderMetalData {
  // Metal Inventory
  metal_type?: MetalType | null;
  estimated_weight_g?: number | null;
  actual_weight_g?: number | null;
  scrap_percentage?: number;
  costing_method_used?: CostingMethod;
  specific_metal_purchase_id?: number | null;

  // For status check
  status?: string;
}

interface MetalInventoryCardProps {
  order: OrderMetalData;
}

// Metal type display configuration
const METAL_TYPE_CONFIG: Record<
  MetalType,
  { label: string; icon: string; className: string }
> = {
  gold_24k: { label: 'Gold 24K (999)', icon: '🥇', className: 'metal-gold-24k' },
  gold_18k: { label: 'Gold 18K (750)', icon: '🥇', className: 'metal-gold-18k' },
  gold_14k: { label: 'Gold 14K (585)', icon: '🥇', className: 'metal-gold-14k' },
  silver_925: { label: 'Silber 925', icon: '⚪', className: 'metal-silver-925' },
  silver_999: { label: 'Silber 999', icon: '⚪', className: 'metal-silver-999' },
  platinum: { label: 'Platin', icon: '◻️', className: 'metal-platinum' },
};

// Costing method descriptions
const COSTING_METHOD_DESC: Record<CostingMethod, string> = {
  FIFO: 'First In, First Out - Älteste Charge zuerst',
  LIFO: 'Last In, First Out - Neueste Charge zuerst',
  AVERAGE: 'Durchschnittspreis aller Chargen',
  SPECIFIC: 'Spezifische Charge ausgewählt',
};

export const MetalInventoryCard: React.FC<MetalInventoryCardProps> = ({ order }) => {
  // If no metal type, don't render anything
  if (!order.metal_type) {
    return null;
  }

  const metalConfig = METAL_TYPE_CONFIG[order.metal_type];
  const estimatedWeight = order.estimated_weight_g ?? 0;
  const scrapPercent = order.scrap_percentage ?? 5;
  const scrapWeight = estimatedWeight * (scrapPercent / 100);
  const totalWeight = estimatedWeight + scrapWeight;
  const actualWeight = order.actual_weight_g;
  const costingMethod = order.costing_method_used ?? 'FIFO';

  // Check if order is completed (has actual weight)
  const isCompleted =
    order.status === 'completed' || order.status === 'delivered' || actualWeight;

  // Format weight
  const formatWeight = (grams: number): string => {
    return `${grams.toFixed(1)}g`;
  };

  return (
    <div className="metal-inventory-card">
      {/* Metal Type */}
      <section className="metal-section">
        <h3>Metallart</h3>
        <div className={`metal-type-badge ${metalConfig.className}`}>
          <span className="metal-icon">{metalConfig.icon}</span>
          <span className="metal-label">{metalConfig.label}</span>
        </div>
      </section>

      {/* Weight Information */}
      <section className="metal-section">
        <h3>Gewicht</h3>
        <div className="metal-weight-grid">
          <div className="metal-line">
            <span className="metal-label">Geschätztes Gewicht:</span>
            <span className="metal-value">{formatWeight(estimatedWeight)}</span>
          </div>
          <div className="metal-line">
            <span className="metal-label">Verschnitt ({scrapPercent}%):</span>
            <span className="metal-value scrap">+{formatWeight(scrapWeight)}</span>
          </div>
          <div className="metal-line total">
            <span className="metal-label">Gesamtbedarf:</span>
            <span className="metal-value total-weight">{formatWeight(totalWeight)}</span>
          </div>

          {isCompleted && actualWeight && (
            <div className="metal-line actual">
              <span className="metal-label">Tatsächliches Gewicht:</span>
              <span className="metal-value actual-weight">
                {formatWeight(actualWeight)}
              </span>
            </div>
          )}

          {isCompleted && actualWeight && actualWeight !== estimatedWeight && (
            <div className="metal-line difference">
              <span className="metal-label">Abweichung:</span>
              <span
                className={`metal-value ${
                  actualWeight > estimatedWeight ? 'over' : 'under'
                }`}
              >
                {actualWeight > estimatedWeight ? '+' : ''}
                {formatWeight(actualWeight - estimatedWeight)}
              </span>
            </div>
          )}
        </div>
      </section>

      {/* Costing Method */}
      <section className="metal-section">
        <h3>Kalkulationsmethode</h3>
        <div className="costing-method">
          <div className="metal-line">
            <span className="metal-label">Methode:</span>
            <span className="metal-value method">{costingMethod}</span>
          </div>
          <div className="costing-description">{COSTING_METHOD_DESC[costingMethod]}</div>

          {order.specific_metal_purchase_id && costingMethod === 'SPECIFIC' ? (
            <div className="metal-batch-info">
              <span className="metal-label">Verwendete Charge:</span>
              <a
                href={`/metal-inventory/${order.specific_metal_purchase_id}`}
                className="batch-link"
              >
                #{order.specific_metal_purchase_id}
              </a>
            </div>
          ) : (
            <div className="metal-line">
              <span className="metal-label">Zuweisung:</span>
              <span className="metal-value">Automatisch</span>
            </div>
          )}
        </div>
      </section>

      {/* Link to Metal Inventory */}
      <section className="metal-section">
        <button
          className="btn-link-metal"
          onClick={() => (window.location.href = '/metal-inventory')}
        >
          🔗 Zum Metallinventar
        </button>
      </section>
    </div>
  );
};
