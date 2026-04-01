// Enhanced Dashboard Page Component (2025) - Role-Specific Views
import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts';
import { DashboardKPIs } from '../components/dashboard/DashboardKPIs';
import { AlertsWidget } from '../components/dashboard/AlertsWidget';
import { DeadlinesWidget } from '../components/dashboard/DeadlinesWidget';
import { ordersApi } from '../api';
import { handoffsApi } from '../api/handoffs';
import { OrderType } from '../types';
import '../styles/pages.css';
import '../styles/dashboard.css';

// ============================================================
// Goldsmith Dashboard View
// ============================================================
const GoldsmithDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [myOrders, setMyOrders] = useState<OrderType[]>([]);
  const [todayDeadlines, setTodayDeadlines] = useState<OrderType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [pendingHandoffs, setPendingHandoffs] = useState<any[]>([]);
  const [isLoadingHandoffs, setIsLoadingHandoffs] = useState(true);

  const fetchGoldsmithData = useCallback(async () => {
    try {
      setIsLoading(true);
      const ordersData = await ordersApi.getAll({ limit: 1000 });
      const ordersList = Array.isArray(ordersData) ? ordersData : ordersData.items || [];

      // "Meine Auftraege" - orders assigned to current user or in_progress
      const assigned = ordersList.filter(
        (o) => o.status === 'in_progress' || o.status === 'new'
      );
      setMyOrders(assigned);

      // "Heutige Deadlines" - orders due today
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const tomorrow = new Date(today);
      tomorrow.setDate(tomorrow.getDate() + 1);

      const dueTodayOrders = ordersList.filter((o) => {
        if (o.status === 'completed' || o.status === 'delivered') return false;
        if (!o.deadline) return false;
        const deadlineDate = new Date(o.deadline);
        deadlineDate.setHours(0, 0, 0, 0);
        return deadlineDate >= today && deadlineDate < tomorrow;
      });
      setTodayDeadlines(dueTodayOrders);
    } catch (err) {
      console.error('Fehler beim Laden der Goldschmied-Daten:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGoldsmithData();
  }, [fetchGoldsmithData]);

  useEffect(() => {
    const loadHandoffs = async () => {
      try {
        setIsLoadingHandoffs(true);
        const resp = await handoffsApi.getPending();
        const data = resp.data;
        setPendingHandoffs(Array.isArray(data) ? data : []);
      } catch {
        setPendingHandoffs([]);
      } finally {
        setIsLoadingHandoffs(false);
      }
    };
    loadHandoffs();
  }, []);

  const handleAcceptHandoff = async (id: number) => {
    try {
      await handoffsApi.accept(id);
      const resp = await handoffsApi.getPending();
      setPendingHandoffs(Array.isArray(resp.data) ? resp.data : []);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Annehmen der Übergabe');
    }
  };

  const handleDeclineHandoff = async (id: number) => {
    const reason = window.prompt('Begründung für die Ablehnung:');
    if (reason === null) return;
    try {
      await handoffsApi.decline(id, { response_notes: reason || 'Abgelehnt' });
      const resp = await handoffsApi.getPending();
      setPendingHandoffs(Array.isArray(resp.data) ? resp.data : []);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Ablehnen der Übergabe');
    }
  };

  return (
    <>
      {/* Meine Auftraege */}
      <section className="dashboard-section">
        <div className="widget-header">
          <span className="widget-header-icon">🔨</span>
          <h2>Meine Aufträge ({myOrders.length})</h2>
        </div>
        {isLoading ? (
          <div className="deadlines-loading">Lade Aufträge...</div>
        ) : myOrders.length === 0 ? (
          <div className="no-deadlines">
            <div className="no-deadlines-icon">✅</div>
            <p>Keine aktiven Aufträge vorhanden</p>
          </div>
        ) : (
          <div className="deadlines-list">
            {myOrders.slice(0, 8).map((order) => (
              <div
                key={order.id}
                className={`deadline-item ${order.status === 'in_progress' ? 'deadline-soon' : 'deadline-ok'}`}
                onClick={() => navigate(`/orders/${order.id}`)}
              >
                <div className="deadline-content">
                  <h4 className="deadline-title">{order.title}</h4>
                  <div className="deadline-meta">
                    <span className={`status-badge status-${order.status}`}>
                      {order.status === 'new' ? 'Neu' : 'In Bearbeitung'}
                    </span>
                    {order.deadline && (
                      <span className="deadline-date">
                        📅 {new Date(order.deadline).toLocaleDateString('de-DE')}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Heutige Deadlines */}
      <section className="dashboard-section">
        <div className="widget-header">
          <span className="widget-header-icon">🔴</span>
          <h2>Heutige Deadlines ({todayDeadlines.length})</h2>
        </div>
        {isLoading ? (
          <div className="deadlines-loading">Lade Deadlines...</div>
        ) : todayDeadlines.length === 0 ? (
          <div className="no-deadlines">
            <div className="no-deadlines-icon">✅</div>
            <p>Keine Deadlines heute</p>
          </div>
        ) : (
          <div className="deadlines-list">
            {todayDeadlines.map((order) => (
              <div
                key={order.id}
                className="deadline-item deadline-urgent"
                onClick={() => navigate(`/orders/${order.id}`)}
              >
                <div className="deadline-badge deadline-urgent">
                  <div className="deadline-days">!</div>
                  <div className="deadline-label">HEUTE</div>
                </div>
                <div className="deadline-content">
                  <h4 className="deadline-title">{order.title}</h4>
                  <div className="deadline-meta">
                    {order.customer && (
                      <span className="deadline-customer">
                        👤 {order.customer.first_name} {order.customer.last_name}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Offene Übergaben */}
      <section className="dashboard-section">
        <div className="widget-header">
          <span className="widget-header-icon">🤝</span>
          <h2>Offene Übergaben ({pendingHandoffs.length})</h2>
        </div>
        {isLoadingHandoffs ? (
          <div className="deadlines-loading">Lade Übergaben...</div>
        ) : pendingHandoffs.length === 0 ? (
          <div className="no-deadlines">
            <div className="no-deadlines-icon">✅</div>
            <p>Keine offenen Übergaben</p>
          </div>
        ) : (
          <div className="deadlines-list">
            {pendingHandoffs.map((handoff) => (
              <div
                key={handoff.id}
                className="deadline-item deadline-soon"
                style={{ cursor: 'default' }}
              >
                <div className="deadline-content">
                  <h4 className="deadline-title">
                    Auftrag #{handoff.order_id} — {handoff.handoff_type}
                  </h4>
                  <div className="deadline-meta">
                    <span className="deadline-customer">
                      Von: {handoff.from_user?.full_name || `#${handoff.from_user_id}`}
                    </span>
                    {handoff.notes && (
                      <span style={{ fontStyle: 'italic', color: '#6b7280' }}>
                        {handoff.notes}
                      </span>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
                  <button
                    style={{
                      background: '#10b981',
                      color: 'white',
                      border: 'none',
                      padding: '0.5rem 1rem',
                      borderRadius: '6px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      minHeight: '44px',
                      fontSize: '0.875rem',
                    }}
                    onClick={() => handleAcceptHandoff(handoff.id)}
                  >
                    Annehmen
                  </button>
                  <button
                    style={{
                      background: 'white',
                      color: '#dc2626',
                      border: '2px solid #ef4444',
                      padding: '0.5rem 1rem',
                      borderRadius: '6px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      minHeight: '44px',
                      fontSize: '0.875rem',
                    }}
                    onClick={() => handleDeclineHandoff(handoff.id)}
                  >
                    Ablehnen
                  </button>
                  <button
                    style={{
                      background: 'white',
                      color: '#6b7280',
                      border: '2px solid #e5e7eb',
                      padding: '0.5rem 1rem',
                      borderRadius: '6px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      minHeight: '44px',
                      fontSize: '0.875rem',
                    }}
                    onClick={() => navigate(`/orders/${handoff.order_id}`)}
                  >
                    Auftrag
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Quick Action: Zeiterfassung starten */}
      <section className="dashboard-section">
        <div className="widget-header">
          <span className="widget-header-icon">⏱️</span>
          <h2>Schnellaktionen</h2>
        </div>
        <div className="dashboard-quick-actions">
          <button
            className="btn-quick-action"
            onClick={() => navigate('/time-tracking')}
          >
            ⏱️ Zeiterfassung starten
          </button>
          <button
            className="btn-quick-action"
            onClick={() => navigate('/scanner')}
          >
            📱 QR-Scanner öffnen
          </button>
        </div>
      </section>
    </>
  );
};

// ============================================================
// Admin / Office Staff Dashboard View
// ============================================================
const AdminDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [newOrders, setNewOrders] = useState<OrderType[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchNewOrders = useCallback(async () => {
    try {
      setIsLoading(true);
      const ordersData = await ordersApi.getAll({ limit: 1000 });
      const ordersList = Array.isArray(ordersData) ? ordersData : ordersData.items || [];
      const filtered = ordersList.filter((o) => o.status === 'new');
      setNewOrders(filtered);
    } catch (err) {
      console.error('Fehler beim Laden der neuen Aufträge:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNewOrders();
  }, [fetchNewOrders]);

  return (
    <>
      {/* KPI Cards - Top Section (F-Pattern Layout) */}
      <section className="dashboard-section kpis-section">
        <DashboardKPIs />
      </section>

      {/* Main Content Grid */}
      <div className="dashboard-main-grid">
        {/* Left Column: Alerts */}
        <section className="dashboard-section alerts-section">
          <AlertsWidget />
        </section>

        {/* Right Column: Deadlines */}
        <section className="dashboard-section deadlines-section">
          <DeadlinesWidget />
        </section>
      </div>

      {/* Neue Auftraege Section */}
      <section className="dashboard-section">
        <div className="widget-header">
          <span className="widget-header-icon">🆕</span>
          <h2>Neue Aufträge ({newOrders.length})</h2>
        </div>
        {isLoading ? (
          <div className="deadlines-loading">Lade neue Aufträge...</div>
        ) : newOrders.length === 0 ? (
          <div className="no-deadlines">
            <div className="no-deadlines-icon">✅</div>
            <p>Keine neuen Aufträge vorhanden</p>
          </div>
        ) : (
          <div className="deadlines-list">
            {newOrders.slice(0, 5).map((order) => (
              <div
                key={order.id}
                className="deadline-item deadline-ok"
                onClick={() => navigate(`/orders/${order.id}`)}
              >
                <div className="deadline-content">
                  <h4 className="deadline-title">{order.title}</h4>
                  <div className="deadline-meta">
                    <span className="status-badge status-new">Neu</span>
                    {order.customer && (
                      <span className="deadline-customer">
                        👤 {order.customer.first_name} {order.customer.last_name}
                      </span>
                    )}
                    {order.deadline && (
                      <span className="deadline-date">
                        📅 {new Date(order.deadline).toLocaleDateString('de-DE')}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
};

// ============================================================
// Viewer Dashboard View (Read-Only, Simplified)
// ============================================================
const ViewerDashboard: React.FC = () => {
  const [orderStats, setOrderStats] = useState<{
    total: number;
    newCount: number;
    inProgress: number;
    completed: number;
  }>({ total: 0, newCount: 0, inProgress: 0, completed: 0 });
  const [isLoading, setIsLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    try {
      setIsLoading(true);
      const ordersData = await ordersApi.getAll({ limit: 1000 });
      const ordersList = Array.isArray(ordersData) ? ordersData : ordersData.items || [];

      setOrderStats({
        total: ordersList.length,
        newCount: ordersList.filter((o) => o.status === 'new').length,
        inProgress: ordersList.filter((o) => o.status === 'in_progress').length,
        completed: ordersList.filter(
          (o) => o.status === 'completed' || o.status === 'delivered'
        ).length,
      });
    } catch (err) {
      console.error('Fehler beim Laden der Statistiken:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  return (
    <>
      {/* Order Stats */}
      <section className="dashboard-section">
        <div className="widget-header">
          <span className="widget-header-icon">📊</span>
          <h2>Auftragsübersicht</h2>
        </div>
        {isLoading ? (
          <div className="deadlines-loading">Lade Statistiken...</div>
        ) : (
          <div className="stats-grid">
            <div className="stat-card">
              <h3>Gesamt</h3>
              <p className="stat-value">{orderStats.total}</p>
            </div>
            <div className="stat-card">
              <h3>Neu</h3>
              <p className="stat-value">{orderStats.newCount}</p>
            </div>
            <div className="stat-card">
              <h3>In Bearbeitung</h3>
              <p className="stat-value">{orderStats.inProgress}</p>
            </div>
            <div className="stat-card">
              <h3>Abgeschlossen</h3>
              <p className="stat-value">{orderStats.completed}</p>
            </div>
          </div>
        )}
      </section>

      {/* Upcoming Deadlines (read-only) */}
      <section className="dashboard-section deadlines-section">
        <DeadlinesWidget />
      </section>
    </>
  );
};

// ============================================================
// Main Dashboard Page - Role Router
// ============================================================
export const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const userRole = user?.role || 'admin';

  const getRoleLabel = (role: string): string => {
    switch (role) {
      case 'goldsmith':
        return 'Goldschmied';
      case 'viewer':
        return 'Betrachter';
      case 'admin':
      default:
        return 'Administrator';
    }
  };

  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <div>
          <h1>Dashboard</h1>
          <p className="dashboard-welcome">
            Willkommen, {user?.first_name || user?.email}!
            <span className="dashboard-role-badge">
              {getRoleLabel(userRole)}
            </span>
          </p>
        </div>
        <div className="dashboard-timestamp">
          <span className="timestamp-label">Zuletzt aktualisiert:</span>
          <span className="timestamp-value">{new Date().toLocaleString('de-DE')}</span>
        </div>
      </header>

      {/* Role-specific content */}
      {userRole === 'goldsmith' && <GoldsmithDashboard />}
      {userRole === 'viewer' && <ViewerDashboard />}
      {(userRole === 'admin' || (userRole !== 'goldsmith' && userRole !== 'viewer')) && (
        <AdminDashboard />
      )}

      {/* Footer Info */}
      <footer className="dashboard-footer">
        <p className="dashboard-info">
          💡 <strong>Tipp:</strong>{' '}
          {userRole === 'goldsmith'
            ? 'Klicken Sie auf einen Auftrag für Details'
            : userRole === 'viewer'
              ? 'Sie haben Lesezugriff auf das Dashboard'
              : 'Klicken Sie auf die KPI-Karten für weitere Details'}
        </p>
      </footer>
    </div>
  );
};
