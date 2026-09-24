// CustomerFormModal - Modal for creating and editing customers
import React, { useState, useEffect, useRef } from 'react';
import { Customer, CustomerCategory, CustomerCreateInput, CustomerUpdateInput } from '../types';
import { CustomerCreateSchema } from '../lib/validation/schemas';
import { useFormValidation } from '../lib/validation/useFormValidation';
import { useConfirm, useToast } from '../contexts';
import { logError } from '../lib/logError';
import {
  CONSENT_METHOD_LABELS,
  ConsentRecord,
  consentsApi,
  extractErrorDetail,
  findActiveConsent,
} from '../api/consents';
import '../styles/customers.css';
// Pulls .cdetail-notes, reused below as the small hint/status text under the
// consent-gated allergies field (customers.css has no equivalent class).
import '../styles/customer-detail.css';

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
  const firstInputRef = useRef<HTMLInputElement>(null);
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
    ring_size: '',
    chain_length_cm: '',
    bracelet_length_cm: '',
    allergies: '',
    birthday: '',
    preferences: '',
  });

  const { validate: zodValidate, errors, clearErrors, clearError } = useFormValidation(CustomerCreateSchema);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { showConfirm } = useConfirm();
  const { showToast } = useToast();

  // GDPR-02 / GDPR-11: allergies are Art. 9 health data and may only be
  // stored while an active HEALTH_DATA consent exists for the customer
  // (see api/consents.ts + services/consent_service.py). `healthConsent`
  // holds that active record for an existing customer; `healthConsentConfirmed`
  // is the local checkbox used to unlock the field before one exists yet.
  const [healthConsent, setHealthConsent] = useState<ConsentRecord | null>(null);
  const [isLoadingConsent, setIsLoadingConsent] = useState(false);
  const [healthConsentConfirmed, setHealthConsentConfirmed] = useState(false);
  const [consentNote, setConsentNote] = useState('');
  const [consentError, setConsentError] = useState<string | null>(null);
  const [isRevokingConsent, setIsRevokingConsent] = useState(false);

  const hasActiveHealthConsent = healthConsent !== null;
  const allergiesEnabled = hasActiveHealthConsent || healthConsentConfirmed;

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
        ring_size: customer.ring_size != null ? String(customer.ring_size) : '',
        chain_length_cm: customer.chain_length_cm != null ? String(customer.chain_length_cm) : '',
        bracelet_length_cm: customer.bracelet_length_cm != null ? String(customer.bracelet_length_cm) : '',
        allergies: customer.allergies || '',
        birthday: customer.birthday ? customer.birthday.substring(0, 10) : '',
        preferences: customer.preferences
          ? Object.entries(customer.preferences).map(([k, v]) => `${k}: ${v}`).join(', ')
          : '',
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
        ring_size: '',
        chain_length_cm: '',
        bracelet_length_cm: '',
        allergies: '',
        birthday: '',
        preferences: '',
      });
    }
    clearErrors();
    setSubmitError(null);
    setHealthConsent(null);
    setHealthConsentConfirmed(false);
    setConsentNote('');
    setConsentError(null);

    if (customer) {
      setIsLoadingConsent(true);
      consentsApi
        .list(customer.id)
        .then((records) => {
          setHealthConsent(findActiveConsent(records, 'health_data'));
        })
        .catch((err) => {
          // Non-fatal: the allergies field simply stays gated behind the
          // checkbox below if we can't confirm an existing consent (e.g.
          // the request failed, or the viewer lacks CONSENT_MANAGE).
          logError('CustomerFormModal.loadHealthConsent', err);
        })
        .finally(() => setIsLoadingConsent(false));
    }
  }, [customer]); // eslint-disable-line react-hooks/exhaustive-deps

  // Focus the first input when modal opens
  useEffect(() => {
    if (isOpen) {
      const t = setTimeout(() => firstInputRef.current?.focus(), 30);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

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

    clearError(name);
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Build the payload to validate (only scalar fields; tags/preferences are
    // assembled further down after Zod passes the core fields)
    const toValidate = {
      first_name: formData.first_name.trim(),
      last_name: formData.last_name.trim(),
      email: formData.email.trim(),
      customer_type: formData.customer_type,
      country: formData.country,
      company_name: formData.company_name.trim() || undefined,
      phone: formData.phone.trim() || undefined,
      mobile: formData.mobile.trim() || undefined,
      street: formData.street.trim() || undefined,
      city: formData.city.trim() || undefined,
      postal_code: formData.postal_code.trim() || undefined,
      source: formData.source.trim() || undefined,
      notes: formData.notes.trim() || undefined,
      allergies: formData.allergies.trim() || undefined,
      birthday: formData.birthday || undefined,
      ring_size: formData.ring_size !== '' ? parseFloat(formData.ring_size) : undefined,
      chain_length_cm: formData.chain_length_cm !== '' ? parseFloat(formData.chain_length_cm) : undefined,
      bracelet_length_cm: formData.bracelet_length_cm !== '' ? parseFloat(formData.bracelet_length_cm) : undefined,
    };

    const zodResult = zodValidate(toValidate);
    if (!zodResult.success) {
      return;
    }

    // GDPR-02: allergies are Art. 9 health data. Storing them needs an
    // active HEALTH_DATA consent — grant it here (or strip the field for a
    // brand-new customer, see below) before the customer is saved.
    const allergiesValue = formData.allergies.trim();
    const needsConsentGrant = allergiesValue !== '' && !hasActiveHealthConsent;
    setConsentError(null);
    if (needsConsentGrant) {
      if (!healthConsentConfirmed) {
        setConsentError('Bitte zuerst die Einwilligung „Gesundheitsdaten“ bestätigen.');
        return;
      }
      if (consentNote.trim() === '') {
        setConsentError('Bitte einen kurzen Nachweis zur Einwilligung angeben.');
        return;
      }
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

      // Measurement fields
      if (formData.ring_size !== '') {
        submitData.ring_size = parseFloat(formData.ring_size);
      }
      if (formData.chain_length_cm !== '') {
        submitData.chain_length_cm = parseFloat(formData.chain_length_cm);
      }
      if (formData.bracelet_length_cm !== '') {
        submitData.bracelet_length_cm = parseFloat(formData.bracelet_length_cm);
      }
      if (formData.allergies.trim()) {
        submitData.allergies = formData.allergies.trim();
      }
      if (formData.birthday) {
        submitData.birthday = formData.birthday;
      }

      // Parse preferences (key: value pairs, comma-separated)
      if (formData.preferences.trim()) {
        const prefs: Record<string, string> = {};
        formData.preferences.split(',').forEach(pair => {
          const [key, ...valueParts] = pair.split(':');
          if (key && valueParts.length > 0) {
            prefs[key.trim()] = valueParts.join(':').trim();
          }
        });
        if (Object.keys(prefs).length > 0) {
          submitData.preferences = prefs;
        }
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

      if (needsConsentGrant && customer) {
        // Editing an existing customer: the consent endpoint is keyed by
        // customer id, which we already have — record it, THEN save the
        // allergy text via the normal PATCH below (GDPR-02 / GDPR-11).
        try {
          const granted = await consentsApi.grant(customer.id, {
            purpose: 'health_data',
            method: 'in_person',
            note: consentNote.trim(),
          });
          setHealthConsent(granted);
        } catch (err) {
          logError('CustomerFormModal.grantHealthConsent', err);
          setConsentError(
            extractErrorDetail(err) ?? 'Einwilligung konnte nicht gespeichert werden.'
          );
          return;
        }
      } else if (needsConsentGrant && !customer) {
        // Brand-new customer: there is no customer id yet, so the consent
        // can't be recorded before creation (the backend 422s allergies on
        // create for the same reason — see
        // tests/integration/test_customer_allergy_consent.py::test_customer_create_with_allergies_is_422).
        // Create the customer without allergies now; the consent + allergy
        // text are finished afterwards from the edit dialog, where a
        // customer id exists.
        delete submitData.allergies;
      }

      await onSubmit(submitData);

      if (needsConsentGrant && !customer) {
        showToast(
          'Kunde wurde ohne Allergien gespeichert. Bitte die Allergie anschließend über „Kunde bearbeiten“ inklusive Einwilligung erfassen.',
          'info'
        );
      }
    } catch (err: any) {
      setSubmitError(err.message || 'Ein Fehler ist aufgetreten');
    }
  };

  const handleRevokeHealthConsent = async () => {
    if (!customer || isRevokingConsent) return;
    const confirmed = await showConfirm({
      title: 'Einwilligung widerrufen',
      message:
        'Möchten Sie die Einwilligung „Gesundheitsdaten“ wirklich widerrufen? Dadurch werden gespeicherte Allergien gelöscht.',
      confirmLabel: 'Widerrufen',
      variant: 'danger',
    });
    if (!confirmed) return;

    setIsRevokingConsent(true);
    try {
      await consentsApi.revoke(customer.id, 'health_data');
      setHealthConsent(null);
      setHealthConsentConfirmed(false);
      setFormData((prev) => ({ ...prev, allergies: '' }));
      showToast('Einwilligung wurde widerrufen. Allergien wurden gelöscht.', 'success');
    } catch (err) {
      logError('CustomerFormModal.revokeHealthConsent', err);
      showToast(
        extractErrorDetail(err) ?? 'Einwilligung konnte nicht widerrufen werden.',
        'error'
      );
    } finally {
      setIsRevokingConsent(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="customer-modal-title"
      onClick={onClose}
    >
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 id="customer-modal-title">{customer ? 'Kunde bearbeiten' : 'Neuer Kunde'}</h2>
          <button
            className="modal-close"
            onClick={onClose}
            disabled={isLoading}
            aria-label="Modal schließen"
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
                <label htmlFor="first_name">
                  Vorname <span className="required">*</span>
                </label>
                <input
                  type="text"
                  id="first_name"
                  name="first_name"
                  ref={firstInputRef}
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
                <label htmlFor="last_name">
                  Nachname <span className="required">*</span>
                </label>
                <input
                  type="text"
                  id="last_name"
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
              <label htmlFor="email">
                E-Mail <span className="required">*</span>
              </label>
              <input
                type="email"
                id="email"
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
                <label htmlFor="phone">Telefon</label>
                <input
                  type="tel"
                  id="phone"
                  name="phone"
                  value={formData.phone}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="+49 123 456789"
                />
              </div>

              <div className="form-group">
                <label htmlFor="mobile">Mobil</label>
                <input
                  type="tel"
                  id="mobile"
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
              <label htmlFor="street">Straße</label>
              <input
                type="text"
                id="street"
                name="street"
                value={formData.street}
                onChange={handleChange}
                disabled={isLoading}
                placeholder="Hauptstraße 123"
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="postal_code">PLZ</label>
                <input
                  type="text"
                  id="postal_code"
                  name="postal_code"
                  value={formData.postal_code}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="12345"
                />
              </div>

              <div className="form-group">
                <label htmlFor="city">Stadt</label>
                <input
                  type="text"
                  id="city"
                  name="city"
                  value={formData.city}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="Berlin"
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="country">Land</label>
              <input
                type="text"
                id="country"
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
              <label htmlFor="customer_type">
                Kundentyp <span className="required">*</span>
              </label>
              <select
                id="customer_type"
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
              <label htmlFor="company_name">
                Firmenname
                {formData.customer_type === 'business' && (
                  <span className="required"> *</span>
                )}
              </label>
              <input
                type="text"
                id="company_name"
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
              <label htmlFor="source">Quelle</label>
              <input
                type="text"
                id="source"
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
              <label htmlFor="tags">Tags (kommagetrennt)</label>
              <input
                type="text"
                id="tags"
                name="tags"
                value={formData.tags}
                onChange={handleChange}
                disabled={isLoading}
                placeholder="VIP, Stammkunde, Online"
              />
            </div>

            <div className="form-group">
              <label htmlFor="notes">Notizen</label>
              <textarea
                id="notes"
                name="notes"
                value={formData.notes}
                onChange={handleChange}
                disabled={isLoading}
                placeholder="Zusätzliche Anmerkungen zum Kunden..."
                rows={4}
              />
            </div>

            {/* Measurements & Preferences */}
            <h3 className="form-section-title">Masse & Vorlieben</h3>

            <div className="form-row" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
              <div className="form-group">
                <label htmlFor="ring_size">Ringgroesse (EU)</label>
                <input
                  type="number"
                  id="ring_size"
                  name="ring_size"
                  value={formData.ring_size}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="z.B. 54"
                  step="0.5"
                  min="0"
                />
              </div>

              <div className="form-group">
                <label htmlFor="chain_length_cm">Kettenlaenge (cm)</label>
                <input
                  type="number"
                  id="chain_length_cm"
                  name="chain_length_cm"
                  value={formData.chain_length_cm}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="z.B. 45"
                  step="0.5"
                  min="0"
                />
              </div>

              <div className="form-group">
                <label htmlFor="bracelet_length_cm">Armband-Laenge (cm)</label>
                <input
                  type="number"
                  id="bracelet_length_cm"
                  name="bracelet_length_cm"
                  value={formData.bracelet_length_cm}
                  onChange={handleChange}
                  disabled={isLoading}
                  placeholder="z.B. 18"
                  step="0.5"
                  min="0"
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="allergies">Allergien</label>
              <input
                type="text"
                id="allergies"
                name="allergies"
                value={formData.allergies}
                onChange={handleChange}
                disabled={isLoading || !allergiesEnabled}
                placeholder="z.B. Nickel, Kupfer"
              />
              {!allergiesEnabled && (
                <p className="cdetail-notes">
                  Allergien sind Gesundheitsdaten (Art. 9 DSGVO) — das Feld ist erst
                  nutzbar, sobald die Einwilligung „Gesundheitsdaten“ vorliegt.
                </p>
              )}
            </div>

            {hasActiveHealthConsent ? (
              <div className="form-group">
                <p className="cdetail-notes">
                  Einwilligung „Gesundheitsdaten“ erteilt am{' '}
                  {healthConsent && new Date(healthConsent.granted_at).toLocaleDateString('de-DE')}
                  {healthConsent && ` (${CONSENT_METHOD_LABELS[healthConsent.method]})`}.
                </p>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleRevokeHealthConsent}
                  disabled={isLoading || isRevokingConsent}
                >
                  {isRevokingConsent ? 'Wird widerrufen…' : 'Einwilligung widerrufen'}
                </button>
              </div>
            ) : (
              <div className="form-group">
                <div className="checkbox-group">
                  <input
                    type="checkbox"
                    id="health_consent_confirmed"
                    checked={healthConsentConfirmed}
                    onChange={(e) => {
                      setHealthConsentConfirmed(e.target.checked);
                      setConsentError(null);
                    }}
                    disabled={isLoading || isLoadingConsent}
                  />
                  <label htmlFor="health_consent_confirmed">
                    Einwilligung „Gesundheitsdaten“ liegt vor
                  </label>
                </div>
                {healthConsentConfirmed && (
                  <div className="form-group">
                    <label htmlFor="health_consent_note">
                      Nachweis der Einwilligung <span className="required">*</span>
                    </label>
                    <input
                      type="text"
                      id="health_consent_note"
                      value={consentNote}
                      onChange={(e) => {
                        setConsentNote(e.target.value);
                        setConsentError(null);
                      }}
                      disabled={isLoading}
                      placeholder="z.B. mündlich beim Termin bestätigt"
                      maxLength={500}
                    />
                  </div>
                )}
                {consentError && <div className="error-message">{consentError}</div>}
              </div>
            )}

            <div className="form-group">
              <label htmlFor="birthday">Geburtstag</label>
              <input
                type="date"
                id="birthday"
                name="birthday"
                value={formData.birthday}
                onChange={handleChange}
                disabled={isLoading}
              />
            </div>

            <div className="form-group">
              <label htmlFor="preferences">Vorlieben (kommagetrennt, Format: Schluessel: Wert)</label>
              <input
                type="text"
                id="preferences"
                name="preferences"
                value={formData.preferences}
                onChange={handleChange}
                disabled={isLoading}
                placeholder="z.B. Bevorzugtes Metall: Platin, Stil: Modern"
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
