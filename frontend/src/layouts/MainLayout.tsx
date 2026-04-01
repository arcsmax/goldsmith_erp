// Main Layout Component - Layout for authenticated pages
import React, { useState, useCallback } from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth, useTimeTracking } from '../contexts';
import TimerWidget from '../components/TimerWidget';
import { OfflineIndicator } from '../components/OfflineIndicator';
import { NotificationBell } from '../components/NotificationBell';
import '../styles/layout.css';

export const MainLayout: React.FC = () => {
  const { user, logout, hasRole } = useAuth();
  const { runningEntry, stopTracking, refreshRunningEntry } = useTimeTracking();
  const navigate = useNavigate();
  const location = useLocation();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleTimerStop = () => {
    // Timer stopped successfully, refresh will happen via context
    refreshRunningEntry();
  };

  const openSidebar = useCallback(() => setIsSidebarOpen(true), []);
  const closeSidebar = useCallback(() => setIsSidebarOpen(false), []);

  const isActivePath = (path: string) => {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  };

  // Nav link that closes sidebar on mobile after navigation
  const handleNavClick = useCallback(() => {
    setIsSidebarOpen(false);
  }, []);

  // Role helpers used to conditionally render nav items
  const canManageCustomers = hasRole(['ADMIN', 'GOLDSMITH']);
  const canManageMaterials = hasRole(['ADMIN', 'GOLDSMITH']);
  const canManageUsers = hasRole(['ADMIN']);

  return (
    <div className="main-layout">
      {/* Offline status indicator — fixed banner, non-blocking */}
      <OfflineIndicator />

      {/* Header */}
      <header className="main-header">
        <div className="header-content">
          {/* Hamburger button — visible on mobile only via CSS */}
          <button
            className="btn-hamburger"
            onClick={openSidebar}
            aria-label="Navigation öffnen"
            aria-expanded={isSidebarOpen}
            aria-controls="main-sidebar"
          >
            ☰
          </button>

          <h1 className="logo">Goldsmith ERP</h1>

          <div className="user-menu">
            <Link to="/scanner" className="btn-scanner">
              📷 Scanner
            </Link>
            <NotificationBell />
            <span className="user-name">
              {user?.first_name || user?.email}
            </span>
            <button onClick={handleLogout} className="btn-logout">
              Abmelden
            </button>
          </div>
        </div>
      </header>

      {/* Offline status banner — non-blocking, auto-dismisses on reconnect */}
      <OfflineIndicator />

      {/* Overlay backdrop for mobile sidebar */}
      <div
        className={`sidebar-overlay${isSidebarOpen ? ' open' : ''}`}
        onClick={closeSidebar}
        aria-hidden="true"
      />

      <div className="main-content-wrapper">
        {/* Sidebar Navigation */}
        <aside
          id="main-sidebar"
          className={`main-sidebar${isSidebarOpen ? ' open' : ''}`}
        >
          {/* Close button row — visible on mobile */}
          <div className="sidebar-close-row">
            <button
              className="btn-sidebar-close"
              onClick={closeSidebar}
              aria-label="Navigation schließen"
            >
              ✕
            </button>
          </div>

          <nav className="sidebar-nav">
            {/* Dashboard — alle Rollen */}
            <Link
              to="/dashboard"
              className={`nav-link ${isActivePath('/dashboard') ? 'active' : ''}`}
              onClick={handleNavClick}
            >
              <span className="nav-icon">📊</span>
              Dashboard
            </Link>

            {/* Kunden — ADMIN und GOLDSMITH */}
            {canManageCustomers && (
              <Link
                to="/customers"
                className={`nav-link ${isActivePath('/customers') ? 'active' : ''}`}
                onClick={handleNavClick}
              >
                <span className="nav-icon">📇</span>
                Kunden
              </Link>
            )}

            {/* Aufträge — alle Rollen */}
            <Link
              to="/orders"
              className={`nav-link ${isActivePath('/orders') ? 'active' : ''}`}
              onClick={handleNavClick}
            >
              <span className="nav-icon">📋</span>
              Aufträge
            </Link>

            {/* Materialien — ADMIN und GOLDSMITH */}
            {canManageMaterials && (
              <Link
                to="/materials"
                className={`nav-link ${isActivePath('/materials') ? 'active' : ''}`}
                onClick={handleNavClick}
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
                onClick={handleNavClick}
              >
                <span className="nav-icon">🥇</span>
                Metallinventar
              </Link>
            )}

            {/* Zeiterfassung — alle Rollen */}
            <Link
              to="/time-tracking"
              className={`nav-link ${isActivePath('/time-tracking') ? 'active' : ''}`}
              onClick={handleNavClick}
            >
              <span className="nav-icon">⏱️</span>
              Zeiterfassung
            </Link>

            {/* Kalender — alle Rollen */}
            <Link
              to="/calendar"
              className={`nav-link ${isActivePath('/calendar') ? 'active' : ''}`}
              onClick={handleNavClick}
            >
              <span className="nav-icon">📅</span>
              Kalender
            </Link>

            {/* Benutzerverwaltung — nur ADMIN */}
            {canManageUsers && (
              <Link
                to="/users"
                className={`nav-link ${isActivePath('/users') ? 'active' : ''}`}
                onClick={handleNavClick}
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
