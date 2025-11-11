// Deadlines Widget - Shows upcoming order deadlines
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ordersApi } from '../../api';
import { OrderType } from '../../types';
import '../../styles/dashboard.css';

interface DeadlineItem {
  order: OrderType;
  daysRemaining: number;
  urgency: 'urgent' | 'soon' | 'ok';
}

export const DeadlinesWidget: React.FC = () => {
  const navigate = useNavigate();
  const [deadlines, setDeadlines] = useState<DeadlineItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDeadlines();
  }, []);

  const fetchDeadlines = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const orders = await ordersApi.getAll({ limit: 1000 });
      const ordersList = Array.isArray(orders) ? orders : orders.items || [];

      const now = new Date();
      const twoWeeksLater = new Date();
      twoWeeksLater.setDate(twoWeeksLater.getDate() + 14);

      // Filter active orders with deadlines in next 14 days
      const upcomingDeadlines = ordersList
        .filter((o) => {
          if (o.status === 'completed' || o.status === 'delivered') return false;
          if (!o.deadline) return false;
          const deadlineDate = new Date(o.deadline);
          return deadlineDate >= now && deadlineDate <= twoWeeksLater;
        })
        .map((order) => {
          const deadlineDate = new Date(order.deadline!);
          const diffTime = deadlineDate.getTime() - now.getTime();
          const daysRemaining = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

          let urgency: 'urgent' | 'soon' | 'ok' = 'ok';
          if (daysRemaining < 2) urgency = 'urgent';
          else if (daysRemaining < 7) urgency = 'soon';

          return { order, daysRemaining, urgency };
        })
        .sort((a, b) => a.daysRemaining - b.daysRemaining)
        .slice(0, 5); // Show top 5

      setDeadlines(upcomingDeadlines);
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unbekannter Fehler';
      console.error('Failed to fetch deadlines:', err);
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const formatDeadline = (daysRemaining: number): string => {
    if (daysRemaining === 0) return 'Heute';
    if (daysRemaining === 1) return 'Morgen';
    return `in ${daysRemaining} Tagen`;
  };

  if (error) {
    return (
      <div className="deadlines-widget">
        <div className="widget-header">
          <span className="widget-header-icon">📅</span>
          <h2>Anstehende Fristen</h2>
        </div>
        <div className="deadlines-error">
          <p>⚠️ Fehler beim Laden: {error}</p>
          <button onClick={fetchDeadlines} className="retry-button">
            Erneut versuchen
          </button>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="deadlines-widget">
        <div className="widget-header">
          <span className="widget-header-icon">📅</span>
          <h2>Anstehende Fristen</h2>
        </div>
        <div className="deadlines-loading">Lade Fristen...</div>
      </div>
    );
  }

  if (deadlines.length === 0) {
    return (
      <div className="deadlines-widget">
        <div className="widget-header">
          <span className="widget-header-icon">📅</span>
          <h2>Anstehende Fristen</h2>
        </div>
        <div className="no-deadlines">
          <div className="no-deadlines-icon">✅</div>
          <p>Keine anstehenden Fristen in den nächsten 14 Tagen</p>
        </div>
      </div>
    );
  }

  return (
    <div className="deadlines-widget">
      <div className="widget-header">
        <span className="widget-header-icon">📅</span>
        <h2>Anstehende Fristen ({deadlines.length})</h2>
      </div>
      <div className="deadlines-list">
        {deadlines.map((item) => (
          <div
            key={item.order.id}
            className={`deadline-item deadline-${item.urgency}`}
            onClick={() => navigate(`/orders/${item.order.id}`)}
          >
            <div className={`deadline-badge deadline-${item.urgency}`}>
              <div className="deadline-days">{item.daysRemaining}</div>
              <div className="deadline-label">
                {item.daysRemaining === 1 ? 'TAG' : 'TAGE'}
              </div>
            </div>
            <div className="deadline-content">
              <h4 className="deadline-title">{item.order.title}</h4>
              <div className="deadline-meta">
                {item.order.customer && (
                  <span className="deadline-customer">
                    👤 {item.order.customer.first_name} {item.order.customer.last_name}
                  </span>
                )}
                {item.order.deadline && (
                  <span className="deadline-date">
                    📅 {new Date(item.order.deadline).toLocaleDateString('de-DE')}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
