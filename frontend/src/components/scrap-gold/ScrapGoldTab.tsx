// Scrap Gold Tab - Main component for Altgold management in order detail
import React, { useState, useEffect, useCallback } from 'react';
import { scrapGoldApi, ScrapGold, ScrapGoldStatus } from '../../api/scrap-gold';
import { AlloyCalculator, ALLOY_OPTIONS } from './AlloyCalculator';
import '../../styles/scrap-gold.css';

interface ScrapGoldTabProps {
  orderId: number;
  customerId: number;
}

const STATUS_CONFIG: Record<ScrapGoldStatus, { label: string; className: string }> = {
  received: { label: 'Empfangen', className: 'status-received' },
  calculated: { label: 'Berechnet', className: 'status-calculated' },
  signed: { label: 'Unterschrieben', className: 'status-signed' },
  settled: { label: 'Verrechnet', className: 'status-settled' },
};

/**
 * Formats alloy number to human-readable label
 */
const getAlloyLabel = (alloy: number): string => {
  const option = ALLOY_OPTIONS.find((o) => o.value === alloy);
  return option ? option.label : `${alloy}`;
};

export const ScrapGoldTab: React.FC<ScrapGoldTabProps> = ({ orderId, customerId }) => {
  const [scrapGold, setScrapGold] = useState<ScrapGold | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isCalculating, setIsCalculating] = useState(false);
  const [goldPriceInput, setGoldPriceInput] = useState<string>('');

  const loadScrapGold = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await scrapGoldApi.getForOrder(orderId);
      setScrapGold(data);
      if (data && data.gold_price_per_g > 0) {
        setGoldPriceInput(data.gold_price_per_g.toFixed(2));
      }
    } catch (err) {
      console.error('Failed to load scrap gold:', err);
      setError('Altgold-Daten konnten nicht geladen werden');
    } finally {
      setIsLoading(false);
    }
  }, [orderId]);

  useEffect(() => {
    loadScrapGold();
  }, [loadScrapGold]);

  const handleCreate = async () => {
    try {
      setIsCreating(true);
      const created = await scrapGoldApi.create(orderId);
      setScrapGold(created);
    } catch (err) {
      console.error('Failed to create scrap gold:', err);
      alert('Altgold-Eintrag konnte nicht erstellt werden.');
    } finally {
      setIsCreating(false);
    }
  };

  const handleAddItem = async (description: string, alloy: number, weightG: number) => {
    if (!scrapGold) return;

    try {
      await scrapGoldApi.addItem(scrapGold.id, { description, alloy, weight_g: weightG });
      await loadScrapGold();
    } catch (err) {
      console.error('Failed to add item:', err);
      alert('Position konnte nicht hinzugefuegt werden.');
    }
  };

  const handleRemoveItem = async (itemId: number) => {
    if (!scrapGold) return;

    try {
      await scrapGoldApi.removeItem(scrapGold.id, itemId);
      await loadScrapGold();
    } catch (err) {
      console.error('Failed to remove item:', err);
      alert('Position konnte nicht entfernt werden.');
    }
  };

  const handleCalculate = async () => {
    if (!scrapGold) return;

    try {
      setIsCalculating(true);
      const updated = await scrapGoldApi.calculate(scrapGold.id);
      setScrapGold(updated);
      if (updated.gold_price_per_g > 0) {
        setGoldPriceInput(updated.gold_price_per_g.toFixed(2));
      }
    } catch (err) {
      console.error('Failed to calculate:', err);
      alert('Berechnung fehlgeschlagen.');
    } finally {
      setIsCalculating(false);
    }
  };

  const handleSign = async () => {
    if (!scrapGold) return;

    // Placeholder: In a real implementation, this would capture a signature via canvas
    const signatureData = `signed_by_customer_${customerId}_at_${new Date().toISOString()}`;

    try {
      const updated = await scrapGoldApi.sign(scrapGold.id, signatureData);
      setScrapGold(updated);
    } catch (err) {
      console.error('Failed to sign:', err);
      alert('Unterschrift konnte nicht gespeichert werden.');
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="scrap-gold-tab">
        <div className="scrap-gold-loading">
          <p>Altgold-Daten werden geladen...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="scrap-gold-tab">
        <div className="scrap-gold-error">
          <p>{error}</p>
          <button className="btn-retry" onClick={loadScrapGold}>
            Erneut versuchen
          </button>
        </div>
      </div>
    );
  }

  // No scrap gold yet - show prompt
  if (!scrapGold) {
    return (
      <div className="scrap-gold-tab">
        <div className="scrap-gold-prompt">
          <div className="prompt-icon">&#x1F947;</div>
          <h2>Altgold vorhanden?</h2>
          <p>Hat der Kunde Altgold zur Verrechnung mitgebracht?</p>
          <div className="prompt-actions">
            <button
              className="btn-prompt-yes"
              onClick={handleCreate}
              disabled={isCreating}
            >
              {isCreating ? 'Wird erstellt...' : 'Ja, Altgold erfassen'}
            </button>
            <button className="btn-prompt-no" disabled>
              Nein
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Scrap gold exists - show full interface
  const statusConfig = STATUS_CONFIG[scrapGold.status] || STATUS_CONFIG.received;
  const isEditable = scrapGold.status === 'received' || scrapGold.status === 'calculated';

  return (
    <div className="scrap-gold-tab">
      {/* Header with status */}
      <div className="scrap-gold-header">
        <h2>Altgold</h2>
        <span className={`scrap-gold-status-badge ${statusConfig.className}`}>
          {statusConfig.label}
        </span>
      </div>

      {/* Alloy Calculator */}
      {isEditable && (
        <AlloyCalculator onAddItem={handleAddItem} isDisabled={!isEditable} />
      )}

      {/* Items List */}
      <div className="scrap-gold-items-section">
        <h3>Positionen ({scrapGold.items.length})</h3>
        {scrapGold.items.length === 0 ? (
          <p className="scrap-gold-empty">
            Noch keine Positionen erfasst. Verwenden Sie den Rechner oben, um Altgold hinzuzufuegen.
          </p>
        ) : (
          <table className="scrap-gold-items-table">
            <thead>
              <tr>
                <th>Beschreibung</th>
                <th>Legierung</th>
                <th>Gewicht (g)</th>
                <th>Feingehalt (g)</th>
                {isEditable && <th>Aktion</th>}
              </tr>
            </thead>
            <tbody>
              {scrapGold.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.description}</td>
                  <td>{getAlloyLabel(item.alloy)}</td>
                  <td className="text-right">{item.weight_g.toFixed(2)}</td>
                  <td className="text-right">{item.fine_content_g.toFixed(3)}</td>
                  {isEditable && (
                    <td>
                      <button
                        className="btn-remove-item"
                        onClick={() => handleRemoveItem(item.id)}
                        title="Position entfernen"
                      >
                        Entfernen
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Summary Section */}
      <div className="scrap-gold-summary">
        <h3>Zusammenfassung</h3>

        <div className="summary-grid">
          <div className="summary-item">
            <span className="summary-label">Gesamt Feingold</span>
            <span className="summary-value highlight">
              {scrapGold.total_fine_gold_g.toFixed(3)} g
            </span>
          </div>

          <div className="summary-item">
            <span className="summary-label">Goldpreis / g</span>
            <div className="summary-input-group">
              <input
                type="number"
                step="0.01"
                min="0"
                value={goldPriceInput}
                onChange={(e) => setGoldPriceInput(e.target.value)}
                placeholder="0.00"
                disabled={!isEditable}
                className="summary-price-input"
              />
              <span className="summary-currency">EUR</span>
            </div>
          </div>

          <div className="summary-item total">
            <span className="summary-label">Gesamtwert</span>
            <span className="summary-value total-value">
              {scrapGold.total_value_eur.toFixed(2)} EUR
            </span>
          </div>

          {scrapGold.price_source && (
            <div className="summary-item source">
              <span className="summary-label">Preisquelle</span>
              <span className="summary-value">{scrapGold.price_source}</span>
            </div>
          )}
        </div>

        {/* Calculate Button */}
        {isEditable && scrapGold.items.length > 0 && (
          <button
            className="btn-calculate"
            onClick={handleCalculate}
            disabled={isCalculating}
          >
            {isCalculating ? 'Wird berechnet...' : 'Berechnen'}
          </button>
        )}
      </div>

      {/* Signature Section */}
      <div className="scrap-gold-signature">
        <h3>Unterschrift</h3>

        {scrapGold.signed_at ? (
          <div className="signature-done">
            <span className="signature-checkmark">&#x2714;</span>
            <p>
              Unterschrieben am{' '}
              {new Date(scrapGold.signed_at).toLocaleString('de-DE')}
            </p>
          </div>
        ) : (
          <div className="signature-pending">
            <div className="signature-area">
              <p>Unterschrift des Kunden</p>
            </div>
            <button
              className="btn-sign"
              onClick={handleSign}
              disabled={scrapGold.status === 'received' && scrapGold.items.length === 0}
            >
              Unterschrift erfassen
            </button>
          </div>
        )}
      </div>

      {/* Notes */}
      {scrapGold.notes && (
        <div className="scrap-gold-notes">
          <h3>Notizen</h3>
          <p>{scrapGold.notes}</p>
        </div>
      )}
    </div>
  );
};
