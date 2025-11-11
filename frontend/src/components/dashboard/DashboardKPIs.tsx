// Dashboard KPIs Component - Displays 5 key metrics
import React, { useEffect, useState, useCallback, useMemo } from 'react';
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

  const fetchAllKPIs = useCallback(async () => {
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
  }, []); // Empty deps - function doesn't depend on external values

  useEffect(() => {
    fetchAllKPIs();
  }, [fetchAllKPIs]);

  // Memoize navigation handlers to prevent unnecessary re-renders
  const navigateToOrders = useCallback(() => navigate('/orders'), [navigate]);
  const navigateToOrdersInProgress = useCallback(() => navigate('/orders?status=in_progress'), [navigate]);
  const navigateToMetalInventory = useCallback(() => navigate('/metal-inventory'), [navigate]);
  const navigateToTimeTracking = useCallback(() => navigate('/time-tracking'), [navigate]);

  // Memoize formatted values to avoid recalculation on every render
  const formattedMonthlyRevenue = useMemo(
    () => stats ? formatCurrency(stats.monthlyRevenue, 0) : '€0',
    [stats]
  );

  const formattedInventoryValue = useMemo(
    () => stats ? formatCurrency(stats.inventoryValue, 0) : '€0',
    [stats]
  );

  const formattedWeeklyHours = useMemo(
    () => stats ? `${stats.weeklyHours.toFixed(1)}h` : '0h',
    [stats]
  );

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
        onClick={navigateToOrders}
        color="blue"
      />

      <KPICard
        title="Umsatz (Monat)"
        value={formattedMonthlyRevenue}
        icon="💰"
        loading={isLoading}
        color="green"
      />

      <KPICard
        title="Inventarwert"
        value={formattedInventoryValue}
        icon="📦"
        loading={isLoading}
        onClick={navigateToMetalInventory}
        color="purple"
      />

      <KPICard
        title="In Produktion"
        value={stats?.inProduction ?? 0}
        icon="🔨"
        loading={isLoading}
        onClick={navigateToOrdersInProgress}
        color="orange"
      />

      <KPICard
        title="Stunden (Woche)"
        value={formattedWeeklyHours}
        icon="⏱️"
        loading={isLoading}
        onClick={navigateToTimeTracking}
        color="teal"
      />
    </div>
  );
};
