/**
 * Customer Detail Page - GDPR-Compliant Customer View
 * Displays complete customer information with GDPR compliance indicators
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getCustomer,
  deleteCustomer,
  exportCustomerData,
  downloadCustomerData,
  anonymizeCustomer,
  formatCustomerName,
  formatCustomerAddress,
  getCustomerInitials,
  getLegalBasisLabel,
  getLegalBasisDescription,
  isRetentionExpiringSoon,
  isRetentionExpired,
  hasMarketingConsent,
  type Customer,
} from '../../lib/api/customers';
import './CustomerDetail.css';

export default function CustomerDetail() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [anonymizing, setAnonymizing] = useState(false);

  useEffect(() => {
    if (id) {
      loadCustomer(parseInt(id));
    }
  }, [id]);

  const loadCustomer = async (customerId: number) => {
    try {
      setLoading(true);
      setError(null);
      const data = await getCustomer(customerId);
      setCustomer(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden des Kunden');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!customer) return;

    const confirmMessage = `Möchten Sie den Kunden "${formatCustomerName(customer)}" wirklich löschen?\n\nDies ist ein Soft-Delete (DSGVO-konform). Der Kunde wird als gelöscht markiert, aber die Daten bleiben erhalten.`;

    if (!confirm(confirmMessage)) {
      return;
    }

    const reason = prompt('Grund für die Löschung (optional):');

    try {
      await deleteCustomer(customer.id, false, reason || 'Manuelles Löschen');
      navigate('/customers');
    } catch (err: any) {
      alert(`Fehler beim Löschen: ${err.response?.data?.detail || 'Unbekannter Fehler'}`);
    }
  };

  const handleExportData = async () => {
    if (!customer) return;

    try {
      setExporting(true);
      await downloadCustomerData(customer.id, formatCustomerName(customer));
      alert('Kundendaten erfolgreich exportiert! (DSGVO Art. 15 - Auskunftsrecht)');
    } catch (err: any) {
      alert(`Fehler beim Exportieren: ${err.response?.data?.detail || 'Unbekannter Fehler'}`);
    } finally {
      setExporting(false);
    }
  };

  const handleAnonymize = async () => {
    if (!customer) return;

    const confirmMessage = `WARNUNG: Möchten Sie den Kunden "${formatCustomerName(customer)}" wirklich anonymisieren?\n\nDies ist NICHT rückgängig zu machen! Alle personenbezogenen Daten werden permanent entfernt.\n\nNur statistische Daten bleiben erhalten (DSGVO Art. 17 - Recht auf Vergessenwerden).`;

    if (!confirm(confirmMessage)) {
      return;
    }

    const reason = prompt('Grund für die Anonymisierung (erforderlich):');

    if (!reason || reason.trim().length < 5) {
      alert('Bitte geben Sie einen ausführlichen Grund für die Anonymisierung an.');
      return;
    }

    try {
      setAnonymizing(true);
      await anonymizeCustomer(customer.id, reason);
      alert('Kunde erfolgreich anonymisiert.');
      navigate('/customers');
    } catch (err: any) {
      alert(`Fehler beim Anonymisieren: ${err.response?.data?.detail || 'Unbekannter Fehler'}`);
    } finally {
      setAnonymizing(false);
    }
  };

  const getCustomerStatusBadge = () => {
    if (!customer) return { label: 'Unbekannt', color: '#6b7280' };

    if (customer.is_deleted) {
      return { label: 'Gelöscht', color: '#6b7280' };
    }
    if (!customer.is_active) {
      return { label: 'Inaktiv', color: '#f59e0b' };
    }
    if (isRetentionExpired(customer)) {
      return { label: 'Aufbewahrung abgelaufen', color: '#dc2626' };
    }
    if (isRetentionExpiringSoon(customer)) {
      return { label: 'Läuft bald ab', color: '#f59e0b' };
    }
    return { label: 'Aktiv', color: '#10b981' };
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('de-DE', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const formatDateTime = (dateString?: string) => {
    if (!dateString) return '-';
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
      <div className="customer-detail-loading">
        <div className="spinner"></div>
        <p>Lade Kundendaten...</p>
      </div>
    );
  }

  if (error || !customer) {
    return (
      <div className="customer-detail-error">
        <h2>❌ Fehler</h2>
        <p>{error || 'Kunde nicht gefunden'}</p>
        <button onClick={() => navigate('/customers')} className="btn-back">
          Zurück zur Liste
        </button>
      </div>
    );
  }

  const statusBadge = getCustomerStatusBadge();

  return (
    <div className="customer-detail-container">
      {/* Header */}
      <div className="detail-header">
        <button onClick={() => navigate('/customers')} className="btn-back-small">
          ← Zurück
        </button>
        <div className="header-actions">
          <button
            onClick={() => navigate(`/customers/${customer.id}/edit`)}
            className="btn-edit"
            disabled={customer.is_deleted}
          >
            ✏️ Bearbeiten
          </button>
          <button
            onClick={() => navigate(`/customers/${customer.id}/consent`)}
            className="btn-consent"
            disabled={customer.is_deleted}
          >
            🔐 Einwilligungen
          </button>
          <button onClick={handleDelete} className="btn-delete" disabled={customer.is_deleted}>
            🗑️ Löschen
          </button>
        </div>
      </div>

      {/* GDPR Warning Banner */}
      {(isRetentionExpired(customer) || isRetentionExpiringSoon(customer)) && (
        <div className="gdpr-warning-banner">
          <span className="warning-icon">⚠️</span>
          <div className="warning-content">
            <strong>DSGVO-Hinweis:</strong>
            {isRetentionExpired(customer) ? (
              <span>
                Die Aufbewahrungsfrist ist abgelaufen! Bitte prüfen Sie, ob die Daten noch
                benötigt werden oder gelöscht werden sollten.
              </span>
            ) : (
              <span>
                Die Aufbewahrungsfrist läuft in Kürze ab. Bitte prüfen Sie die Datenverarbeitung.
              </span>
            )}
          </div>
        </div>
      )}

      {/* Customer Info Card */}
      <div className="customer-info-card">
        <div className="info-header">
          <div className="header-left">
            <div className="customer-avatar-large">{getCustomerInitials(customer)}</div>
            <div>
              <h1>{formatCustomerName(customer)}</h1>
              <p className="customer-number-display">
                Kundennummer: <code>{customer.customer_number}</code>
              </p>
            </div>
          </div>
          <span className="status-badge-large" style={{ backgroundColor: statusBadge.color }}>
            {statusBadge.label}
          </span>
        </div>

        {/* Contact Information */}
        <div className="info-section">
          <h2>Kontaktinformationen</h2>
          <div className="info-grid">
            <div className="info-item">
              <span className="info-label">📧 E-Mail</span>
              <span className="info-value">
                <a href={`mailto:${customer.email}`}>{customer.email}</a>
              </span>
            </div>

            {customer.phone && (
              <div className="info-item">
                <span className="info-label">📞 Telefon</span>
                <span className="info-value">
                  <a href={`tel:${customer.phone}`}>{customer.phone}</a>
                </span>
              </div>
            )}

            {customer.address_line1 && (
              <div className="info-item full-width">
                <span className="info-label">📍 Adresse</span>
                <span className="info-value">{formatCustomerAddress(customer)}</span>
              </div>
            )}
          </div>
        </div>

        {/* GDPR Compliance Information */}
        <div className="info-section gdpr-section">
          <h2>🔒 DSGVO-Compliance</h2>
          <div className="info-grid">
            <div className="info-item">
              <span className="info-label">Rechtsgrundlage</span>
              <span className="info-value">
                <span className="legal-basis-badge">
                  {getLegalBasisLabel(customer.legal_basis)}
                </span>
                <small className="legal-basis-description">
                  {getLegalBasisDescription(customer.legal_basis)}
                </small>
              </span>
            </div>

            <div className="info-item">
              <span className="info-label">Datenverarbeitungseinwilligung</span>
              <span className="info-value">
                <span className={`consent-indicator ${customer.data_processing_consent ? 'yes' : 'no'}`}>
                  {customer.data_processing_consent ? '✓ Erteilt' : '✗ Nicht erteilt'}
                </span>
              </span>
            </div>

            {customer.consent_date && (
              <div className="info-item">
                <span className="info-label">Einwilligungsdatum</span>
                <span className="info-value">{formatDate(customer.consent_date)}</span>
              </div>
            )}

            {customer.consent_version && (
              <div className="info-item">
                <span className="info-label">Einwilligungsversion</span>
                <span className="info-value">{customer.consent_version}</span>
              </div>
            )}

            <div className="info-item">
              <span className="info-label">Datenkategorie</span>
              <span className="info-value">{customer.data_retention_category}</span>
            </div>

            {customer.retention_deadline && (
              <div className="info-item">
                <span className="info-label">Aufbewahrungsfrist bis</span>
                <span className="info-value">
                  {formatDate(customer.retention_deadline)}
                  {isRetentionExpired(customer) && (
                    <span className="retention-expired"> (Abgelaufen!)</span>
                  )}
                  {isRetentionExpiringSoon(customer) && !isRetentionExpired(customer) && (
                    <span className="retention-expiring"> (Läuft bald ab)</span>
                  )}
                </span>
              </div>
            )}

            {customer.last_order_date && (
              <div className="info-item">
                <span className="info-label">Letzte Bestellung</span>
                <span className="info-value">{formatDate(customer.last_order_date)}</span>
              </div>
            )}
          </div>
        </div>

        {/* Consent Status */}
        <div className="info-section">
          <h2>Einwilligungen</h2>
          <div className="consent-grid">
            <div className="consent-item">
              <span className="consent-label">📧 Marketing-Einwilligung</span>
              <span className={`consent-status ${customer.consent_marketing ? 'yes' : 'no'}`}>
                {customer.consent_marketing ? '✓ Erteilt' : '✗ Nicht erteilt'}
              </span>
            </div>

            <div className="consent-item">
              <span className="consent-label">✉️ E-Mail-Kommunikation</span>
              <span className={`consent-status ${customer.email_communication_consent ? 'yes' : 'no'}`}>
                {customer.email_communication_consent ? '✓ Erteilt' : '✗ Nicht erteilt'}
              </span>
            </div>

            <div className="consent-item">
              <span className="consent-label">📞 Telefon-Kommunikation</span>
              <span className={`consent-status ${customer.phone_communication_consent ? 'yes' : 'no'}`}>
                {customer.phone_communication_consent ? '✓ Erteilt' : '✗ Nicht erteilt'}
              </span>
            </div>

            {customer.sms_communication_consent !== undefined && (
              <div className="consent-item">
                <span className="consent-label">💬 SMS-Kommunikation</span>
                <span className={`consent-status ${customer.sms_communication_consent ? 'yes' : 'no'}`}>
                  {customer.sms_communication_consent ? '✓ Erteilt' : '✗ Nicht erteilt'}
                </span>
              </div>
            )}
          </div>

          <button
            onClick={() => navigate(`/customers/${customer.id}/consent`)}
            className="btn-manage-consents"
            disabled={customer.is_deleted}
          >
            🔐 Einwilligungen verwalten
          </button>
        </div>

        {/* Notes */}
        {customer.notes && (
          <div className="info-section">
            <h2>Notizen</h2>
            <div className="notes-content">{customer.notes}</div>
          </div>
        )}

        {/* Tags */}
        {customer.tags && customer.tags.length > 0 && (
          <div className="info-section">
            <h2>Tags</h2>
            <div className="tags-container">
              {customer.tags.map((tag, index) => (
                <span key={index} className="tag-badge">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Audit Information */}
        <div className="info-footer">
          <small>Erstellt: {formatDateTime(customer.created_at)}</small>
          {customer.updated_at && <small>Aktualisiert: {formatDateTime(customer.updated_at)}</small>}
          {customer.is_deleted && customer.deleted_at && (
            <small className="deleted-info">
              Gelöscht: {formatDateTime(customer.deleted_at)}
              {customer.deletion_reason && ` (${customer.deletion_reason})`}
            </small>
          )}
        </div>
      </div>

      {/* GDPR Actions Card */}
      <div className="gdpr-actions-card">
        <h2>🔒 DSGVO-Aktionen</h2>
        <div className="gdpr-actions-grid">
          <button
            onClick={handleExportData}
            disabled={exporting || customer.is_deleted}
            className="btn-gdpr-action export"
          >
            <span className="action-icon">📥</span>
            <span className="action-label">Daten exportieren</span>
            <small className="action-description">Art. 15 - Auskunftsrecht</small>
          </button>

          <button
            onClick={() => navigate(`/customers/${customer.id}/consent`)}
            disabled={customer.is_deleted}
            className="btn-gdpr-action consent"
          >
            <span className="action-icon">🔐</span>
            <span className="action-label">Einwilligungen verwalten</span>
            <small className="action-description">Art. 7 - Einwilligungsverwaltung</small>
          </button>

          <button
            onClick={handleAnonymize}
            disabled={anonymizing || customer.is_deleted}
            className="btn-gdpr-action anonymize"
          >
            <span className="action-icon">🔒</span>
            <span className="action-label">Kunde anonymisieren</span>
            <small className="action-description">Art. 17 - Recht auf Vergessenwerden</small>
          </button>

          <button
            onClick={handleDelete}
            disabled={customer.is_deleted}
            className="btn-gdpr-action delete"
          >
            <span className="action-icon">🗑️</span>
            <span className="action-label">Soft Delete</span>
            <small className="action-description">DSGVO-konformes Löschen</small>
          </button>
        </div>

        <div className="gdpr-info-text">
          <strong>Hinweis:</strong> Alle Aktionen werden gemäß DSGVO Art. 30 protokolliert.
          Der Kunde wird über Änderungen informiert, sofern rechtlich erforderlich.
        </div>
      </div>

      {/* Audit Log Preview */}
      <div className="audit-log-card">
        <h2>📋 Prüfprotokoll</h2>
        <div className="coming-soon">
          📊 Vollständiges Prüfprotokoll wird in einer zukünftigen Version verfügbar sein.
          <br />
          <small>(DSGVO Art. 30 - Verzeichnis von Verarbeitungstätigkeiten)</small>
        </div>
      </div>
    </div>
  );
}
