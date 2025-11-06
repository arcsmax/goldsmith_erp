/**
 * Customer Form - Create/Edit customers with GDPR compliance
 * Comprehensive form with all required GDPR fields
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getCustomer,
  createCustomer,
  updateCustomer,
  type Customer,
  type CustomerCreate,
  type CustomerUpdate,
} from '../../lib/api/customers';
import './CustomerForm.css';

const LEGAL_BASIS_OPTIONS = [
  { value: 'contract', label: 'Vertrag', description: 'Vertragserfüllung (DSGVO Art. 6(1)(b))' },
  { value: 'consent', label: 'Einwilligung', description: 'Ausdrückliche Einwilligung (DSGVO Art. 6(1)(a))' },
  { value: 'legitimate_interest', label: 'Berechtigtes Interesse', description: 'Berechtigtes Interesse (DSGVO Art. 6(1)(f))' },
];

const COUNTRIES = ['Deutschland', 'Österreich', 'Schweiz', 'Andere'];

const CONSENT_VERSION = '1.0';

export default function CustomerForm() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEditMode = !!id;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Basic Information
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');

  // Address
  const [addressLine1, setAddressLine1] = useState('');
  const [addressLine2, setAddressLine2] = useState('');
  const [postalCode, setPostalCode] = useState('');
  const [city, setCity] = useState('');
  const [country, setCountry] = useState('Deutschland');

  // GDPR Compliance
  const [legalBasis, setLegalBasis] = useState<'contract' | 'consent' | 'legitimate_interest'>('contract');
  const [dataProcessingConsent, setDataProcessingConsent] = useState(true);
  const [consentMarketing, setConsentMarketing] = useState(false);
  const [emailCommunicationConsent, setEmailCommunicationConsent] = useState(true);
  const [phoneCommunicationConsent, setPhoneCommunicationConsent] = useState(false);
  const [smsCommunicationConsent, setSmsCommunicationConsent] = useState(false);

  // Additional
  const [notes, setNotes] = useState('');
  const [tags, setTags] = useState('');

  useEffect(() => {
    if (isEditMode && id) {
      loadCustomer(parseInt(id));
    }
  }, [id, isEditMode]);

  const loadCustomer = async (customerId: number) => {
    try {
      setLoading(true);
      const customer = await getCustomer(customerId);

      setFirstName(customer.first_name);
      setLastName(customer.last_name);
      setEmail(customer.email);
      setPhone(customer.phone || '');

      setAddressLine1(customer.address_line1 || '');
      setAddressLine2(customer.address_line2 || '');
      setPostalCode(customer.postal_code || '');
      setCity(customer.city || '');
      setCountry(customer.country);

      setLegalBasis(customer.legal_basis as 'contract' | 'consent' | 'legitimate_interest');
      setDataProcessingConsent(customer.data_processing_consent);
      setConsentMarketing(customer.consent_marketing);
      setEmailCommunicationConsent(customer.email_communication_consent);
      setPhoneCommunicationConsent(customer.phone_communication_consent);
      setSmsCommunicationConsent(customer.sms_communication_consent || false);

      setNotes(customer.notes || '');
      setTags(customer.tags?.join(', ') || '');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden des Kunden');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (!firstName.trim()) {
      setError('Bitte geben Sie einen Vornamen ein');
      return;
    }

    if (!lastName.trim()) {
      setError('Bitte geben Sie einen Nachnamen ein');
      return;
    }

    if (!email.trim()) {
      setError('Bitte geben Sie eine E-Mail-Adresse ein');
      return;
    }

    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setError('Bitte geben Sie eine gültige E-Mail-Adresse ein');
      return;
    }

    // GDPR validation
    if (!dataProcessingConsent) {
      setError('Die Einwilligung zur Datenverarbeitung ist erforderlich');
      return;
    }

    try {
      setSaving(true);

      const customerData: CustomerCreate | CustomerUpdate = {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim().toLowerCase(),
        phone: phone.trim() || undefined,
        address_line1: addressLine1.trim() || undefined,
        address_line2: addressLine2.trim() || undefined,
        postal_code: postalCode.trim() || undefined,
        city: city.trim() || undefined,
        country: country,
        legal_basis: legalBasis,
        consent_marketing: consentMarketing,
        consent_version: CONSENT_VERSION,
        consent_method: 'web_form',
        data_processing_consent: dataProcessingConsent,
        email_communication_consent: emailCommunicationConsent,
        phone_communication_consent: phoneCommunicationConsent,
        sms_communication_consent: smsCommunicationConsent,
        notes: notes.trim() || undefined,
        tags: tags
          .split(',')
          .map((tag) => tag.trim())
          .filter((tag) => tag.length > 0) || undefined,
      };

      if (isEditMode && id) {
        await updateCustomer(parseInt(id), customerData);
      } else {
        await createCustomer(customerData as CustomerCreate);
      }

      navigate('/customers');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Speichern des Kunden');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    navigate('/customers');
  };

  if (loading) {
    return (
      <div className="customer-form-loading">
        <div className="spinner"></div>
        <p>Lade Kundendaten...</p>
      </div>
    );
  }

  return (
    <div className="customer-form-container">
      <div className="customer-form-header">
        <h1>{isEditMode ? 'Kunde bearbeiten' : 'Neuen Kunden hinzufügen'}</h1>
        <div className="gdpr-badge">
          🔒 DSGVO-konform
        </div>
      </div>

      <form onSubmit={handleSubmit} className="customer-form">
        {error && (
          <div className="form-error">
            ❌ {error}
          </div>
        )}

        {/* Basic Information */}
        <div className="form-section">
          <h2>Persönliche Informationen</h2>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="firstName">
                Vorname <span className="required">*</span>
              </label>
              <input
                id="firstName"
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                placeholder="Max"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="lastName">
                Nachname <span className="required">*</span>
              </label>
              <input
                id="lastName"
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                placeholder="Mustermann"
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="email">
                E-Mail <span className="required">*</span>
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="max.mustermann@example.de"
                required
              />
              <small className="field-hint">
                Wird für Kommunikation und DSGVO-Anfragen verwendet
              </small>
            </div>

            <div className="form-group">
              <label htmlFor="phone">Telefon</label>
              <input
                id="phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+49 123 456789"
              />
              <small className="field-hint">
                Optional, verschlüsselt gespeichert
              </small>
            </div>
          </div>
        </div>

        {/* Address */}
        <div className="form-section">
          <h2>Adresse</h2>

          <div className="form-group">
            <label htmlFor="addressLine1">Straße und Hausnummer</label>
            <input
              id="addressLine1"
              type="text"
              value={addressLine1}
              onChange={(e) => setAddressLine1(e.target.value)}
              placeholder="Musterstraße 123"
            />
          </div>

          <div className="form-group">
            <label htmlFor="addressLine2">Adresszusatz</label>
            <input
              id="addressLine2"
              type="text"
              value={addressLine2}
              onChange={(e) => setAddressLine2(e.target.value)}
              placeholder="Apartment 4B"
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="postalCode">Postleitzahl</label>
              <input
                id="postalCode"
                type="text"
                value={postalCode}
                onChange={(e) => setPostalCode(e.target.value)}
                placeholder="12345"
              />
            </div>

            <div className="form-group">
              <label htmlFor="city">Stadt</label>
              <input
                id="city"
                type="text"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Berlin"
              />
            </div>

            <div className="form-group">
              <label htmlFor="country">Land</label>
              <select
                id="country"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
              >
                {COUNTRIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <small className="field-hint">
            🔒 Adressdaten werden verschlüsselt gespeichert (DSGVO Art. 32)
          </small>
        </div>

        {/* GDPR Compliance */}
        <div className="form-section gdpr-section">
          <h2>🔒 DSGVO-Compliance</h2>

          <div className="form-group">
            <label htmlFor="legalBasis">
              Rechtsgrundlage <span className="required">*</span>
            </label>
            <select
              id="legalBasis"
              value={legalBasis}
              onChange={(e) => setLegalBasis(e.target.value as any)}
              required
            >
              {LEGAL_BASIS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <small className="field-hint">
              {LEGAL_BASIS_OPTIONS.find((o) => o.value === legalBasis)?.description}
            </small>
          </div>

          <div className="consent-group">
            <h3>Einwilligungen</h3>

            <div className="consent-item required-consent">
              <label>
                <input
                  type="checkbox"
                  checked={dataProcessingConsent}
                  onChange={(e) => setDataProcessingConsent(e.target.checked)}
                  required
                />
                <span className="consent-label">
                  <strong>Datenverarbeitung (Erforderlich) *</strong>
                  <small>
                    Ich willige in die Verarbeitung meiner personenbezogenen Daten gemäß DSGVO Art.
                    6(1) ein.
                  </small>
                </span>
              </label>
            </div>

            <div className="consent-item">
              <label>
                <input
                  type="checkbox"
                  checked={consentMarketing}
                  onChange={(e) => setConsentMarketing(e.target.checked)}
                />
                <span className="consent-label">
                  <strong>Marketing-Einwilligung</strong>
                  <small>Ich möchte Informationen über Angebote und Neuigkeiten erhalten.</small>
                </span>
              </label>
            </div>

            <div className="consent-item">
              <label>
                <input
                  type="checkbox"
                  checked={emailCommunicationConsent}
                  onChange={(e) => setEmailCommunicationConsent(e.target.checked)}
                />
                <span className="consent-label">
                  <strong>E-Mail-Kommunikation</strong>
                  <small>Kontaktaufnahme per E-Mail für geschäftliche Zwecke.</small>
                </span>
              </label>
            </div>

            <div className="consent-item">
              <label>
                <input
                  type="checkbox"
                  checked={phoneCommunicationConsent}
                  onChange={(e) => setPhoneCommunicationConsent(e.target.checked)}
                />
                <span className="consent-label">
                  <strong>Telefon-Kommunikation</strong>
                  <small>Kontaktaufnahme per Telefon für geschäftliche Zwecke.</small>
                </span>
              </label>
            </div>

            <div className="consent-item">
              <label>
                <input
                  type="checkbox"
                  checked={smsCommunicationConsent}
                  onChange={(e) => setSmsCommunicationConsent(e.target.checked)}
                />
                <span className="consent-label">
                  <strong>SMS-Kommunikation</strong>
                  <small>Kontaktaufnahme per SMS für Terminbestätigungen etc.</small>
                </span>
              </label>
            </div>
          </div>

          <div className="gdpr-info-box">
            <strong>Ihre Rechte:</strong> Sie können Ihre Einwilligungen jederzeit widerrufen. Sie
            haben das Recht auf Auskunft, Berichtigung, Löschung und Datenübertragbarkeit (DSGVO Art.
            15-20).
          </div>
        </div>

        {/* Additional Information */}
        <div className="form-section">
          <h2>Zusätzliche Informationen</h2>

          <div className="form-group">
            <label htmlFor="notes">Notizen</label>
            <textarea
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Interne Notizen zum Kunden..."
              rows={4}
            />
            <small className="field-hint">
              Für interne Verwendung, nicht für den Kunden sichtbar
            </small>
          </div>

          <div className="form-group">
            <label htmlFor="tags">Tags</label>
            <input
              id="tags"
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="VIP, Stammkunde, Großauftrag (Komma-getrennt)"
            />
            <small className="field-hint">
              Mehrere Tags mit Komma trennen
            </small>
          </div>
        </div>

        {/* Form Actions */}
        <div className="form-actions">
          <button
            type="button"
            className="btn-cancel"
            onClick={handleCancel}
            disabled={saving}
          >
            Abbrechen
          </button>
          <button type="submit" className="btn-submit" disabled={saving}>
            {saving ? (
              <>
                <span className="btn-spinner"></span>
                Speichert...
              </>
            ) : (
              <>💾 {isEditMode ? 'Änderungen speichern' : 'Kunde hinzufügen'}</>
            )}
          </button>
        </div>
      </form>

      {/* GDPR Compliance Notice */}
      <div className="gdpr-footer">
        <p>
          🔒 Alle Daten werden gemäß DSGVO verschlüsselt gespeichert und protokolliert. Jede
          Datenverarbeitung wird in Ihrem Audit-Log dokumentiert (Art. 30 DSGVO).
        </p>
      </div>
    </div>
  );
}
