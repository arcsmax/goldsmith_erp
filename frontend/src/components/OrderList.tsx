import React from 'react';
import { OrderType } from '../types';

interface OrderListProps {
  orders: OrderType[];
}

const OrderList: React.FC<OrderListProps> = ({ orders }) => {
  if (orders.length === 0) {
    return <p>Keine Aufträge gefunden.</p>;
  }

  return (
    <div className="order-list">
      <h2>Aufträge</h2>
      
      <table className="order-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Titel</th>
            <th>Beschreibung</th>
            <th>Preis</th>
            <th>Status</th>
            <th>Erstellt</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.id} className={`order-status-${order.status}`}>
              <td>{order.id}</td>
              <td>{order.title}</td>
              <td>{order.description}</td>
              <td>{order.price ? `${order.price} €` : '-'}</td>
              <td>
                <span className="status-badge">
                  {order.status === 'new' && 'Neu'}
                  {order.status === 'in_progress' && 'In Bearbeitung'}
                  {order.status === 'completed' && 'Fertiggestellt'}
                  {order.status === 'delivered' && 'Ausgeliefert'}
                </span>
              </td>
              <td>{new Date(order.created_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default OrderList;