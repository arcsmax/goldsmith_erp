// Dashboard KPIs Component - Displays 5 key metrics
//
// W3-03: TanStack Query. The orders query is shared with AlertsWidget
// (dashboardQueries.ts), so the Kennzahlen section fetches orders once.
import React, { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { timeTrackingApi } from '../../api';
import { queryKeys, type DateRange } from '../../api/queryKeys';
import type { OrderListItem } from '../../api/orders';
import { getErrorMessage } from '../../lib/errors';
import { KPICard } from './KPICard';
import { inventoryStatisticsQuery, widgetOrdersQuery } from './dashboardQueries';
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

function isoDay(date: Date): string {
  return date.toISOString().split('T')[0];
}

function currentWeek(): DateRange {
  return { start_date: isoDay(getWeekStart()), end_date: isoDay(getTodayEnd()) };
}

function orderStats(orders: readonly OrderListItem[]) {
  const monthStart = getMonthStart();
  return {
    activeOrders: orders.filter((o) => o.status === 'new' || o.status === 'in_progress').length,
    inProduction: orders.filter((o) => o.status === 'in_progress').length,
    // Monthly revenue: completed or delivered orders updated this month.
    monthlyRevenue: orders
      .filter((o) => {
        if (o.status !== 'completed' && o.status !== 'delivered') return false;
        return Boolean(o.updated_at) && new Date(o.updated_at) >= monthStart;
      })
      .reduce((sum, o) => sum + (o.price || 0), 0),
  };
}

export const DashboardKPIs: React.FC = () => {
  const navigate = useNavigate();
  const [week] = useState(currentWeek);

  const ordersQuery = useQuery(widgetOrdersQuery());
  // Inventory and hours are secondary: a failure shows 0 instead of hiding the KPIs.
  const inventoryQuery = useQuery(inventoryStatisticsQuery());
  const hoursQuery = useQuery({
    queryKey: queryKeys.timer.summary(week),
    queryFn: () => timeTrackingApi.getSummary(week),
  });

  const isLoading = ordersQuery.isPending || inventoryQuery.isPending || hoursQuery.isPending;
  const stats = useMemo<KPIStats | null>(() => {
    if (!ordersQuery.data) return null;
    return {
      ...orderStats(ordersQuery.data),
      inventoryValue: inventoryQuery.data?.total_value || 0,
      weeklyHours: hoursQuery.data?.total_hours || 0,
    };
  }, [ordersQuery.data, inventoryQuery.data, hoursQuery.data]);
  const error = ordersQuery.isError
    ? getErrorMessage(ordersQuery.error, 'Fehler beim Laden der Dashboard-Daten')
    : null;
  const fetchAllKPIs = () => {
    void ordersQuery.refetch();
    void inventoryQuery.refetch();
    void hoursQuery.refetch();
  };

  // Memoize navigation handlers to prevent unnecessary re-renders
  const navigateToOrders = useCallback(() => navigate('/orders'), [navigate]);
  const navigateToOrdersInProgress = useCallback(() => navigate('/orders?status=in_progress'), [navigate]);
  const navigateToOrdersCompleted = useCallback(() => navigate('/orders?status=completed'), [navigate]);
  const navigateToMetalInventory = useCallback(() => navigate('/metal-inventory'), [navigate]);
  const navigateToTimeTracking = useCallback(() => navigate('/time-tracking'), [navigate]);

  // Memoize formatted values to avoid recalculation on every render
  const formattedMonthlyRevenue = useMemo(
    () => stats ? formatCurrency(stats.monthlyRevenue, 0) : formatCurrency(0, 0),
    [stats]
  );

  const formattedInventoryValue = useMemo(
    () => stats ? formatCurrency(stats.inventoryValue, 0) : formatCurrency(0, 0),
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
        onClick={navigateToOrdersCompleted}
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
