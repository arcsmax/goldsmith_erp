// Dashboard — "Heute" start-of-day view for every role (W2-03).
//
// The work view comes first for everyone, Anne as ADMIN included
// (UI-UX-PLAYBOOK 5.4). It is one server summary (GET /dashboard/today)
// spanning orders and repairs: overdue first in the danger style, due soon,
// waiting on the customer, and today's timers. Each row links to its next
// action. ADMIN additionally sees the KPIs and alerts under "Kennzahlen".
// Role projection happens on the server: VIEWER gets no prices.
import React from 'react';
import { useAuth } from '../contexts';
import { DashboardKPIs } from '../components/dashboard/DashboardKPIs';
import { AlertsWidget } from '../components/dashboard/AlertsWidget';
import { HandoffLane } from '../components/dashboard/HandoffLane';
import { TodayView } from '../components/dashboard/TodayView';
import { canOpenRepairs } from '../components/dashboard/todayLanes';
import '../styles/pages.css';
import '../styles/dashboard.css';

const ROLE_LABELS: Readonly<Record<string, string>> = {
  ADMIN: 'Administrator',
  GOLDSMITH: 'Goldschmied',
  VIEWER: 'Betrachter',
};

function formatToday(now: Date): string {
  return now.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit' });
}

const KennzahlenSection: React.FC = () => (
  <section className="today-kennzahlen" aria-labelledby="kennzahlen-title">
    <h2 id="kennzahlen-title" className="today-kennzahlen-title">
      Kennzahlen
    </h2>
    <div className="dashboard-section kpis-section">
      <DashboardKPIs />
    </div>
    <div className="dashboard-section alerts-section">
      <AlertsWidget />
    </div>
  </section>
);

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const role = (user?.role ?? '').toUpperCase();
  const roleLabel = ROLE_LABELS[role];

  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <div>
          <h1>Heute, {formatToday(new Date())}</h1>
          <p className="dashboard-welcome">
            Willkommen, {user?.first_name || user?.email}!
            {roleLabel && <span className="dashboard-role-badge">{roleLabel}</span>}
          </p>
        </div>
      </header>

      <TodayView role={role} />
      {canOpenRepairs(role) && <HandoffLane />}
      {role === 'ADMIN' && <KennzahlenSection />}
    </div>
  );
};
