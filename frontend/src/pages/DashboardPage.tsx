// Dashboard Page Component
import React, { useEffect, useState } from 'react';
import { useAuth } from '../contexts';
import { ordersApi, materialsApi } from '../api';
import { OrderType, MaterialType } from '../types';
import '../styles/dashboard.css';

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const [orders, setOrders] = useState<OrderType[]>([]);
  const [lowStockMaterials, setLowStockMaterials] = useState<MaterialType[]>([]);
  const [totalStockValue, setTotalStockValue] = useState<number>(0);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setIsLoading(true);

        // Fetch recent orders (limit to 5)
        const ordersData = await ordersApi.getAll(0, 5);
        setOrders(ordersData);

        // Fetch low stock materials
        const lowStock = await materialsApi.getLowStock(10);
        setLowStockMaterials(lowStock);

        // Fetch total stock value
        const stockValue = await materialsApi.getTotalStockValue();
        setTotalStockValue(stockValue.total_value);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  if (isLoading) {
    return (
      <div className="dashboard-loading">
        <p>Lade Dashboard...</p>
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <h1>Dashboard</h1>
        <p>
          Willkommen, {user?.first_name || user?.email}!
        </p>
      </header>

      <div className="dashboard-grid">
        {/* Stats Cards */}
        <div className="stats-grid">
          <div className="stat-card">
            <h3>Gesamte Aufträge</h3>
            <p className="stat-value">{orders.length}</p>
          </div>

          <div className="stat-card">
            <h3>Lagerwert</h3>
            <p className="stat-value">{totalStockValue.toFixed(2)} €</p>
          </div>

          <div className="stat-card warning">
            <h3>Niedriger Bestand</h3>
            <p className="stat-value">{lowStockMaterials.length}</p>
          </div>
        </div>

        {/* Recent Orders */}
        <div className="dashboard-section">
          <h2>Aktuelle Aufträge</h2>
          {orders.length === 0 ? (
            <p>Keine Aufträge vorhanden.</p>
          ) : (
            <table className="dashboard-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Titel</th>
                  <th>Status</th>
                  <th>Preis</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.id}>
                    <td>#{order.id}</td>
                    <td>{order.title}</td>
                    <td>
                      <span className={`status-badge status-${order.status}`}>
                        {order.status}
                      </span>
                    </td>
                    <td>{order.price ? `${order.price} €` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Low Stock Materials */}
        {lowStockMaterials.length > 0 && (
          <div className="dashboard-section warning-section">
            <h2>Materialien mit niedrigem Bestand</h2>
            <table className="dashboard-table">
              <thead>
                <tr>
                  <th>Material</th>
                  <th>Bestand</th>
                  <th>Einheit</th>
                </tr>
              </thead>
              <tbody>
                {lowStockMaterials.map((material) => (
                  <tr key={material.id}>
                    <td>{material.name}</td>
                    <td className="low-stock">{material.stock}</td>
                    <td>{material.unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
