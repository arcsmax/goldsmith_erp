// Enhanced Dashboard Page Component (2025) - Role-Specific Views
import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth, useToast } from '../contexts';
import { DashboardKPIs } from '../components/dashboard/DashboardKPIs';
import { AlertsWidget } from '../components/dashboard/AlertsWidget';
import { DeadlinesWidget } from '../components/dashboard/DeadlinesWidget';
import { ordersApi } from '../api';
import { handoffsApi } from '../api/handoffs';
import { OrderType } from '../types';
import '../styles/pages.css';
import '../styles/dashboard.css';

// ============================================================
// Goldsmith Dashboard — unified work queue
// ============================================================

interface TodoItem {
  id: string;
  type: 'handoff' | 'deadline' | 'fitting' | 'order';
  priority: 'urgent' | 'high' | 'medium' | 'low';
  title: string;
  subtitle: string;
  deadline?: string;
  orderId?: number;
  handoffId?: number;
  action: string;
  /** Raw handoff object, only present for type === 'handoff' */
  handoffData?: any;
}

// Priority sort order: urgent first
const PRIORITY_ORDER: Record<TodoItem['priority'], number> = {
  urgent: 0,
  high: 1,
  medium: 2,
  low: 3,
};

const PRIORITY_BORDER: Record<TodoItem['priority'], string> = {
  urgent: '#dc2626',
  high: '#f59e0b',
  medium: '#eab308',
  low: '#3b82f6',
};

const PRIORITY_BG: Record<TodoItem['priority'], string> = {
  urgent: '#fef2f2',
  high: '#fffbeb',
  medium: '#fefce8',
  low: '#eff6ff',
};

const PRIORITY_BADGE_BG: Record<TodoItem['priority'], string> = {
  urgent: '#dc2626',
  high: '#f59e0b',
  medium: '#eab308',
  low: '#3b82f6',
};

const PRIORITY_LABEL: Record<TodoItem['priority'], string> = {
  urgent: 'DRINGEND',
  high: 'HOCH',
  medium: 'MITTEL',
  low: 'NORMAL',
};

