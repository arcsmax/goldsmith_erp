// Dashboard API — the "Heute" start-of-day view (W2-03).
// Contract: src/goldsmith_erp/models/dashboard.py (GET /dashboard/today).
import apiClient from './client';

export type WorkItemKind = 'order' | 'repair';

export interface DashboardWorkItem {
  kind: WorkItemKind;
  id: number;
  reference: string;
  title: string;
  status: string;
  /** ISO date (Europe/Berlin calendar day). */
  due_date: string;
  /** Positive: days past due. Zero: due today. Negative: days left. */
  days_overdue: number;
  customer_id?: number | null;
  customer_name?: string | null;
  bag_number?: string | null;
}

export type PendingKind =
  | 'cost_change'
  | 'customer_update'
  | 'repair_ready'
  | 'order_ready'
  | 'quote';

export interface DashboardPendingItem {
  kind: PendingKind;
  id: number;
  title: string;
  reference: string;
  /** When the item started waiting (naive UTC ISO timestamp). */
  since: string;
  customer_id?: number | null;
  customer_name?: string | null;
  order_id?: number | null;
  repair_id?: number | null;
  quote_id?: number | null;
  bag_number?: string | null;
  valid_until?: string | null;
  /** Financial. Absent for roles without FINANCIAL_VIEW. */
  amount?: number | null;
}

export interface DashboardTimerItem {
  id: string;
  order_id: number;
  order_title?: string | null;
  user_id: number;
  user_name?: string | null;
  activity_name?: string | null;
  start_time: string;
  end_time?: string | null;
  duration_minutes?: number | null;
  is_running: boolean;
}

export interface DashboardToday {
  today: string;
  generated_at: string;
  can_view_financials: boolean;
  truncated: boolean;
  overdue: DashboardWorkItem[];
  due_soon: DashboardWorkItem[];
  customer_pending: DashboardPendingItem[];
  timers: DashboardTimerItem[];
  counts: {
    overdue: number;
    due_soon: number;
    customer_pending: number;
    timers: number;
  };
}

export const dashboardApi = {
  getToday: async (): Promise<DashboardToday> => {
    const response = await apiClient.get<DashboardToday>('/dashboard/today');
    return response.data;
  },
};
