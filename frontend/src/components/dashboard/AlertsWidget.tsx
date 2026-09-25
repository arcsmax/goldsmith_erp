// Alerts Widget - Shows important notifications
//
// W3-03: three queries (low stock, metal purchases, recent orders). The
// orders query is shared with DashboardKPIs (dashboardQueries.ts), so the
// Kennzahlen section fetches orders once. A single failing source is logged
// in its query function and skipped; only when every source fails does the
// widget show an error.
import React, { useCallback, useMemo } from 'react';
import { useNavigate, type NavigateFunction } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { OrderListItem } from '../../api/orders';
import {
  LOW_STOCK_THRESHOLD,
  lowStockQuery,
  metalPurchasesQuery,
  widgetOrdersQuery,
} from './dashboardQueries';
import '../../styles/dashboard.css';

interface Alert {
  id: string;
  type: 'warning' | 'info' | 'error';
  title: string;
  message: string;
  action?: () => void;
  actionLabel?: string;
}

/** Metal lots with less than this many grams left raise the low-metal alert. */
const LOW_METAL_GRAMS = 50;

function isOverdue(order: OrderListItem, now: Date): boolean {
  if (order.status === 'completed' || order.status === 'delivered') return false;
  return Boolean(order.deadline) && new Date(order.deadline as string) < now;
}

function buildAlerts(
  sources: {
    lowStockCount?: number;
    lowMetalCount?: number;
    orders?: readonly OrderListItem[];
  },
  navigate: NavigateFunction,
): Alert[] {
  const alerts: Alert[] = [];
  if (sources.lowStockCount) {
    alerts.push({
      id: 'low-stock',
      type: 'warning',
      title: 'Materialbestand niedrig',
      message: `${sources.lowStockCount} Material(ien) haben weniger als ${LOW_STOCK_THRESHOLD} Einheiten auf Lager`,
      action: () => navigate('/materials'),
      actionLabel: 'Zu Materialien',
    });
  }
  if (sources.lowMetalCount) {
    alerts.push({
      id: 'low-metal',
      type: 'warning',
      title: 'Metallinventar niedrig',
      message: `${sources.lowMetalCount} Metall-Charge(n) haben weniger als ${LOW_METAL_GRAMS}g verbleibend`,
      action: () => navigate('/metal-inventory'),
      actionLabel: 'Zum Inventar',
    });
  }
  const now = new Date();
  const overdueCount = (sources.orders ?? []).filter((o) => isOverdue(o, now)).length;
  if (overdueCount > 0) {
    alerts.push({
      id: 'overdue',
      type: 'error',
      title: 'Überfällige Aufträge',
      message: `${overdueCount} Auftrag/Aufträge sind überfällig`,
      action: () => navigate('/orders'),
      actionLabel: 'Zu Aufträgen',
    });
  }
  if (alerts.length === 0) {
    alerts.push({
      id: 'all-good',
      type: 'info',
      title: 'Alles in Ordnung',
      message: 'Keine Warnungen oder Probleme vorhanden',
    });
  }
  return alerts;
}

export const AlertsWidget: React.FC = () => {
  const navigate = useNavigate();
  const lowStock = useQuery(lowStockQuery());
  const metal = useQuery(metalPurchasesQuery());
  const orders = useQuery(widgetOrdersQuery());
  const sources = [lowStock, metal, orders] as const;

  const isLoading = sources.some((q) => q.isPending);
  const error = sources.every((q) => q.isError) ? 'Keine Quelle erreichbar' : null;
  const alerts = useMemo(() => {
    if (isLoading) return [];
    return buildAlerts(
      {
        lowStockCount: lowStock.data?.length,
        lowMetalCount: metal.data?.filter((m) => m.remaining_weight_g < LOW_METAL_GRAMS).length,
        orders: orders.data,
      },
      navigate,
    );
  }, [isLoading, lowStock.data, metal.data, orders.data, navigate]);
  const fetchAlerts = () => sources.forEach((q) => void q.refetch());

  // Memoize icon selector to avoid recreating on every render
  const getAlertIcon = useCallback((type: Alert['type']): string => {
    switch (type) {
      case 'error':
        return '🔴';
      case 'warning':
        return '⚠️';
      case 'info':
        return 'ℹ️';
      default:
        return '📢';
    }
  }, []);

  if (error) {
    return (
      <div className="alerts-widget">
        <div className="widget-header">
          <span className="widget-header-icon">⚠️</span>
          <h2>Benachrichtigungen</h2>
        </div>
        <div className="alerts-error">
          <p>⚠️ Fehler beim Laden: {error}</p>
          <button onClick={fetchAlerts} className="retry-button">
            Erneut versuchen
          </button>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="alerts-widget">
        <div className="widget-header">
          <span className="widget-header-icon">⚠️</span>
          <h2>Benachrichtigungen</h2>
        </div>
        <div className="alerts-loading">Lade Benachrichtigungen...</div>
      </div>
    );
  }

  return (
    <div className="alerts-widget">
      <div className="widget-header">
        <span className="widget-header-icon">⚠️</span>
        <h2>Benachrichtigungen</h2>
      </div>
      <div className="alerts-list">
        {alerts.map((alert) => {
          const className = `alert-item alert-${alert.type} ${alert.action ? 'clickable' : ''}`;
          const content = (
            <>
              <span className="alert-icon">{getAlertIcon(alert.type)}</span>
              <div className="alert-content">
                <h4 className="alert-title">{alert.title}</h4>
                <p className="alert-message">{alert.message}</p>
                {alert.action && alert.actionLabel && (
                  <span className="alert-action">
                    {alert.actionLabel} →
                  </span>
                )}
              </div>
            </>
          );

          return alert.action ? (
            <button
              key={alert.id}
              type="button"
              className={className}
              onClick={alert.action}
            >
              {content}
            </button>
          ) : (
            <div key={alert.id} className={className}>
              {content}
            </div>
          );
        })}
      </div>
    </div>
  );
};
