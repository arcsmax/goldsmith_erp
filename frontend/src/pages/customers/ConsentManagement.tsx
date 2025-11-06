/**
 * Consent Management Page - GDPR Article 7 Compliance
 * Manage customer consents for various communication types
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getCustomer,
  getConsentStatus,
  updateConsent,
  revokeAllConsents,
  formatCustomerName,
  type Customer,
  type ConsentStatus,
  type ConsentUpdate,
} from '../../lib/api/customers';
import './ConsentManagement.css';

const CONSENT_VERSION = '1.0';

export default function ConsentManagement() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [consentStatus, setConsentStatus] = useState<ConsentStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Consent states
  const [marketingConsent, setMarketingConsent] = useState(false);
  const [emailConsent, setEmailConsent] = useState(false);
  const [phoneConsent, setPhoneConsent] = useState(false);
  const [smsConsent, setSmsConsent] = useState(false);
  const [dataProcessingConsent, setDataProcessingConsent] = useState(false);

  useEffect(() => {
    if (id) {
      loadCustomerAndConsents(parseInt(id));
    }
  }, [id]);

  const loadCustomerAndConsents = async (customerId: number) => {
    try {
      setLoading(true);
      setError(null);

      const [customerData, consents] = await Promise.all([
        getCustomer(customerId),
        getConsentStatus(customerId),
      ]);

      setCustomer(customerData);
      setConsentStatus(consents);

      // Set consent states
      setMarketingConsent(consents.marketing);
      setEmailConsent(consents.email_communication);
      setPhoneConsent(consents.phone_communication);
      setSmsConsent(consents.sms_communication);
      setDataProcessingConsent(consents.data_processing);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Einwilligungen');
    } finally {
      setLoading(false);
    }
  };

  const handleConsentUpdate = async (
    consentType: 'marketing' | 'email' | 'phone' | 'sms' | 'data_processing',
    value: boolean
  ) => {
    if (!customer) return;

    try {
      setSaving(true);

      const consentUpdate: ConsentUpdate = {
        consent_type: consentType,
        consent_value: value,
        consent_version: CONSENT_VERSION,
        consent_method: 'web_interface',
      };

      const updatedCustomer = await updateConsent(customer.id, consentUpdate);

      // Reload consent status
      await loadCustomerAndConsents(customer.id);

      alert('Einwilligung erfolgreich aktualisiert');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Aktualisieren der Einwilligung');
      // Revert the change
      await loadCustomerAndConsents(customer.id);
    } finally {
      setSaving(false);
    }
  };

  const handleRevokeAll = async () => {
    if (!customer) return;

    const confirmMessage = `WARNUNG: Möchten Sie wirklich ALLE Einwilligungen für ${formatCustomerName(
      customer
    )} widerrufen?\n\nDies betrifft:\n- Marketing\n- E-Mail-Kommunikation\n- Telefon-Kommunikation\n- SMS-Kommunikation\n\nDie Datenverarbeitungseinwilligung kann nicht widerrufen werden, da sie für die Geschäftsbeziehung erforderlich ist.`;

    if (!confirm(confirmMessage)) {
      return;
    }

    try {
      setSaving(true);
      await revokeAllConsents(customer.id);
      await loadCustomerAndConsents(customer.id);
      alert('Alle Einwilligungen erfolgreich widerrufen (DSGVO Art. 7(3))');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Widerrufen der Einwilligungen');
    } finally {
      setSaving(false);
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Unbekannt';
    return new Date(dateString).toLocaleDateString('de-DE', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="consent-management-loading">
        <div className="spinner"></div>
        <p>Lade Einwilligungen...</p>
      </div>
    );
  }

  if (error || !customer || !consentStatus) {
    return (
      <div className="consent-management-error">
        <h2>❌ Fehler</h2>
        <p>{error || 'Kunde oder Einwilligungen nicht gefunden'}</p>
        <button onClick={() => navigate('/customers')} className="btn-back">
          Zurück zur Liste
        </button>
      </div>
    );
  }

  return (
    <div className="consent-management-container">
      {/* Header */}
      <div className="consent-header">
        <button onClick={() => navigate(`/customers/${customer.id}`)} className="btn-back-small">
          ← Zurück zum Kunden
        </button>
      </div>

      {/* Customer Info */}
      <div className="customer-info-banner">
        <div className="customer-avatar">{customer.first_name[0]}{customer.last_name[0]}</div>
        <div className="customer-details">
          <h1>Einwilligungen verwalten</h1>
          <p className="customer-name">{formatCustomerName(customer)}</p>
          <p className="customer-email">{customer.email}</p>
        </div>
      </div>

      {/* GDPR Info Banner */}
      <div className="gdpr-info-banner">
        <span className="gdpr-icon">🔒</span>
        <div className="gdpr-text">
          <strong>DSGVO Art. 7:</strong> Der Kunde kann Einwilligungen jederzeit widerrufen. Der
          Widerruf ist so einfach wie die Erteilung der Einwilligung. Alle Änderungen werden
          protokolliert (Art. 30 DSGVO).
        </div>
      </div>

      {/* Consent Status Card */}
      <div className="consent-status-card">
        <h2>Einwilligungsstatus</h2>

        <div className="consent-metadata">
          <div className="metadata-item">
            <span className="metadata-label">Letzte Einwilligung:</span>
            <span className="metadata-value">{formatDate(consentStatus.consent_date)}</span>
          </div>
          {consentStatus.consent_version && (
            <div className="metadata-item">
              <span className="metadata-label">Einwilligungsversion:</span>
              <span className="metadata-value">{consentStatus.consent_version}</span>
            </div>
          )}
          {consentStatus.consent_method && (
            <div className="metadata-item">
              <span className="metadata-label">Methode:</span>
              <span className="metadata-value">{consentStatus.consent_method}</span>
            </div>
          )}
        </div>

        {/* Consent Toggles */}
        <div className="consent-toggles">
          {/* Data Processing Consent (Required) */}
          <div className="consent-toggle-item required">
            <div className="consent-info">
              <div className="consent-icon">📋</div>
              <div className="consent-details">
                <h3>Datenverarbeitung</h3>
                <p>
                  Grundlegende Datenverarbeitung für die Geschäftsbeziehung (DSGVO Art. 6(1)(b))
                </p>
                <small className="consent-note">
                  Erforderlich - Kann nicht widerrufen werden ohne Beendigung der
                  Geschäftsbeziehung
                </small>
              </div>
            </div>
            <div className="consent-toggle-control">
              <label className="toggle-switch disabled">
                <input
                  type="checkbox"
                  checked={dataProcessingConsent}
                  disabled
                />
                <span className="toggle-slider"></span>
              </label>
              <span className={`consent-status-badge ${dataProcessingConsent ? 'active' : 'inactive'}`}>
                {dataProcessingConsent ? 'Erteilt' : 'Nicht erteilt'}
              </span>
            </div>
          </div>

          {/* Marketing Consent */}
          <div className="consent-toggle-item">
            <div className="consent-info">
              <div className="consent-icon">📧</div>
              <div className="consent-details">
                <h3>Marketing-Einwilligung</h3>
                <p>Erhalt von Marketing-Materialien, Angeboten und Neuigkeiten</p>
                <small className="consent-note">
                  DSGVO Art. 6(1)(a) - Jederzeit widerrufbar
                </small>
              </div>
            </div>
            <div className="consent-toggle-control">
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={marketingConsent}
                  onChange={(e) => {
                    setMarketingConsent(e.target.checked);
                    handleConsentUpdate('marketing', e.target.checked);
                  }}
                  disabled={saving}
                />
                <span className="toggle-slider"></span>
              </label>
              <span className={`consent-status-badge ${marketingConsent ? 'active' : 'inactive'}`}>
                {marketingConsent ? 'Erteilt' : 'Nicht erteilt'}
              </span>
            </div>
          </div>

          {/* Email Communication Consent */}
          <div className="consent-toggle-item">
            <div className="consent-info">
              <div className="consent-icon">✉️</div>
              <div className="consent-details">
                <h3>E-Mail-Kommunikation</h3>
                <p>Kontaktaufnahme per E-Mail für geschäftliche Zwecke</p>
                <small className="consent-note">
                  DSGVO Art. 6(1)(a) - Jederzeit widerrufbar
                </small>
              </div>
            </div>
            <div className="consent-toggle-control">
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={emailConsent}
                  onChange={(e) => {
                    setEmailConsent(e.target.checked);
                    handleConsentUpdate('email', e.target.checked);
                  }}
                  disabled={saving}
                />
                <span className="toggle-slider"></span>
              </label>
              <span className={`consent-status-badge ${emailConsent ? 'active' : 'inactive'}`}>
                {emailConsent ? 'Erteilt' : 'Nicht erteilt'}
              </span>
            </div>
          </div>

          {/* Phone Communication Consent */}
          <div className="consent-toggle-item">
            <div className="consent-info">
              <div className="consent-icon">📞</div>
              <div className="consent-details">
                <h3>Telefon-Kommunikation</h3>
                <p>Kontaktaufnahme per Telefon für geschäftliche Zwecke</p>
                <small className="consent-note">
                  DSGVO Art. 6(1)(a) - Jederzeit widerrufbar
                </small>
              </div>
            </div>
            <div className="consent-toggle-control">
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={phoneConsent}
                  onChange={(e) => {
                    setPhoneConsent(e.target.checked);
                    handleConsentUpdate('phone', e.target.checked);
                  }}
                  disabled={saving}
                />
                <span className="toggle-slider"></span>
              </label>
              <span className={`consent-status-badge ${phoneConsent ? 'active' : 'inactive'}`}>
                {phoneConsent ? 'Erteilt' : 'Nicht erteilt'}
              </span>
            </div>
          </div>

          {/* SMS Communication Consent */}
          <div className="consent-toggle-item">
            <div className="consent-info">
              <div className="consent-icon">💬</div>
              <div className="consent-details">
                <h3>SMS-Kommunikation</h3>
                <p>Kontaktaufnahme per SMS für Terminbestätigungen etc.</p>
                <small className="consent-note">
                  DSGVO Art. 6(1)(a) - Jederzeit widerrufbar
                </small>
              </div>
            </div>
            <div className="consent-toggle-control">
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={smsConsent}
                  onChange={(e) => {
                    setSmsConsent(e.target.checked);
                    handleConsentUpdate('sms', e.target.checked);
                  }}
                  disabled={saving}
                />
                <span className="toggle-slider"></span>
              </label>
              <span className={`consent-status-badge ${smsConsent ? 'active' : 'inactive'}`}>
                {smsConsent ? 'Erteilt' : 'Nicht erteilt'}
              </span>
            </div>
          </div>
        </div>

        {/* Revoke All Button */}
        <div className="revoke-all-section">
          <button
            onClick={handleRevokeAll}
            disabled={saving}
            className="btn-revoke-all"
          >
            🚫 Alle Einwilligungen widerrufen
          </button>
          <small className="revoke-note">
            Widerruft alle optionalen Einwilligungen (Marketing, E-Mail, Telefon, SMS)
          </small>
        </div>
      </div>

      {/* GDPR Rights Info */}
      <div className="gdpr-rights-card">
        <h2>Rechte des Kunden (DSGVO)</h2>
        <div className="rights-grid">
          <div className="right-item">
            <div className="right-icon">📋</div>
            <div className="right-content">
              <strong>Art. 15 - Auskunftsrecht</strong>
              <p>Recht auf Auskunft über verarbeitete personenbezogene Daten</p>
            </div>
          </div>

          <div className="right-item">
            <div className="right-icon">✏️</div>
            <div className="right-content">
              <strong>Art. 16 - Recht auf Berichtigung</strong>
              <p>Recht auf Berichtigung unrichtiger Daten</p>
            </div>
          </div>

          <div className="right-item">
            <div className="right-icon">🗑️</div>
            <div className="right-content">
              <strong>Art. 17 - Recht auf Löschung</strong>
              <p>Recht auf Löschung personenbezogener Daten (Recht auf Vergessenwerden)</p>
            </div>
          </div>

          <div className="right-item">
            <div className="right-icon">📊</div>
            <div className="right-content">
              <strong>Art. 20 - Recht auf Datenübertragbarkeit</strong>
              <p>Recht auf Erhalt der bereitgestellten Daten in strukturiertem Format</p>
            </div>
          </div>

          <div className="right-item">
            <div className="right-icon">🚫</div>
            <div className="right-content">
              <strong>Art. 21 - Widerspruchsrecht</strong>
              <p>Recht auf Widerspruch gegen die Verarbeitung</p>
            </div>
          </div>

          <div className="right-item">
            <div className="right-icon">⚖️</div>
            <div className="right-content">
              <strong>Art. 77 - Beschwerderecht</strong>
              <p>Recht auf Beschwerde bei einer Aufsichtsbehörde</p>
            </div>
          </div>
        </div>
      </div>

      {/* Audit Note */}
      <div className="audit-note">
        <p>
          🔒 Alle Änderungen werden gemäß DSGVO Art. 30 protokolliert und können im Audit-Log
          eingesehen werden. Der Kunde wird über wesentliche Änderungen informiert.
        </p>
      </div>
    </div>
  );
}
