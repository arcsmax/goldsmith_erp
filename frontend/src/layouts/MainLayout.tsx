// Main Layout Component - Layout for authenticated pages
import React, { useState, useCallback } from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth, useTimeTracking } from '../contexts';
import TimerWidget from '../components/TimerWidget';
// Slice 10 — global scanner FAB + overlay, reachable from every
// authenticated page. Stacks cleanly above TimerWidget via the
// --fab-bottom CSS token (see styles/components/ScanFab.css).
import { ScanFab, ScanOverlay } from '../components/scanner';
// Slice 12 / A12.1 — one-time toast nudge when a likely USB-HID scanner
// burst is detected while Werkbank-Modus is off. Default-OFF HID is
// invisible; the nudge is Lena's killer #2 mitigation.
import { HidBurstNudge } from '../components/HidBurstNudge';
import { OfflineIndicator } from '../components/OfflineIndicator';
import { NotificationBell } from '../components/NotificationBell';
import { HealthDot } from '../components/HealthDot';
import { GlobalSearch } from '../components/GlobalSearch';
import '../styles/layout.css';
import '../styles/admin.css';
import '../styles/components/GlobalSearch.css';

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
  const canManageInvoices = hasRole(['ADMIN', 'GOLDSMITH']);
  const isAdmin = hasRole(['ADMIN']);

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

          <GlobalSearch />

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

            {/* Reparaturen — ADMIN und GOLDSMITH */}
            {canManageCustomers && (
              <Link
                to="/repairs"
                className={`nav-link ${isActivePath('/repairs') ? 'active' : ''}`}
                onClick={handleNavClick}
              >
                <span className="nav-icon">🔧</span>
                Reparaturen
              </Link>
            )}

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

            {/* Rechnungen — ADMIN und GOLDSMITH */}
            {canManageInvoices && (
              <Link
                to="/invoices"
                className={`nav-link ${isActivePath('/invoices') ? 'active' : ''}`}
                onClick={handleNavClick}
              >
                <span className="nav-icon">🧾</span>
                Rechnungen
              </Link>
            )}

            {/* Angebote (Kostenvoranschlag) — ADMIN und GOLDSMITH */}
            {canManageInvoices && (
              <Link
                to="/quotes"
                className={`nav-link ${isActivePath('/quotes') ? 'active' : ''}`}
                onClick={handleNavClick}
              >
                <span className="nav-icon">📝</span>
                Angebote
              </Link>
            )}

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

            {/* Systemübersicht — nur ADMIN */}
            {isAdmin && (
              <Link
                to="/admin/system"
                className={`nav-link ${isActivePath('/admin/system') ? 'active' : ''}`}
                onClick={handleNavClick}
              >
                <span className="nav-icon">⚙️</span>
                System
              </Link>
            )}
          </nav>

          {/* Sidebar footer: HealthDot for ADMIN — shows live system status */}
          {isAdmin && (
            <div style={{ padding: '0.75rem 0.5rem', borderTop: '1px solid #f0f0f0', marginTop: 'auto' }}>
              <HealthDot />
            </div>
          )}
        </aside>

        {/* Main Content */}
        <main className="main-content">
          <Outlet />
        </main>
      </div>

      {/* Footer */}
      <footer className="main-footer">
        <p>&copy; {new Date().getFullYear()} Goldsmith ERP. Alle Rechte vorbehalten.</p>
      </footer>

      {/* Timer Widget - Sticky, always visible when tracking */}
      <TimerWidget
        runningEntry={runningEntry}
        onStop={handleTimerStop}
        onRefresh={refreshRunningEntry}
      />

      {/* Scanner FAB (Slice 10). Stacks above TimerWidget when a timer runs
          via .scan-fab--stacked. Hidden on /login + /register via ScanFab's
          own route guard. */}
      <ScanFab />

      {/* Scanner overlay (Slice 10). Mounted here so every authenticated
          page renders over it. The overlay is position:fixed with
          z-index 1500 — above TimerWidget (1050) and ScanFab (1060). */}
      <ScanOverlay />

      {/* HID burst-detection nudge (A12.1). Invisible — attaches a
          document-level keydown listener and triggers a one-time toast
          when a suspected USB scanner burst fires while Werkbank-Modus
          is off and the user is a goldsmith. */}
      <HidBurstNudge />
    </div>
  );
};
