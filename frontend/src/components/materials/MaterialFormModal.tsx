// Material Form Modal Component
import React, { useState, useEffect } from 'react';
import { MaterialType, MaterialCreateInput, MaterialUpdateInput } from '../../types';
import { MaterialCreateSchema } from '../../lib/validation/schemas';
import { useFormValidation } from '../../lib/validation/useFormValidation';
import '../../styles/materials.css';

interface MaterialFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: MaterialCreateInput | MaterialUpdateInput) => Promise<void>;
  material?: MaterialType | null;
  isLoading?: boolean;
}

const UNIT_OPTIONS = [
  { value: 'Stück', label: 'Stück' },
  { value: 'g', label: 'Gramm (g)' },
  { value: 'kg', label: 'Kilogramm (kg)' },
  { value: 'ml', label: 'Milliliter (ml)' },
  { value: 'l', label: 'Liter (l)' },
  { value: 'cm', label: 'Zentimeter (cm)' },
  { value: 'm', label: 'Meter (m)' },
];

export const MaterialFormModal: React.FC<MaterialFormModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  material,
  isLoading = false,
}) => {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    unit_price: '',
    stock: '',
    unit: 'Stück',
  });

  const { validate: zodValidate, errors, clearError } = useFormValidation(MaterialCreateSchema);

  // Initialize form with material data if editing
  useEffect(() => {
    if (material) {
      setFormData({
        name: material.name,
        description: material.description || '',
        unit_price: material.unit_price.toString(),
        stock: material.stock.toString(),
        unit: material.unit,
      });
    } else {
      setFormData({
        name: '',
        description: '',
        unit_price: '',
        stock: '',
        unit: 'Stück',
      });
    }
  }, [material, isOpen]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    clearError(name);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Coerce string inputs to the expected types before Zod validation
    const parsed = {
      name: formData.name.trim(),
      description: formData.description.trim() || undefined,
      unit_price: parseFloat(formData.unit_price),
      stock: parseFloat(formData.stock),
      unit: formData.unit,
    };

    const result = zodValidate(parsed);
    if (!result.success) {
      return;
    }

    await onSubmit(result.data);
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{material ? 'Material bearbeiten' : 'Neues Material'}</h2>
          <button className="modal-close" onClick={onClose} type="button">
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="material-form">
          <div className="form-body">
            {/* Name */}
            <div className="form-group">
              <label htmlFor="name">
                Name <span className="required">*</span>
              </label>
              <input
                type="text"
                id="name"
                name="name"
                value={formData.name}
                onChange={handleChange}
                className={errors.name ? 'error' : ''}
                placeholder="z.B. Edelstein, Verschluss, Kette"
              />
              {errors.name && <span className="error-message">{errors.name}</span>}
            </div>

            {/* Description */}
            <div className="form-group">
              <label htmlFor="description">Beschreibung</label>
              <textarea
                id="description"
                name="description"
                value={formData.description}
                onChange={handleChange}
                rows={3}
                placeholder="Optionale Beschreibung des Materials"
              />
            </div>

            {/* Unit Price */}
            <div className="form-group">
              <label htmlFor="unit_price">
                Preis pro Einheit (€) <span className="required">*</span>
              </label>
              <input
                type="number"
                id="unit_price"
                name="unit_price"
                value={formData.unit_price}
                onChange={handleChange}
                className={errors.unit_price ? 'error' : ''}
                placeholder="0.00"
                step="0.01"
                min="0"
              />
              {errors.unit_price && (
                <span className="error-message">{errors.unit_price}</span>
              )}
            </div>

            {/* Stock */}
            <div className="form-group">
              <label htmlFor="stock">
                Bestand <span className="required">*</span>
              </label>
              <input
                type="number"
                id="stock"
                name="stock"
                value={formData.stock}
                onChange={handleChange}
                className={errors.stock ? 'error' : ''}
                placeholder="0"
                step="0.01"
                min="0"
              />
              {errors.stock && <span className="error-message">{errors.stock}</span>}
            </div>

            {/* Unit */}
            <div className="form-group">
              <label htmlFor="unit">
                Einheit <span className="required">*</span>
              </label>
              <select
                id="unit"
                name="unit"
                value={formData.unit}
                onChange={handleChange}
                className={errors.unit ? 'error' : ''}
              >
                {UNIT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              {errors.unit && <span className="error-message">{errors.unit}</span>}
            </div>

            {/* Stock Value (calculated, read-only) */}
            {formData.unit_price && formData.stock && (
              <div className="form-group">
                <label>Gesamtwert</label>
                <div className="calculated-value">
                  {(parseFloat(formData.unit_price) * parseFloat(formData.stock)).toFixed(
                    2
                  )}{' '}
                  €
                </div>
              </div>
            )}
          </div>

          <div className="modal-footer">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary"
              disabled={isLoading}
            >
              Abbrechen
            </button>
            <button type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading ? 'Speichern...' : material ? 'Aktualisieren' : 'Erstellen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