function formatRelativeDeadline(deadlineStr: string): string {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const deadline = new Date(deadlineStr);
  deadline.setHours(0, 0, 0, 0);
  const diffDays = Math.round((deadline.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays < 0) return `${Math.abs(diffDays)} Tag${Math.abs(diffDays) === 1 ? '' : 'e'} überfällig`;
  if (diffDays === 0) return 'heute';
  if (diffDays === 1) return 'morgen';
  return `in ${diffDays} Tagen`;
}

function buildTodoList(orders: OrderType[], handoffs: any[]): TodoItem[] {
  const items: TodoItem[] = [];

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const in3Days = new Date(today);
  in3Days.setDate(today.getDate() + 3);

  // Pending handoffs — always URGENT
  for (const handoff of handoffs) {
    items.push({
      id: `handoff-${handoff.id}`,
      type: 'handoff',
      priority: 'urgent',
      title: `Übergabe: Auftrag #${handoff.order_id} — ${handoff.handoff_type}`,
      subtitle: `Von: ${handoff.from_user?.full_name || `#${handoff.from_user_id}`}${handoff.notes ? ` · ${handoff.notes}` : ''}`,
      orderId: handoff.order_id,
      handoffId: handoff.id,
      action: 'Annehmen/Ablehnen',
      handoffData: handoff,
    });
  }

  for (const order of orders) {
    if (order.status === 'completed' || order.status === 'delivered') continue;

    const customerName =
      order.customer
        ? `${order.customer.first_name} ${order.customer.last_name}`.trim()
        : undefined;
    const subtitle = customerName ? `Kunde: ${customerName}` : 'Kein Kunde hinterlegt';

    // Deadline today — URGENT
    if (order.deadline) {
      const dl = new Date(order.deadline);
      dl.setHours(0, 0, 0, 0);

      if (dl.getTime() === today.getTime()) {
        items.push({
          id: `deadline-today-${order.id}`,
          type: 'deadline',
          priority: 'urgent',
          title: order.title,
          subtitle,
          deadline: order.deadline,
          orderId: order.id,
          action: 'Bearbeiten',
        });
        continue;
      }

      // Deadline within 3 days — HIGH
      if (dl > today && dl <= in3Days) {
        items.push({
          id: `deadline-soon-${order.id}`,
          type: 'deadline',
          priority: 'high',
          title: order.title,
          subtitle,
          deadline: order.deadline,
          orderId: order.id,
          action: 'Bearbeiten',
        });
        continue;
      }
    }

    // Waiting for fitting — MEDIUM
    if (order.status === 'waiting_for_fitting') {
      items.push({
        id: `fitting-${order.id}`,
        type: 'fitting',
        priority: 'medium',
        title: order.title,
        subtitle,
        deadline: order.deadline,
        orderId: order.id,
        action: 'Anprobe planen',
      });
      continue;
    }

    // In progress or confirmed — LOW
    if (order.status === 'in_progress' || order.status === 'confirmed') {
      items.push({
        id: `order-${order.id}`,
        type: 'order',
        priority: 'low',
        title: order.title,
        subtitle,
        deadline: order.deadline,
        orderId: order.id,
        action: 'Bearbeiten',
      });
    }
  }

  // Sort by priority then soonest deadline
  items.sort((a, b) => {
    const prioA = PRIORITY_ORDER[a.priority];
    const prioB = PRIORITY_ORDER[b.priority];
    if (prioA !== prioB) return prioA - prioB;
    if (a.deadline && b.deadline) {
      return new Date(a.deadline).getTime() - new Date(b.deadline).getTime();
    }
    if (a.deadline) return -1;
    if (b.deadline) return 1;
    return 0;
  });

  return items;
}

const GoldsmithDashboard: React.FC = () => {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [orders, setOrders] = useState<OrderType[]>([]);
  const [pendingHandoffs, setPendingHandoffs] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const loadAll = useCallback(async () => {
    setIsLoading(true);
    try {
      const [ordersData, handoffResp] = await Promise.all([
        ordersApi.getAll({ limit: 1000 }),
        handoffsApi.getPending().catch(() => ({ data: [] })),
      ]);
      const ordersList = Array.isArray(ordersData) ? ordersData : ordersData.items || [];
      setOrders(ordersList);
      setPendingHandoffs(Array.isArray(handoffResp.data) ? handoffResp.data : []);
    } catch (err) {
      console.error('Fehler beim Laden der Goldschmied-Daten:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleAcceptHandoff = async (id: number) => {
    try {
      await handoffsApi.accept(id);
      await loadAll();
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Annehmen der Übergabe', 'error');
    }
  };

  const handleDeclineHandoff = async (id: number) => {
    const reason = window.prompt('Begründung für die Ablehnung:');
    if (reason === null) return;
    try {
      await handoffsApi.decline(id, { response_notes: reason || 'Abgelehnt' });
      await loadAll();
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Ablehnen der Übergabe', 'error');
    }
  };

  const todoItems = buildTodoList(orders, pendingHandoffs);

  return (
    <>
      {/* Mein Arbeitsvorrat */}
      <section className="dashboard-section">
        <div className="widget-header">
          <span className="widget-header-icon">&#x1F528;</span>
          <h2>Mein Arbeitsvorrat ({todoItems.length} Aufgabe{todoItems.length !== 1 ? 'n' : ''})</h2>
        </div>

        {isLoading ? (
          <div className="deadlines-loading">Lade Aufgaben...</div>
        ) : todoItems.length === 0 ? (
          <div className="no-deadlines">
            <div className="no-deadlines-icon">&#x2713;</div>
            <p>Keine offenen Aufgaben — alles erledigt!</p>
          </div>
        ) : (
          <div className="deadlines-list">
            {todoItems.map((item) => (
              <div
                key={item.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1rem',
                  padding: '1.25rem',
                  background: PRIORITY_BG[item.priority],
                  borderRadius: '8px',
                  borderLeft: `4px solid ${PRIORITY_BORDER[item.priority]}`,
                  transition: 'all 0.2s ease',
                  cursor: item.type !== 'handoff' ? 'pointer' : 'default',
                }}
                onClick={item.type !== 'handoff' && item.orderId !== undefined
                  ? () => navigate(`/orders/${item.orderId}`)
                  : undefined}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLDivElement).style.transform = 'translateX(4px)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.transform = '';
                }}
              >
                {/* Priority badge */}
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    minWidth: '70px',
                    padding: '0.625rem 0.5rem',
                    borderRadius: '6px',
                    background: PRIORITY_BADGE_BG[item.priority],
                    color: 'white',
                    fontWeight: 700,
                    flexShrink: 0,
                    fontSize: '0.7rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                    textAlign: 'center',
                    lineHeight: 1.2,
                  }}
                >
                  {PRIORITY_LABEL[item.priority]}
                </div>

                {/* Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <h4 className="deadline-title" style={{ marginBottom: '0.375rem' }}>
                    {item.title}
                  </h4>
                  <div className="deadline-meta">
                    <span className="deadline-customer">{item.subtitle}</span>
                    {item.deadline && (
                      <span className="deadline-date">
                        &#x1F4C5; {formatRelativeDeadline(item.deadline)}
                      </span>
                    )}
                    <span
                      className={`status-badge status-${item.type === 'handoff' ? 'new' : item.type === 'fitting' ? 'in_progress' : 'in_progress'}`}
                      style={{ fontSize: '0.8rem' }}
                    >
                      {item.action}
                    </span>
                  </div>
                </div>

                {/* Actions */}
                {item.type === 'handoff' && item.handoffId !== undefined ? (
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
                      onClick={(e) => { e.stopPropagation(); handleAcceptHandoff(item.handoffId!); }}
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
                      onClick={(e) => { e.stopPropagation(); handleDeclineHandoff(item.handoffId!); }}
                    >
                      Ablehnen
                    </button>
                    {item.orderId !== undefined && (
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
                        onClick={(e) => { e.stopPropagation(); navigate(`/orders/${item.orderId}`); }}
                      >
                        Auftrag
                      </button>
                    )}
                  </div>
                ) : (
                  <button
                    style={{
                      background: 'white',
                      color: '#374151',
                      border: '2px solid #e5e7eb',
                      padding: '0.5rem 1rem',
                      borderRadius: '6px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      minHeight: '44px',
                      fontSize: '0.875rem',
                      flexShrink: 0,
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (item.orderId !== undefined) navigate(`/orders/${item.orderId}`);
                    }}
                  >
                    {item.action}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Quick Action: Zeiterfassung starten */}
      <section className="dashboard-section">
        <div className="widget-header">
          <span className="widget-header-icon">&#x23F1;&#xFE0F;</span>
          <h2>Schnellaktionen</h2>
        </div>
        <div className="dashboard-quick-actions">
          <button
            className="btn-quick-action"
            onClick={() => navigate('/time-tracking')}
          >
            &#x23F1;&#xFE0F; Zeiterfassung starten
          </button>
          <button
            className="btn-quick-action"
            onClick={() => navigate('/scanner')}
          >
            &#x1F4F1; QR-Scanner öffnen
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
