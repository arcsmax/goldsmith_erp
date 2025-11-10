// CustomerFormModal - Modal for creating and editing customers
import React, { useState, useEffect } from 'react';
import { Customer, CustomerCategory, CustomerCreateInput, CustomerUpdateInput } from '../types';
import '../styles/customers.css';

interface CustomerFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CustomerCreateInput | CustomerUpdateInput) => Promise<void>;
  customer?: Customer | null;
  isLoading?: boolean;
}

export const CustomerFormModal: React.FC<CustomerFormModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  customer,
  isLoading = false,
}) => {
  // Form state
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    company_name: '',
    phone: '',
    mobile: '',
    street: '',
    city: '',
    postal_code: '',
    country: 'Deutschland',
    customer_type: 'private' as CustomerCategory,
    source: '',
    notes: '',
    tags: '',
    is_active: true,
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Initialize form data when editing
  useEffect(() => {
    if (customer) {
      setFormData({
        first_name: customer.first_name || '',
        last_name: customer.last_name || '',
        email: customer.email || '',
        company_name: customer.company_name || '',
        phone: customer.phone || '',
        mobile: customer.mobile || '',
        street: customer.street || '',
        city: customer.city || '',
        postal_code: customer.postal_code || '',
        country: customer.country || 'Deutschland',
        customer_type: customer.customer_type || 'private',
        source: customer.source || '',
        notes: customer.notes || '',
        tags: customer.tags?.join(', ') || '',
        is_active: customer.is_active ?? true,
      });
    } else {
      // Reset form for new customer
      setFormData({
        first_name: '',
        last_name: '',
        email: '',
        company_name: '',
        phone: '',
        mobile: '',
        street: '',
        city: '',
        postal_code: '',
        country: 'Deutschland',
        customer_type: 'private',
        source: '',
        notes: '',
        tags: '',
        is_active: true,
      });
    }
    setErrors({});
    setSubmitError(null);
  }, [customer]);

  // Handle input changes
  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    const { name, value, type } = e.target;
    const checked = (e.target as HTMLInputElement).checked;

    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));

    // Clear error for this field
    if (errors[name]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  // Validate form
  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    // Required fields
    if (!formData.first_name.trim()) {
      newErrors.first_name = 'Vorname ist erforderlich';
    }
    if (!formData.last_name.trim()) {
      newErrors.last_name = 'Nachname ist erforderlich';
    }
    if (!formData.email.trim()) {
      newErrors.email = 'E-Mail ist erforderlich';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Ungültige E-Mail-Adresse';
    }

    // Company name required for business customers
    if (formData.customer_type === 'business' && !formData.company_name.trim()) {
      newErrors.company_name = 'Firmenname ist für Geschäftskunden erforderlich';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) {
      return;
    }

    try {
      setSubmitError(null);

      // Prepare data for submission
      const submitData: any = {
        first_name: formData.first_name.trim(),
        last_name: formData.last_name.trim(),
        email: formData.email.trim(),
        customer_type: formData.customer_type,
        country: formData.country,
      };

      // Optional fields
      if (formData.company_name.trim()) {
        submitData.company_name = formData.company_name.trim();
      }
      if (formData.phone.trim()) {
        submitData.phone = formData.phone.trim();
      }
      if (formData.mobile.trim()) {
        submitData.mobile = formData.mobile.trim();
      }
      if (formData.street.trim()) {
        submitData.street = formData.street.trim();
      }
      if (formData.city.trim()) {
        submitData.city = formData.city.trim();
      }
      if (formData.postal_code.trim()) {
        submitData.postal_code = formData.postal_code.trim();
      }
      if (formData.source.trim()) {
        submitData.source = formData.source.trim();
      }
      if (formData.notes.trim()) {
        submitData.notes = formData.notes.trim();
      }

      // Parse tags
      if (formData.tags.trim()) {
        submitData.tags = formData.tags
          .split(',')
          .map(tag => tag.trim())
          .filter(tag => tag.length > 0);
      }

      // Include is_active only when editing
      if (customer) {
        submitData.is_active = formData.is_active;
      }

      await onSubmit(submitData);
    } catch (err: any) {
      setSubmitError(err.message || 'Ein Fehler ist aufgetreten');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{customer ? 'Kunde bearbeiten' : 'Neuer Kunde'}</h2>
          <button
            className="modal-close"
            onClick={onClose}
            disabled={isLoading}
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {submitError && (
              <div className="page-error" style={{ marginBottom: '1rem' }}>
                {submitError}
              </div>
            )}

            {/* Personal Information */}
            <h3 className="form-section-title">Persönliche Daten</h3>

            <div className="form-row">
              <div className="form-group">
                <label>
                  Vorname <span className="required">*</span>
                </label>
                <input
                  type="text"
                  name="first_name"
                  value={formData.first_name}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="Max"
                />
                {errors.first_name && (
                  <div className="error-message">{errors.first_name}</div>
                )}
              </div>

              <div className="form-group">
                <label>
                  Nachname <span className="required">*</span>
                </label>
                <input
                  type="text"
                  name="last_name"
                  value={formData.last_name}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="Müller"
                />
                {errors.last_name && (
                  <div className="error-message">{errors.last_name}</div>
                )}
              </div>
            </div>

            <div className="form-group">
              <label>
                E-Mail <span className="required">*</span>
              </label>
              <input
                type="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                disabled={isLoading}
                placeholder="max.mueller@example.com"
              />
              {errors.email && (
                <div className="error-message">{errors.email}</div>
              )}
            </div>

            {/* Contact Information */}
            <h3 className="form-section-title">Kontaktdaten</h3>

            <div className="form-row">
              <div className="form-group">
                <label>Telefon</label>
                <input
                  type="tel"
                  name="phone"
                  value={formData.phone}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="+49 123 456789"
                />
              </div>

              <div className="form-group">
                <label>Mobil</label>
                <input
                  type="tel"
                  name="mobile"
                  value={formData.mobile}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="+49 170 1234567"
                />
              </div>
            </div>

            {/* Address */}
            <h3 className="form-section-title">Adresse</h3>

            <div className="form-group">
              <label>Straße</label>
              <input
                type="text"
                name="street"
                value={formData.street}
                onChange={handleChange}
                disabled={isLoading}
                placeholder="Hauptstraße 123"
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>PLZ</label>
                <input
                  type="text"
                  name="postal_code"
                  value={formData.postal_code}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="12345"
                />
              </div>

              <div className="form-group">
                <label>Stadt</label>
                <input
                  type="text"
                  name="city"
                  value={formData.city}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="Berlin"
                />
              </div>
            </div>

            <div className="form-group">
              <label>Land</label>
              <input
                type="text"
                name="country"
                value={formData.country}
                onChange={handleChange}
                disabled={isLoading}
                placeholder="Deutschland"
              />
            </div>

            {/* Business Information */}
            <h3 className="form-section-title">Geschäftsinformationen</h3>

            <div className="form-group">
              <label>
                Kundentyp <span className="required">*</span>
              </label>
              <select
                name="customer_type"
                value={formData.customer_type}
                onChange={handleChange}
                disabled={isLoading}
              >
                <option value="private">Privat</option>
                <option value="business">Geschäftskunde</option>
              </select>
            </div>

            <div className="form-group">
              <label>
                Firmenname
                {formData.customer_type === 'business' && (
                  <span className="required"> *</span>
                )}
              </label>
              <input
                type="text"
                name="company_name"
                value={formData.company_name}
                onChange={handleChange}
                disabled={isLoading}
                placeholder="Gold AG"
              />
              {errors.company_name && (
                <div className="error-message">{errors.company_name}</div>
              )}
            </div>

            <div className="form-group">
              <label>Quelle</label>
              <input
                type="text"
                name="source"
                value={formData.source}
                onChange={handleChange}
                disabled={isLoading}
                placeholder="z.B. Website, Empfehlung, Messe"
              />
            </div>

            {/* Additional Information */}
            <h3 className="form-section-title">Zusätzliche Informationen</h3>

            <div className="form-group">
              <label>Tags (kommagetrennt)</label>
              <input
                type="text"
                name="tags"
                value={formData.tags}
                onChange={handleChange}
                disabled={isLoading}
                placeholder="VIP, Stammkunde, Online"
              />
            </div>

            <div className="form-group">
              <label>Notizen</label>
              <textarea
                name="notes"
                value={formData.notes}
                onChange={handleChange}
                disabled={isLoading}
                placeholder="Zusätzliche Anmerkungen zum Kunden..."
                rows={4}
              />
            </div>

            {customer && (
              <div className="form-group">
                <div className="checkbox-group">
                  <input
                    type="checkbox"
                    id="is_active"
                    name="is_active"
                    checked={formData.is_active}
                    onChange={handleChange}
                    disabled={isLoading}
                  />
                  <label htmlFor="is_active">Kunde ist aktiv</label>
                </div>
              </div>
            )}
          </div>

          <div className="modal-footer">
            <button
              type="button"
              className="btn-secondary"
              onClick={onClose}
              disabled={isLoading}
            >
              Abbrechen
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={isLoading}
            >
              {isLoading ? 'Speichern...' : customer ? 'Aktualisieren' : 'Erstellen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
