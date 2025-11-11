// Enhanced Dashboard Page Component (2025)
import React from 'react';
import { useAuth } from '../contexts';
import { DashboardKPIs } from '../components/dashboard/DashboardKPIs';
import { AlertsWidget } from '../components/dashboard/AlertsWidget';
import { DeadlinesWidget } from '../components/dashboard/DeadlinesWidget';
import '../styles/pages.css';
import '../styles/dashboard.css';

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();

  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <div>
          <h1>Dashboard</h1>
          <p className="dashboard-welcome">
            Willkommen, {user?.first_name || user?.email}!
          </p>
        </div>
        <div className="dashboard-timestamp">
          <span className="timestamp-label">Zuletzt aktualisiert:</span>
          <span className="timestamp-value">{new Date().toLocaleString('de-DE')}</span>
        </div>
      </header>

      {/* KPI Cards - Top Section (F-Pattern Layout) */}
      <section className="dashboard-section kpis-section">
        <DashboardKPIs />
      </section>

      {/* Main Content Grid */}
      <div className="dashboard-main-grid">
        {/* Left Column: Alerts */}
        <section className="dashboard-section alerts-section">
          <AlertsWidget />
        </section>

        {/* Right Column: Deadlines */}
        <section className="dashboard-section deadlines-section">
          <DeadlinesWidget />
        </section>
      </div>

      {/* Footer Info */}
      <footer className="dashboard-footer">
        <p className="dashboard-info">
          💡 <strong>Tipp:</strong> Klicken Sie auf die KPI-Karten für weitere Details
        </p>
      </footer>
    </div>
  );
};
