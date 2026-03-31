// Main Layout Component - Layout for authenticated pages
import React from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth, useTimeTracking } from '../contexts';
import TimerWidget from '../components/TimerWidget';
import '../styles/layout.css';

export const MainLayout: React.FC = () => {
  const { user, logout, hasRole } = useAuth();
  const { runningEntry, stopTracking, refreshRunningEntry } = useTimeTracking();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleTimerStop = () => {
    // Timer stopped successfully, refresh will happen via context
    refreshRunningEntry();
  };

  const isActivePath = (path: string) => {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  };

  // Role helpers used to conditionally render nav items
  const canManageCustomers = hasRole(['ADMIN', 'GOLDSMITH']);
  const canManageMaterials = hasRole(['ADMIN', 'GOLDSMITH']);
  const canManageUsers = hasRole(['ADMIN']);

  return (
    <div className="main-layout">
      {/* Header */}
      <header className="main-header">
        <div className="header-content">
          <h1 className="logo">Goldsmith ERP</h1>

          <div className="user-menu">
            <Link to="/scanner" className="btn-scanner">
              📷 Scanner
            </Link>
            <span className="user-name">
              {user?.first_name || user?.email}
            </span>
            <button onClick={handleLogout} className="btn-logout">
              Abmelden
            </button>
          </div>
        </div>
      </header>

      <div className="main-content-wrapper">
        {/* Sidebar Navigation */}
        <aside className="main-sidebar">
          <nav className="sidebar-nav">
            {/* Dashboard — alle Rollen */}
            <Link
              to="/dashboard"
              className={`nav-link ${isActivePath('/dashboard') ? 'active' : ''}`}
            >
              <span className="nav-icon">📊</span>
              Dashboard
            </Link>

            {/* Kunden — ADMIN und GOLDSMITH */}
            {canManageCustomers && (
              <Link
                to="/customers"
                className={`nav-link ${isActivePath('/customers') ? 'active' : ''}`}
              >
                <span className="nav-icon">📇</span>
                Kunden
              </Link>
            )}

            {/* Aufträge — alle Rollen */}
            <Link
              to="/orders"
              className={`nav-link ${isActivePath('/orders') ? 'active' : ''}`}
            >
              <span className="nav-icon">📋</span>
              Aufträge
            </Link>

            {/* Materialien — ADMIN und GOLDSMITH */}
            {canManageMaterials && (
              <Link
                to="/materials"
                className={`nav-link ${isActivePath('/materials') ? 'active' : ''}`}
              >
                <span className="nav-icon">💎</span>
                Materialien
              </Link>
            )}

            {/* Metallinventar — ADMIN und GOLDSMITH */}
            {canManageMaterials && (
              <Link
                to="/metal-inventory"
                className={`nav-link ${isActivePath('/metal-inventory') ? 'active' : ''}`}
              >
                <span className="nav-icon">🥇</span>
                Metallinventar
              </Link>
            )}

            {/* Zeiterfassung — alle Rollen */}
            <Link
              to="/time-tracking"
              className={`nav-link ${isActivePath('/time-tracking') ? 'active' : ''}`}
            >
              <span className="nav-icon">⏱️</span>
              Zeiterfassung
            </Link>

            {/* Kalender — alle Rollen */}
            <Link
              to="/calendar"
              className={`nav-link ${isActivePath('/calendar') ? 'active' : ''}`}
            >
              <span className="nav-icon">📅</span>
              Kalender
            </Link>

            {/* Benutzerverwaltung — nur ADMIN */}
            {canManageUsers && (
              <Link
                to="/users"
                className={`nav-link ${isActivePath('/users') ? 'active' : ''}`}
              >
                <span className="nav-icon">👥</span>
                Benutzer
              </Link>
            )}
          </nav>
        </aside>

        {/* Main Content */}
        <main className="main-content">
          <Outlet />
        </main>
      </div>

      {/* Footer */}
      <footer className="main-footer">
        <p>&copy; 2025 Goldsmith ERP. Alle Rechte vorbehalten.</p>
      </footer>

      {/* Timer Widget - Sticky, always visible when tracking */}
      <TimerWidget
        runningEntry={runningEntry}
        onStop={handleTimerStop}
        onRefresh={refreshRunningEntry}
      />
    </div>
  );
};
