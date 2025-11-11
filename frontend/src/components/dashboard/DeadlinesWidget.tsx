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

  useEffect(() => {
    fetchDeadlines();
  }, []);

  const fetchDeadlines = async () => {
    try {
      setIsLoading(true);
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
    } catch (err) {
      console.error('Failed to fetch deadlines:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const formatDeadline = (daysRemaining: number): string => {
    if (daysRemaining === 0) return 'Heute';
    if (daysRemaining === 1) return 'Morgen';
    return `in ${daysRemaining} Tagen`;
  };

  if (isLoading) {
    return (
      <div className="deadlines-widget">
        <h3>📅 Anstehende Fristen</h3>
        <div className="deadlines-loading">Lade Fristen...</div>
      </div>
    );
  }

  if (deadlines.length === 0) {
    return (
      <div className="deadlines-widget">
        <h3>📅 Anstehende Fristen</h3>
        <div className="deadlines-empty">
          <p>✅ Keine anstehenden Fristen in den nächsten 14 Tagen</p>
        </div>
      </div>
    );
  }

  return (
    <div className="deadlines-widget">
      <h3>📅 Anstehende Fristen ({deadlines.length})</h3>
      <div className="deadlines-list">
        {deadlines.map((item) => (
          <div
            key={item.order.id}
            className={`deadline-item deadline-${item.urgency}`}
            onClick={() => navigate(`/orders/${item.order.id}`)}
          >
            <div className="deadline-header">
              <span className="deadline-title">{item.order.title}</span>
              <span className={`deadline-badge deadline-badge-${item.urgency}`}>
                {formatDeadline(item.daysRemaining)}
              </span>
            </div>
            <div className="deadline-details">
              {item.order.customer && (
                <span className="deadline-customer">
                  {item.order.customer.first_name} {item.order.customer.last_name}
                </span>
              )}
              <span className="deadline-status">• {item.order.status}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
