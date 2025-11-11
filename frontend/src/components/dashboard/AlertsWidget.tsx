// Alerts Widget - Shows important notifications
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { materialsApi, metalInventoryApi, ordersApi } from '../../api';
import '../../styles/dashboard.css';

interface Alert {
  id: string;
  type: 'warning' | 'info' | 'error';
  title: string;
  message: string;
  action?: () => void;
  actionLabel?: string;
}

export const AlertsWidget: React.FC = () => {
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAlerts();
  }, []);

  const fetchAlerts = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const alertsList: Alert[] = [];

      // Fetch low stock materials
      try {
        const lowStockMaterials = await materialsApi.getLowStock(10);
        if (lowStockMaterials.length > 0) {
          alertsList.push({
            id: 'low-stock',
            type: 'warning',
            title: 'Materialbestand niedrig',
            message: `${lowStockMaterials.length} Material(ien) haben weniger als 10 Einheiten auf Lager`,
            action: () => navigate('/materials'),
            actionLabel: 'Zu Materialien',
          });
        }
      } catch (e) {
        console.warn('Could not fetch low stock materials:', e);
        // Continue with other alerts
      }

      // Fetch low metal inventory
      try {
        const metalInventory = await metalInventoryApi.getAll();
        const lowMetal = metalInventory.filter((m) => m.remaining_weight_g < 50);
        if (lowMetal.length > 0) {
          alertsList.push({
            id: 'low-metal',
            type: 'warning',
            title: 'Metallinventar niedrig',
            message: `${lowMetal.length} Metall-Charge(n) haben weniger als 50g verbleibend`,
            action: () => navigate('/metal-inventory'),
            actionLabel: 'Zum Inventar',
          });
        }
      } catch (e) {
        console.warn('Could not fetch metal inventory:', e);
        // Continue with other alerts
      }

      // Fetch overdue orders
      try {
        const orders = await ordersApi.getAll({ limit: 1000 });
        const ordersList = Array.isArray(orders) ? orders : orders.items || [];
        const now = new Date();
        const overdueOrders = ordersList.filter((o) => {
          if (o.status === 'completed' || o.status === 'delivered') return false;
          if (!o.deadline) return false;
          return new Date(o.deadline) < now;
        });

        if (overdueOrders.length > 0) {
          alertsList.push({
            id: 'overdue',
            type: 'error',
            title: 'Überfällige Aufträge',
            message: `${overdueOrders.length} Auftrag/Aufträge sind überfällig`,
            action: () => navigate('/orders'),
            actionLabel: 'Zu Aufträgen',
          });
        }
      } catch (e) {
        console.warn('Could not fetch orders for deadlines:', e);
        // Continue - might still have other alerts
      }

      // If no alerts, show success message
      if (alertsList.length === 0) {
        alertsList.push({
          id: 'all-good',
          type: 'info',
          title: 'Alles in Ordnung',
          message: 'Keine Warnungen oder Probleme vorhanden',
        });
      }

      setAlerts(alertsList);
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unbekannter Fehler';
      console.error('Failed to fetch alerts:', err);
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const getAlertIcon = (type: Alert['type']): string => {
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
  };

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
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={`alert-item alert-${alert.type} ${alert.action ? 'clickable' : ''}`}
            onClick={alert.action}
            style={{ cursor: alert.action ? 'pointer' : 'default' }}
          >
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
          </div>
        ))}
      </div>
    </div>
  );
};
