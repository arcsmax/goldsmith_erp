// ConsumeMetalModal.tsx
// Modal for recording material consumption against an order.
// Supports FIFO, LIFO, AVERAGE and SPECIFIC costing methods.
// A preview call shows cost breakdown before the user commits.
import React, { useEffect, useState, useCallback } from 'react';
import { metalInventoryApi } from '../../api';
import { ordersApi } from '../../api';
import {
  MetalType,
  CostingMethod,
  OrderType,
  MetalPurchaseListItem,
  OrderMaterialAllocation,
} from '../../types';

interface ConsumeMetalModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const METAL_TYPE_OPTIONS: { value: MetalType; label: string }[] = [
  { value: 'gold_24k', label: 'Gold 24K (999.9)' },
  { value: 'gold_22k', label: 'Gold 22K (916)' },
  { value: 'gold_18k', label: 'Gold 18K (750)' },
  { value: 'gold_14k', label: 'Gold 14K (585)' },
  { value: 'gold_9k', label: 'Gold 9K (375)' },
  { value: 'silver_999', label: 'Silber 999' },
  { value: 'silver_925', label: 'Silber 925 (Sterling)' },
  { value: 'silver_800', label: 'Silber 800' },
  { value: 'platinum_950', label: 'Platin 950' },
  { value: 'platinum_900', label: 'Platin 900' },
  { value: 'palladium', label: 'Palladium' },
  { value: 'white_gold_18k', label: 'Weißgold 18K' },
  { value: 'white_gold_14k', label: 'Weißgold 14K' },
  { value: 'rose_gold_18k', label: 'Rotgold 18K' },
  { value: 'rose_gold_14k', label: 'Rotgold 14K' },
];

const COSTING_METHODS: { value: CostingMethod; label: string; description: string }[] = [
  { value: 'fifo', label: 'FIFO', description: 'Älteste Charge zuerst' },
  { value: 'lifo', label: 'LIFO', description: 'Neueste Charge zuerst' },
  { value: 'average', label: 'Durchschnitt', description: 'Gewichteter Durchschnittspreis' },
  { value: 'specific', label: 'Spezifisch', description: 'Bestimmte Charge auswählen' },
];

const formatCurrency = (amount: number): string =>
  new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(amount);

const formatWeight = (g: number): string => `${g.toFixed(3)} g`;

