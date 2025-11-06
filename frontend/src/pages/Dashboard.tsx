/**
 * Dashboard Page - Real-time overview of the goldsmith workshop
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getMaterials, type Material } from '../lib/api/materials';
import { getCustomers, getCustomerStatistics, type Customer, type CustomerStatistics } from '../lib/api/customers';
import { isRetentionExpiringSoon, formatCustomerName } from '../lib/api/customers';
import './Dashboard.css';

export default function Dashboard() {
  const navigate = useNavigate();

  // State
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Material data
  const [materials, setMaterials] = useState<Material[]>([]);
  const [lowStockMaterials, setLowStockMaterials] = useState<Material[]>([]);
  const [totalStockValue, setTotalStockValue] = useState(0);

  // Customer data
  const [recentCustomers, setRecentCustomers] = useState<Customer[]>([]);
  const [customerStats, setCustomerStats] = useState<CustomerStatistics | null>(null);
  const [retentionAlerts, setRetentionAlerts] = useState<Customer[]>([]);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch data in parallel
      const [materialsData, customersData, statsData] = await Promise.all([
        getMaterials({ limit: 100 }).catch(() => ({ items: [], total: 0, skip: 0, limit: 100, has_more: false })),
        getCustomers({ limit: 5, order_by: '-created_at' }).catch(() => ({ items: [], total: 0, skip: 0, limit: 5, has_more: false })),
        getCustomerStatistics().catch(() => null),
      ]);

      // Process materials
      setMaterials(materialsData.items);

      // Calculate stock value
      const stockValue = materialsData.items.reduce(
        (sum, mat) => sum + mat.stock * mat.unit_price,
        0
      );
      setTotalStockValue(stockValue);

      // Find low stock materials
      const lowStock = materialsData.items.filter(
        (mat) => mat.stock <= mat.min_stock
      ).slice(0, 5);
      setLowStockMaterials(lowStock);

      // Process customers
      setRecentCustomers(customersData.items);
      setCustomerStats(statsData);

      // Find retention alerts (customers with expiring retention)
      const alerts = customersData.items.filter((customer) =>
        isRetentionExpiringSoon(customer, 90) // 90 days warning
      );
      setRetentionAlerts(alerts);
    } catch (err: any) {
      setError('Fehler beim Laden des Dashboards');
      console.error('Dashboard error:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(price);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('de-DE', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  if (loading) {
    return (
      <div className="dashboard-loading">
        <div className="spinner"></div>
        <p>Lade Dashboard...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-error">
        <h2>❌ Fehler</h2>
        <p>{error}</p>
        <button onClick={loadDashboardData} className="btn-retry">
          Erneut versuchen
        </button>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1 className="page-title">📊 Dashboard</h1>
        <button onClick={loadDashboardData} className="btn-refresh">
          🔄 Aktualisieren
        </button>
      </div>

      {/* Statistics Cards */}
      <div className="dashboard-grid">
        <div className="stat-card stock-value">
          <div className="stat-icon">💰</div>
          <div className="stat-content">
            <div className="stat-label">Materialwert</div>
            <div className="stat-value">{formatPrice(totalStockValue)}</div>
            <div className="stat-detail">{materials.length} Materialien</div>
          </div>
        </div>

        <div className="stat-card customers">
          <div className="stat-icon">👥</div>
          <div className="stat-content">
            <div className="stat-label">Kunden</div>
            <div className="stat-value">{customerStats?.total_active_customers || 0}</div>
            <div className="stat-detail">
              {customerStats?.marketing_consent_customers || 0} Marketing-Einwilligung
            </div>
          </div>
        </div>

        <div className="stat-card low-stock">
          <div className="stat-icon">⚠️</div>
          <div className="stat-content">
            <div className="stat-label">Niedriger Bestand</div>
            <div className="stat-value">{lowStockMaterials.length}</div>
            <div className="stat-detail">Benötigt Nachbestellung</div>
          </div>
        </div>

        <div className="stat-card gdpr-alerts">
          <div className="stat-icon">🔒</div>
          <div className="stat-content">
            <div className="stat-label">DSGVO-Hinweise</div>
            <div className="stat-value">{retentionAlerts.length}</div>
            <div className="stat-detail">Aufbewahrung läuft ab</div>
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="dashboard-sections">
        {/* Low Stock Materials */}
        {lowStockMaterials.length > 0 && (
          <section className="dashboard-section low-stock-section">
            <div className="section-header">
              <h2>⚠️ Niedriger Bestand</h2>
              <button onClick={() => navigate('/materials')} className="btn-view-all">
                Alle anzeigen →
              </button>
            </div>

            <div className="low-stock-list">
              {lowStockMaterials.map((material) => (
                <div
                  key={material.id}
                  className="low-stock-item"
                  onClick={() => navigate(`/materials/${material.id}`)}
                >
                  <div className="material-info">
                    <strong>{material.name}</strong>
                    <span className="material-type">{material.material_type}</span>
                  </div>
                  <div className="stock-info">
                    <span className="stock-current">
                      {material.stock} {material.unit}
                    </span>
                    <span className="stock-min">Min: {material.min_stock}</span>
                  </div>
                  <div className="stock-status-indicator">
                    {material.stock === 0 ? '🔴' : '🟡'}
                  </div>
                </div>
              ))}
            </div>

            {lowStockMaterials.length === 0 && (
              <div className="empty-state">
                <p>✅ Alle Materialien haben ausreichend Bestand</p>
              </div>
            )}
          </section>
        )}

        {/* Recent Customers */}
        <section className="dashboard-section recent-customers-section">
          <div className="section-header">
            <h2>👥 Neue Kunden</h2>
            <button onClick={() => navigate('/customers')} className="btn-view-all">
              Alle anzeigen →
            </button>
          </div>

          <div className="recent-customers-list">
            {recentCustomers.map((customer) => (
              <div
                key={customer.id}
                className="recent-customer-item"
                onClick={() => navigate(`/customers/${customer.id}`)}
              >
                <div className="customer-avatar">
                  {customer.first_name[0]}{customer.last_name[0]}
                </div>
                <div className="customer-info">
                  <strong>{formatCustomerName(customer)}</strong>
                  <span className="customer-email">{customer.email}</span>
                </div>
                <div className="customer-meta">
                  <span className="customer-date">{formatDate(customer.created_at)}</span>
                  {customer.consent_marketing && (
                    <span className="consent-badge">📧 Marketing</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {recentCustomers.length === 0 && (
            <div className="empty-state">
              <p>Noch keine Kunden vorhanden</p>
              <button onClick={() => navigate('/customers/new')} className="btn-add">
                ➕ Kunde hinzufügen
              </button>
            </div>
          )}
        </section>

        {/* GDPR Retention Alerts */}
        {retentionAlerts.length > 0 && (
          <section className="dashboard-section gdpr-alerts-section">
            <div className="section-header">
              <h2>🔒 DSGVO-Hinweise</h2>
              <button onClick={() => navigate('/customers')} className="btn-view-all">
                Alle anzeigen →
              </button>
            </div>

            <div className="gdpr-alerts-list">
              {retentionAlerts.map((customer) => (
                <div
                  key={customer.id}
                  className="gdpr-alert-item"
                  onClick={() => navigate(`/customers/${customer.id}`)}
                >
                  <div className="alert-icon">⚠️</div>
                  <div className="alert-info">
                    <strong>{formatCustomerName(customer)}</strong>
                    <span className="alert-message">
                      Aufbewahrungsfrist läuft bald ab
                      {customer.retention_deadline && (
                        <> - {formatDate(customer.retention_deadline)}</>
                      )}
                    </span>
                  </div>
                  <div className="alert-action">→</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Quick Actions */}
        <section className="dashboard-section quick-actions-section">
          <h2>Schnellzugriff</h2>

          <div className="quick-actions-grid">
            <button
              className="quick-action-btn materials"
              onClick={() => navigate('/materials/new')}
            >
              <span className="action-icon">➕</span>
              <span className="action-label">Material hinzufügen</span>
            </button>

            <button
              className="quick-action-btn customers"
              onClick={() => navigate('/customers/new')}
            >
              <span className="action-icon">👤</span>
              <span className="action-label">Kunde hinzufügen</span>
            </button>

            <button
              className="quick-action-btn materials-list"
              onClick={() => navigate('/materials')}
            >
              <span className="action-icon">💎</span>
              <span className="action-label">Materialien anzeigen</span>
            </button>

            <button
              className="quick-action-btn customers-list"
              onClick={() => navigate('/customers')}
            >
              <span className="action-icon">👥</span>
              <span className="action-label">Kunden anzeigen</span>
            </button>
          </div>
        </section>

        {/* Welcome Section */}
        <section className="dashboard-section welcome-section">
          <h2>Willkommen im Goldsmith ERP</h2>
          <p>
            Ihr zentrales System für Material- und Kundenverwaltung mit vollständiger
            DSGVO-Compliance.
          </p>
          <div className="system-status">
            <span className="status-indicator">🟢</span>
            <span className="status-text">System läuft</span>
          </div>
        </section>
      </div>
    </div>
  );
}
