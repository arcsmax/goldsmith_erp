// Orders Page Component
import React, { useEffect, useState } from 'react';
import { ordersApi } from '../api';
import { OrderType } from '../types';
import '../styles/pages.css';

export const OrdersPage: React.FC = () => {
  const [orders, setOrders] = useState<OrderType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchOrders();
  }, []);

  const fetchOrders = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await ordersApi.getAll();
      setOrders(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Aufträge');
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      new: 'Neu',
      in_progress: 'In Bearbeitung',
      completed: 'Fertiggestellt',
      delivered: 'Ausgeliefert',
    };
    return labels[status] || status;
  };

  if (isLoading) {
    return <div className="page-loading">Lade Aufträge...</div>;
  }

  if (error) {
    return <div className="page-error">{error}</div>;
  }

  return (
    <div className="page-container">
      <header className="page-header">
        <h1>Aufträge</h1>
        <button className="btn-primary">+ Neuer Auftrag</button>
      </header>

      {orders.length === 0 ? (
        <div className="empty-state">
          <p>Keine Aufträge vorhanden.</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Titel</th>
                <th>Beschreibung</th>
                <th>Status</th>
                <th>Preis</th>
                <th>Erstellt</th>
                <th>Aktualisiert</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id}>
                  <td>#{order.id}</td>
                  <td>{order.title}</td>
                  <td>{order.description}</td>
                  <td>
                    <span className={`status-badge status-${order.status}`}>
                      {getStatusLabel(order.status)}
                    </span>
                  </td>
                  <td>{order.price ? `${order.price} €` : '-'}</td>
                  <td>{new Date(order.created_at).toLocaleDateString('de-DE')}</td>
                  <td>{new Date(order.updated_at).toLocaleDateString('de-DE')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
