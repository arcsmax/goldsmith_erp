// Metal Purchase Form Modal Component
import React, { useState, useEffect } from 'react';
import {
  MetalPurchaseType,
  MetalPurchaseCreateInput,
  MetalPurchaseUpdateInput,
  MetalType,
} from '../../types';
import '../../styles/metal-inventory.css';

interface MetalPurchaseFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: MetalPurchaseCreateInput | MetalPurchaseUpdateInput) => Promise<void>;
  purchase?: MetalPurchaseType | null;
  isLoading?: boolean;
}

interface FormData {
  date_purchased: string;
  metal_type: MetalType | '';
  weight_g: string;
  price_total: string;
  supplier: string;
  invoice_number: string;
  notes: string;
  lot_number: string;
}

interface FormErrors {
  metal_type?: string;
  weight_g?: string;
  price_total?: string;
}

const METAL_TYPE_OPTIONS: { value: MetalType; label: string; category: string }[] = [
  // Gold
  { value: 'gold_24k', label: 'Gold 24K (999.9)', category: 'Gold' },
  { value: 'gold_22k', label: 'Gold 22K (916)', category: 'Gold' },
  { value: 'gold_18k', label: 'Gold 18K (750)', category: 'Gold' },
  { value: 'gold_14k', label: 'Gold 14K (585)', category: 'Gold' },
  { value: 'gold_9k', label: 'Gold 9K (375)', category: 'Gold' },
  // Silver
  { value: 'silver_999', label: 'Silber 999 (Feinsilber)', category: 'Silber' },
  { value: 'silver_925', label: 'Silber 925 (Sterling)', category: 'Silber' },
  { value: 'silver_800', label: 'Silber 800 (Altsilber)', category: 'Silber' },
  // Platinum & Palladium
  { value: 'platinum_950', label: 'Platin 950', category: 'Platin' },
  { value: 'platinum_900', label: 'Platin 900', category: 'Platin' },
  { value: 'palladium', label: 'Palladium 999', category: 'Palladium' },
  // White Gold
  { value: 'white_gold_18k', label: 'Weißgold 18K (750)', category: 'Weißgold' },
  { value: 'white_gold_14k', label: 'Weißgold 14K (585)', category: 'Weißgold' },
  // Rose Gold
  { value: 'rose_gold_18k', label: 'Rotgold 18K (750)', category: 'Rotgold' },
  { value: 'rose_gold_14k', label: 'Rotgold 14K (585)', category: 'Rotgold' },
];

