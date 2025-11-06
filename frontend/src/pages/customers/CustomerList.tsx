/**
 * Customer List Page - GDPR-Compliant Customer Management
 * Displays customers with search, filtering, and GDPR compliance indicators
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getCustomers,
  searchCustomers,
  deleteCustomer,
  formatCustomerName,
  formatCustomerAddress,
  getCustomerInitials,
  hasMarketingConsent,
  isRetentionExpiringSoon,
  getLegalBasisLabel,
} from '../../lib/api/customers';
import type { Customer, CustomerList as CustomerListType } from '../../types';
import './CustomerList.css';

export default function CustomerList() {
  const navigate = useNavigate();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState<'all' | 'active' | 'inactive'>('active');
  const [showDeleted, setShowDeleted] = useState(false);

  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCustomers, setTotalCustomers] = useState(0);
  const limit = 20;

  useEffect(() => {
    loadCustomers();
  }, [page, activeFilter, showDeleted]);

  const loadCustomers = async () => {
    try {
      setLoading(true);
      setError(null);

      const params: any = {
        skip: (page - 1) * limit,
        limit,
        include_deleted: showDeleted,
      };

      if (activeFilter === 'active') {
        params.is_active = true;
      } else if (activeFilter === 'inactive') {
        params.is_active = false;
      }

      const response = await getCustomers(params);
      setCustomers(response.items);
      setTotalCustomers(response.total);
      setTotalPages(Math.ceil(response.total / limit));
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Kunden');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!searchQuery.trim()) {
      loadCustomers();
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const results = await searchCustomers({
        query: searchQuery,
        skip: 0,
        limit: 100,
        include_deleted: showDeleted,
      });

      setCustomers(results);
      setTotalCustomers(results.length);
      setTotalPages(1);
      setPage(1);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler bei der Suche');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (customer: Customer) => {
    const confirmMessage = `Möchten Sie den Kunden "${formatCustomerName(customer)}" wirklich löschen?

Dies ist ein Soft-Delete (DSGVO-konform). Der Kunde wird als gelöscht markiert, aber die Daten bleiben erhalten.`;

    if (!confirm(confirmMessage)) {
      return;
    }

    const reason = prompt('Grund für die Löschung (optional):');

    try {
      await deleteCustomer(customer.id, false, reason || 'Manuelles Löschen');
      loadCustomers();
    } catch (err: any) {
      alert(`Fehler beim Löschen: ${err.response?.data?.detail || 'Unbekannter Fehler'}`);
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('de-DE');
  };

  const getCustomerStatusBadge = (customer: Customer) => {
    if (customer.is_deleted) {
      return { status: 'deleted', label: 'Gelöscht', color: '#6b7280' };
    }
    if (!customer.is_active) {
      return { status: 'inactive', label: 'Inaktiv', color: '#f59e0b' };
    }
    if (isRetentionExpiringSoon(customer)) {
      return { status: 'expiring', label: 'Läuft ab', color: '#f59e0b' };
    }
    return { status: 'active', label: 'Aktiv', color: '#10b981' };
  };

  return (
    <div className="customer-list-container">
      <div className="customer-list-header">
        <div className="header-top">
          <h1>👥 Kunden-Verwaltung</h1>
          <button
            className="btn-add-customer"
            onClick={() => navigate('/customers/new')}
          >
            ➕ Kunde hinzufügen
          </button>
        </div>

        {/* Statistics Summary */}
        <div className="statistics-summary">
          <div className="stat-card">
            <span className="stat-label">Gesamt:</span>
            <span className="stat-value">{totalCustomers}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Aktiv:</span>
            <span className="stat-value">{customers.filter(c => c.is_active && !c.is_deleted).length}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Marketing-Einwilligung:</span>
            <span className="stat-value">{customers.filter(c => hasMarketingConsent(c)).length}</span>
          </div>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="filters-section">
        <form onSubmit={handleSearch} className="search-form">
          <input
            type="text"
            placeholder="🔍 Kunde suchen (Name, E-Mail, Kundennummer)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />
          <button type="submit" className="btn-search">
            Suchen
          </button>
          {searchQuery && (
            <button
              type="button"
              className="btn-clear"
              onClick={() => {
                setSearchQuery('');
                loadCustomers();
              }}
            >
              ✕
            </button>
          )}
        </form>

        <div className="filter-controls">
          <select
            value={activeFilter}
            onChange={(e) => {
              setActiveFilter(e.target.value as any);
              setPage(1);
            }}
            className="filter-select"
          >
            <option value="all">Alle Kunden</option>
            <option value="active">Nur Aktive</option>
            <option value="inactive">Nur Inaktive</option>
          </select>

          <label className="filter-checkbox">
            <input
              type="checkbox"
              checked={showDeleted}
              onChange={(e) => {
                setShowDeleted(e.target.checked);
                setPage(1);
              }}
            />
            <span>🗑️ Gelöschte anzeigen</span>
          </label>
        </div>
      </div>

      {/* GDPR Info Banner */}
      <div className="gdpr-info-banner">
        <span className="gdpr-icon">🔒</span>
        <span className="gdpr-text">
          DSGVO-konforme Verwaltung | Alle Zugriffe werden protokolliert (Art. 30 DSGVO)
        </span>
      </div>

      {/* Error Display */}
      {error && (
        <div className="error-banner">
          ❌ {error}
        </div>
      )}

      {/* Loading State */}
      {loading ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Lade Kunden...</p>
        </div>
      ) : (
        <>
          {/* Customers Table */}
          <div className="customers-table-wrapper">
            <table className="customers-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Kunde</th>
                  <th>Kontakt</th>
                  <th>Kundennummer</th>
                  <th>Rechtsgrundlage</th>
                  <th>Einwilligungen</th>
                  <th>Erstellt</th>
                  <th className="actions-col">Aktionen</th>
                </tr>
              </thead>
              <tbody>
                {customers.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="no-results">
                      {searchQuery
                        ? `Keine Kunden gefunden für "${searchQuery}"`
                        : 'Keine Kunden vorhanden. Fügen Sie den ersten Kunden hinzu!'
                      }
                    </td>
                  </tr>
                ) : (
                  customers.map((customer) => {
                    const statusBadge = getCustomerStatusBadge(customer);

                    return (
                      <tr
                        key={customer.id}
                        className={`customer-row status-${statusBadge.status}`}
                        onClick={() => navigate(`/customers/${customer.id}`)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td>
                          <div className="status-cell">
                            <span
                              className="status-badge"
                              style={{ backgroundColor: statusBadge.color }}
                            >
                              {statusBadge.label}
                            </span>
                            {isRetentionExpiringSoon(customer) && (
                              <span className="retention-warning" title="Aufbewahrungsfrist läuft bald ab">
                                ⏰
                              </span>
                            )}
                          </div>
                        </td>

                        <td className="customer-name-cell">
                          <div className="customer-avatar">
                            {getCustomerInitials(customer)}
                          </div>
                          <div className="customer-info">
                            <strong>{formatCustomerName(customer)}</strong>
                            {customer.notes && (
                              <div className="customer-notes" title={customer.notes}>
                                📝 {customer.notes.substring(0, 40)}{customer.notes.length > 40 ? '...' : ''}
                              </div>
                            )}
                          </div>
                        </td>

                        <td className="contact-cell">
                          <div className="contact-info">
                            <div>📧 {customer.email}</div>
                            {customer.phone && <div>📞 {customer.phone}</div>}
                            {customer.city && <div>📍 {customer.city}, {customer.country}</div>}
                          </div>
                        </td>

                        <td>
                          <code className="customer-number">{customer.customer_number}</code>
                        </td>

                        <td>
                          <span className="legal-basis-badge">
                            {getLegalBasisLabel(customer.legal_basis)}
                          </span>
                        </td>

                        <td className="consents-cell">
                          <div className="consent-indicators">
                            {customer.consent_marketing && (
                              <span className="consent-badge consent-yes" title="Marketing-Einwilligung">
                                📧 Marketing
                              </span>
                            )}
                            {customer.email_communication_consent && (
                              <span className="consent-badge consent-yes" title="E-Mail-Kommunikation">
                                ✉️ E-Mail
                              </span>
                            )}
                            {customer.phone_communication_consent && (
                              <span className="consent-badge consent-yes" title="Telefon-Kommunikation">
                                📞 Telefon
                              </span>
                            )}
                            {!customer.consent_marketing &&
                             !customer.email_communication_consent &&
                             !customer.phone_communication_consent && (
                              <span className="consent-badge consent-no">
                                Keine
                              </span>
                            )}
                          </div>
                        </td>

                        <td>{formatDate(customer.created_at)}</td>

                        <td className="actions-cell" onClick={(e) => e.stopPropagation()}>
                          <div className="action-buttons">
                            <button
                              className="btn-action btn-view"
                              onClick={() => navigate(`/customers/${customer.id}`)}
                              title="Details anzeigen"
                            >
                              👁️
                            </button>
                            <button
                              className="btn-action btn-edit"
                              onClick={() => navigate(`/customers/${customer.id}/edit`)}
                              title="Bearbeiten"
                              disabled={customer.is_deleted}
                            >
                              ✏️
                            </button>
                            <button
                              className="btn-action btn-consent"
                              onClick={() => navigate(`/customers/${customer.id}/consent`)}
                              title="Einwilligungen verwalten"
                              disabled={customer.is_deleted}
                            >
                              🔐
                            </button>
                            <button
                              className="btn-action btn-delete"
                              onClick={() => handleDelete(customer)}
                              title="Löschen (Soft Delete)"
                              disabled={customer.is_deleted}
                            >
                              🗑️
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="btn-page"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
              >
                ← Zurück
              </button>
              <span className="page-info">
                Seite {page} von {totalPages} ({totalCustomers} Kunden gesamt)
              </span>
              <button
                className="btn-page"
                disabled={page === totalPages}
                onClick={() => setPage(page + 1)}
              >
                Weiter →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
