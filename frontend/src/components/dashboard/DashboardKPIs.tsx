// Dashboard KPIs Component - Displays 5 key metrics
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ordersApi, metalInventoryApi, timeTrackingApi } from '../../api';
import { KPICard } from './KPICard';
import { formatCurrency } from '../../utils/formatters';
import { getWeekStart, getTodayEnd, getMonthStart } from '../../utils/dateHelpers';
import '../../styles/dashboard.css';

interface KPIStats {
  activeOrders: number;
  monthlyRevenue: number;
  inventoryValue: number;
  inProduction: number;
  weeklyHours: number;
}

export const DashboardKPIs: React.FC = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState<KPIStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAllKPIs();
  }, []);

  const fetchAllKPIs = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Fetch all data in parallel
      const [ordersData, inventoryData, timeData] = await Promise.all([
        ordersApi.getAll({ limit: 1000 }),
        metalInventoryApi.getTotalValue(),
        timeTrackingApi.getSummary({
          start_date: getWeekStart().toISOString().split('T')[0],
          end_date: getTodayEnd().toISOString().split('T')[0],
        }).catch(() => ({ total_hours: 0, billable_hours: 0, entries_count: 0, average_session_minutes: 0 })),
      ]);

      const orders = Array.isArray(ordersData) ? ordersData : ordersData.items || [];

      // Calculate KPIs
      const activeOrders = orders.filter(
        (o) => o.status === 'new' || o.status === 'in_progress'
      ).length;

      const inProduction = orders.filter((o) => o.status === 'in_progress').length;

      // Monthly revenue (completed orders this month)
      const monthStart = getMonthStart();

      const monthlyRevenue = orders
        .filter((o) => {
          if (o.status !== 'completed' && o.status !== 'delivered') return false;
          if (!o.updated_at) return false;
          const updatedDate = new Date(o.updated_at);
          return updatedDate >= monthStart;
        })
        .reduce((sum, o) => sum + (o.price || 0), 0);

      setStats({
        activeOrders,
        monthlyRevenue,
        inventoryValue: inventoryData.total_value || 0,
        inProduction,
        weeklyHours: timeData.total_hours || 0,
      });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Dashboard-Daten');
    } finally {
      setIsLoading(false);
    }
  };

  if (error) {
    return (
      <div className="dashboard-error">
        <p>⚠️ {error}</p>
        <button onClick={fetchAllKPIs}>Erneut versuchen</button>
      </div>
    );
  }

  return (
    <div className="dashboard-kpis">
      <KPICard
        title="Aktive Aufträge"
        value={stats?.activeOrders ?? 0}
        icon="📊"
        loading={isLoading}
        onClick={() => navigate('/orders')}
        color="blue"
      />

      <KPICard
        title="Umsatz (Monat)"
        value={stats ? formatCurrency(stats.monthlyRevenue, 0) : '€0'}
        icon="💰"
        loading={isLoading}
        color="green"
      />

      <KPICard
        title="Inventarwert"
        value={stats ? formatCurrency(stats.inventoryValue, 0) : '€0'}
        icon="📦"
        loading={isLoading}
        onClick={() => navigate('/metal-inventory')}
        color="purple"
      />

      <KPICard
        title="In Produktion"
        value={stats?.inProduction ?? 0}
        icon="🔨"
        loading={isLoading}
        onClick={() => navigate('/orders?status=in_progress')}
        color="orange"
      />

      <KPICard
        title="Stunden (Woche)"
        value={stats ? `${stats.weeklyHours.toFixed(1)}h` : '0h'}
        icon="⏱️"
        loading={isLoading}
        onClick={() => navigate('/time-tracking')}
        color="teal"
      />
    </div>
  );
};