export const MetalPurchaseFormModal: React.FC<MetalPurchaseFormModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  purchase,
  isLoading = false,
}) => {
  const isEditMode = Boolean(purchase);

  const [formData, setFormData] = useState<FormData>({
    date_purchased: new Date().toISOString().split('T')[0],
    metal_type: '',
    weight_g: '',
    price_total: '',
    supplier: '',
    invoice_number: '',
    notes: '',
    lot_number: '',
  });

  const [errors, setErrors] = useState<FormErrors>({});
  const [autoGenerateLotNumber, setAutoGenerateLotNumber] = useState(true);

  useEffect(() => {
    if (isOpen) {
      if (purchase) {
        // Edit mode: populate form with purchase data
        setFormData({
          date_purchased: purchase.date_purchased
            ? new Date(purchase.date_purchased).toISOString().split('T')[0]
            : new Date().toISOString().split('T')[0],
          metal_type: purchase.metal_type,
          weight_g: purchase.weight_g.toString(),
          price_total: purchase.price_total.toString(),
          supplier: purchase.supplier || '',
          invoice_number: purchase.invoice_number || '',
          notes: purchase.notes || '',
          lot_number: purchase.lot_number || '',
        });
        setAutoGenerateLotNumber(false);
      } else {
        // Create mode: reset form
        resetForm();
        setAutoGenerateLotNumber(true);
      }
      setErrors({});
    }
  }, [isOpen, purchase]);

  const resetForm = () => {
    setFormData({
      date_purchased: new Date().toISOString().split('T')[0],
      metal_type: '',
      weight_g: '',
      price_total: '',
      supplier: '',
      invoice_number: '',
      notes: '',
      lot_number: '',
    });
  };

  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));

    // Clear error for this field
    if (errors[name as keyof FormErrors]) {
      setErrors((prev) => ({ ...prev, [name]: undefined }));
    }

    // Auto-generate lot number when metal_type or date changes
    if (autoGenerateLotNumber && (name === 'metal_type' || name === 'date_purchased')) {
      const updatedData = { ...formData, [name]: value };
      if (updatedData.metal_type && updatedData.date_purchased) {
        const lotNumber = generateLotNumber(
          updatedData.metal_type as MetalType,
          updatedData.date_purchased
        );
        setFormData((prev) => ({ ...prev, [name]: value, lot_number: lotNumber }));
      }
    }
  };

  const generateLotNumber = (metalType: MetalType, date: string): string => {
    const dateObj = new Date(date);
    const year = dateObj.getFullYear().toString().slice(-2);
    const month = (dateObj.getMonth() + 1).toString().padStart(2, '0');
    const day = dateObj.getDate().toString().padStart(2, '0');
    const metalCode = metalType.toUpperCase().replace(/_/g, '-');
    const random = Math.random().toString(36).substring(2, 6).toUpperCase();
    return `${metalCode}-${year}${month}${day}-${random}`;
  };

  const validate = (): boolean => {
    const newErrors: FormErrors = {};

    if (!formData.metal_type) {
      newErrors.metal_type = 'Metalltyp ist erforderlich';
    }

    if (!formData.weight_g || parseFloat(formData.weight_g) <= 0) {
      newErrors.weight_g = 'Gewicht muss größer als 0 sein';
    }

    if (!formData.price_total || parseFloat(formData.price_total) <= 0) {
      newErrors.price_total = 'Preis muss größer als 0 sein';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) return;

    const submitData: MetalPurchaseCreateInput | MetalPurchaseUpdateInput = {
      date_purchased: formData.date_purchased,
      metal_type: formData.metal_type as MetalType,
      weight_g: parseFloat(formData.weight_g),
      price_total: parseFloat(formData.price_total),
      supplier: formData.supplier || undefined,
      invoice_number: formData.invoice_number || undefined,
      notes: formData.notes || undefined,
      lot_number: formData.lot_number || undefined,
    };

    await onSubmit(submitData);
  };

  const calculatePricePerGram = (): number | null => {
    const weight = parseFloat(formData.weight_g);
    const price = parseFloat(formData.price_total);
    if (weight > 0 && price > 0) {
      return price / weight;
    }
    return null;
  };

  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  };

  if (!isOpen) return null;

  const pricePerGram = calculatePricePerGram();

  // Group options by category for better UX
  const groupedOptions = METAL_TYPE_OPTIONS.reduce((acc, option) => {
    if (!acc[option.category]) {
      acc[option.category] = [];
    }
    acc[option.category].push(option);
    return acc;
  }, {} as Record<string, typeof METAL_TYPE_OPTIONS>);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content metal-purchase-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{isEditMode ? 'Metalleinkauf bearbeiten' : 'Neuer Metalleinkauf'}</h2>
          <button className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-form">
          <div className="form-grid">
            {/* Date Purchased */}
            <div className="form-group">
              <label htmlFor="date_purchased">
                Kaufdatum <span className="required">*</span>
              </label>
              <input
                type="date"
                id="date_purchased"
                name="date_purchased"
                value={formData.date_purchased}
                onChange={handleChange}
                required
              />
            </div>

            {/* Metal Type */}
            <div className="form-group">
              <label htmlFor="metal_type">
                Metalltyp <span className="required">*</span>
              </label>
              <select
                id="metal_type"
                name="metal_type"
                value={formData.metal_type}
                onChange={handleChange}
                required
                className={errors.metal_type ? 'error' : ''}
              >
                <option value="">-- Metalltyp wählen --</option>
                {Object.entries(groupedOptions).map(([category, options]) => (
                  <optgroup key={category} label={category}>
                    {options.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {errors.metal_type && <span className="error-text">{errors.metal_type}</span>}
            </div>

            {/* Weight */}
            <div className="form-group">
              <label htmlFor="weight_g">
                Gewicht (g) <span className="required">*</span>
              </label>
              <input
                type="number"
                id="weight_g"
                name="weight_g"
                value={formData.weight_g}
                onChange={handleChange}
                step="0.01"
                min="0"
                placeholder="100.00"
                required
                className={errors.weight_g ? 'error' : ''}
              />
              {errors.weight_g && <span className="error-text">{errors.weight_g}</span>}
            </div>

            {/* Price Total */}
            <div className="form-group">
              <label htmlFor="price_total">
                Gesamtpreis (€) <span className="required">*</span>
              </label>
              <input
                type="number"
                id="price_total"
                name="price_total"
                value={formData.price_total}
                onChange={handleChange}
                step="0.01"
                min="0"
                placeholder="5000.00"
                required
                className={errors.price_total ? 'error' : ''}
              />
              {errors.price_total && <span className="error-text">{errors.price_total}</span>}
            </div>

            {/* Price per Gram (calculated) */}
            {pricePerGram !== null && (
              <div className="form-group calculated-field">
                <label>Preis pro Gramm</label>
                <div className="calculated-value highlight">
                  {formatCurrency(pricePerGram)}
                </div>
              </div>
            )}

            {/* Supplier */}
            <div className="form-group">
              <label htmlFor="supplier">Lieferant</label>
              <input
                type="text"
                id="supplier"
                name="supplier"
                value={formData.supplier}
                onChange={handleChange}
                placeholder="Edelmetall GmbH"
              />
            </div>

            {/* Invoice Number */}
            <div className="form-group">
              <label htmlFor="invoice_number">Rechnungsnummer</label>
              <input
                type="text"
                id="invoice_number"
                name="invoice_number"
                value={formData.invoice_number}
                onChange={handleChange}
                placeholder="RE-2025-12345"
              />
            </div>

            {/* Lot Number */}
            <div className="form-group">
              <label htmlFor="lot_number">
                Chargen-Nummer
                {!isEditMode && (
                  <label className="checkbox-inline">
                    <input
                      type="checkbox"
                      checked={autoGenerateLotNumber}
                      onChange={(e) => setAutoGenerateLotNumber(e.target.checked)}
                    />
                    Automatisch generieren
                  </label>
                )}
              </label>
              <input
                type="text"
                id="lot_number"
                name="lot_number"
                value={formData.lot_number}
                onChange={handleChange}
                disabled={autoGenerateLotNumber && !isEditMode}
                placeholder="GOLD-24K-250115-A3F2"
              />
            </div>
          </div>

          {/* Notes */}
          <div className="form-group full-width">
            <label htmlFor="notes">Notizen</label>
            <textarea
              id="notes"
              name="notes"
              value={formData.notes}
              onChange={handleChange}
              rows={3}
              placeholder="Zusätzliche Informationen..."
            />
          </div>

          {/* Form Actions */}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={isLoading}>
              Abbrechen
            </button>
            <button type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading
                ? 'Wird gespeichert...'
                : isEditMode
                ? 'Speichern'
                : 'Einkauf erstellen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