export const ConsumeMetalModal: React.FC<ConsumeMetalModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  // Form state
  const [orderId, setOrderId] = useState<number | ''>('');
  const [metalType, setMetalType] = useState<MetalType | ''>('');
  const [weightG, setWeightG] = useState('');
  const [costingMethod, setCostingMethod] = useState<CostingMethod>('fifo');
  const [specificPurchaseId, setSpecificPurchaseId] = useState<number | ''>('');
  const [notes, setNotes] = useState('');

  // Remote data
  const [inProgressOrders, setInProgressOrders] = useState<OrderType[]>([]);
  const [availableBatches, setAvailableBatches] = useState<MetalPurchaseListItem[]>([]);

  // UI state
  const [isLoadingOrders, setIsLoadingOrders] = useState(false);
  const [isLoadingBatches, setIsLoadingBatches] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [preview, setPreview] = useState<OrderMaterialAllocation | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Load in-progress orders once when modal opens
  useEffect(() => {
    if (!isOpen) return;
    resetForm();
    loadOrders();
  }, [isOpen]);

  // Load available batches whenever metal type changes
  useEffect(() => {
    if (!metalType) {
      setAvailableBatches([]);
      setSpecificPurchaseId('');
      return;
    }
    loadBatches(metalType);
  }, [metalType]);

  // Clear preview whenever key inputs change
  useEffect(() => {
    setPreview(null);
    setPreviewError(null);
  }, [orderId, metalType, weightG, costingMethod, specificPurchaseId]);

  const resetForm = () => {
    setOrderId('');
    setMetalType('');
    setWeightG('');
    setCostingMethod('fifo');
    setSpecificPurchaseId('');
    setNotes('');
    setPreview(null);
    setPreviewError(null);
    setSubmitError(null);
    setAvailableBatches([]);
  };

  const loadOrders = async () => {
    try {
      setIsLoadingOrders(true);
      // Fetch generously — filter client-side for in_progress
      const all = await ordersApi.getAll({ limit: 500 });
      const active = all.filter(
        (o) =>
          o.status === 'in_progress' ||
          o.status === 'confirmed' ||
          o.status === 'new' ||
          o.status === 'draft' ||
          o.status === 'waiting_for_fitting' ||
          o.status === 'fitting_done' ||
          o.status === 'ready_for_setting' ||
          o.status === 'quality_check'
      );
      setInProgressOrders(active);
    } catch {
      // Non-blocking — user can still type the order id
    } finally {
      setIsLoadingOrders(false);
    }
  };

  const loadBatches = async (type: MetalType) => {
    try {
      setIsLoadingBatches(true);
      const batches = await metalInventoryApi.listPurchases({
        metal_type: type,
        include_depleted: false,
      });
      setAvailableBatches(batches);
    } catch {
      setAvailableBatches([]);
    } finally {
      setIsLoadingBatches(false);
    }
  };

  const isFormValid = (): boolean => {
    if (!orderId || !metalType || !weightG) return false;
    const w = parseFloat(weightG);
    if (isNaN(w) || w <= 0) return false;
    if (costingMethod === 'specific' && !specificPurchaseId) return false;
    return true;
  };

  const handlePreview = useCallback(async () => {
    if (!isFormValid() || !metalType) return;
    const w = parseFloat(weightG);
    setIsPreviewLoading(true);
    setPreviewError(null);
    setPreview(null);
    try {
      const result = await metalInventoryApi.previewAllocation({
        metal_type: metalType,
        required_weight_g: w,
        costing_method: costingMethod,
        specific_purchase_id:
          costingMethod === 'specific' && specificPurchaseId
            ? Number(specificPurchaseId)
            : undefined,
      });
      // Inject order_id into the preview result (backend returns a placeholder)
      setPreview({ ...result, order_id: Number(orderId) });
    } catch (err: any) {
      setPreviewError(
        err.response?.data?.detail || 'Vorschau konnte nicht geladen werden.'
      );
    } finally {
      setIsPreviewLoading(false);
    }
  }, [orderId, metalType, weightG, costingMethod, specificPurchaseId]);

  const handleSubmit = async () => {
    if (!isFormValid() || !metalType) return;
    const w = parseFloat(weightG);
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await metalInventoryApi.consumeMaterial(
        {
          order_id: Number(orderId),
          weight_used_g: w,
          costing_method: costingMethod,
          metal_purchase_id:
            costingMethod === 'specific' && specificPurchaseId
              ? Number(specificPurchaseId)
              : undefined,
          notes: notes.trim() || undefined,
        },
        metalType
      );
      onSuccess();
      onClose();
    } catch (err: any) {
      setSubmitError(
        err.response?.data?.detail || 'Verbrauch konnte nicht gespeichert werden.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Verbrauch erfassen">
      <div className="modal consume-metal-modal">
        <div className="modal-header">
          <h2>Verbrauch erfassen</h2>
          <button
            className="modal-close"
            onClick={onClose}
            aria-label="Schließen"
            disabled={isSubmitting}
          >
            &times;
          </button>
        </div>

        <div className="modal-body">
          {/* Order selector */}
          <div className="form-group">
            <label htmlFor="consume-order">Auftrag *</label>
            <select
              id="consume-order"
              value={orderId}
              onChange={(e) => setOrderId(e.target.value ? Number(e.target.value) : '')}
              disabled={isLoadingOrders || isSubmitting}
            >
              <option value="">
                {isLoadingOrders ? 'Lade Aufträge...' : '-- Auftrag auswählen --'}
              </option>
              {inProgressOrders.map((o) => (
                <option key={o.id} value={o.id}>
                  #{o.id} – {o.title} ({o.status})
                </option>
              ))}
            </select>
          </div>

          {/* Metal type */}
          <div className="form-group">
            <label htmlFor="consume-metal-type">Metalltyp *</label>
            <select
              id="consume-metal-type"
              value={metalType}
              onChange={(e) => setMetalType(e.target.value as MetalType | '')}
              disabled={isSubmitting}
            >
              <option value="">-- Metalltyp auswählen --</option>
              {METAL_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Weight */}
          <div className="form-group">
            <label htmlFor="consume-weight">Gewicht (g) *</label>
            <input
              id="consume-weight"
              type="number"
              min="0.001"
              max="1000"
              step="0.001"
              value={weightG}
              onChange={(e) => setWeightG(e.target.value)}
              placeholder="z.B. 4.2"
              disabled={isSubmitting}
            />
          </div>

          {/* Costing method */}
          <div className="form-group">
            <label>Bewertungsmethode *</label>
            <div className="costing-method-grid">
              {COSTING_METHODS.map((m) => (
                <label
                  key={m.value}
                  className={`costing-method-option ${costingMethod === m.value ? 'selected' : ''}`}
                >
                  <input
                    type="radio"
                    name="costing-method"
                    value={m.value}
                    checked={costingMethod === m.value}
                    onChange={() => setCostingMethod(m.value)}
                    disabled={isSubmitting}
                  />
                  <span className="costing-method-label">{m.label}</span>
                  <span className="costing-method-desc">{m.description}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Batch selector — only shown for SPECIFIC method */}
          {costingMethod === 'specific' && (
            <div className="form-group">
              <label htmlFor="consume-batch">Charge *</label>
              {!metalType ? (
                <p className="field-hint">Bitte zuerst Metalltyp auswählen.</p>
              ) : isLoadingBatches ? (
                <p className="field-hint">Lade Chargen...</p>
              ) : availableBatches.length === 0 ? (
                <p className="field-hint warning">Keine aktiven Chargen für diesen Metalltyp.</p>
              ) : (
                <select
                  id="consume-batch"
                  value={specificPurchaseId}
                  onChange={(e) =>
                    setSpecificPurchaseId(e.target.value ? Number(e.target.value) : '')
                  }
                  disabled={isSubmitting}
                >
                  <option value="">-- Charge auswählen --</option>
                  {availableBatches.map((b) => (
                    <option key={b.id} value={b.id}>
                      #{b.id} – {b.supplier ?? 'Unbekannt'} –{' '}
                      {b.remaining_weight_g.toFixed(2)} g verbleibend @{' '}
                      {formatCurrency(b.price_per_gram)}/g
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          {/* Notes */}
          <div className="form-group">
            <label htmlFor="consume-notes">Notiz</label>
            <textarea
              id="consume-notes"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="z.B. Ringfertigung – Kundenwunsch Rotgold"
              disabled={isSubmitting}
            />
          </div>

          {/* Preview section */}
          {previewError && (
            <div className="consume-error" role="alert">
              {previewError}
            </div>
          )}

          {preview && (
            <div className="consume-preview" role="region" aria-label="Kostenvorschau">
              <h4>Kostenvorschau</h4>
              <table className="preview-table">
                <thead>
                  <tr>
                    <th>Charge</th>
                    <th>Gewicht</th>
                    <th>Preis/g</th>
                    <th>Kosten</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.allocations.map((alloc) => (
                    <tr key={alloc.metal_purchase_id}>
                      <td>#{alloc.metal_purchase_id}</td>
                      <td>{formatWeight(alloc.weight_allocated_g)}</td>
                      <td>{formatCurrency(alloc.price_per_gram)}/g</td>
                      <td>{formatCurrency(alloc.cost)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={2}>
                      <strong>Gesamt ({preview.costing_method.toUpperCase()})</strong>
                    </td>
                    <td>{formatWeight(preview.required_weight_g)}</td>
                    <td>
                      <strong>{formatCurrency(preview.total_cost)}</strong>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}

          {submitError && (
            <div className="consume-error" role="alert">
              {submitError}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button
            type="button"
            className="btn-secondary"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Abbrechen
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={handlePreview}
            disabled={!isFormValid() || isPreviewLoading || isSubmitting}
          >
            {isPreviewLoading ? 'Lade...' : 'Vorschau'}
          </button>

          <button
            type="button"
            className="btn-primary"
            onClick={handleSubmit}
            disabled={!isFormValid() || isSubmitting}
          >
            {isSubmitting ? 'Speichern...' : 'Verbrauch buchen'}
          </button>
        </div>
      </div>
    </div>
  );
};
