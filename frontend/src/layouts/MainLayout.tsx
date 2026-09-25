// Main layout for authenticated pages (UI-UX-PLAYBOOK 4.11, W4-03).
//
// Desktop (>=1024px): header plus the grouped sidebar from navigation.ts.
// Below 1024px: the sidebar becomes a drawer (hamburger, Escape closes and
// returns focus) and the app TabBar holds the five most-used entries.
// Timer, scan FAB/overlay, HID nudge and the notification bell stay mounted.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth, useTimeTracking } from '../contexts';
import TimerWidget from '../components/TimerWidget';
import { ScanFab, ScanOverlay } from '../components/scanner';
import { HidBurstNudge } from '../components/HidBurstNudge';
import { OfflineIndicator } from '../components/OfflineIndicator';
import { NotificationBell } from '../components/NotificationBell';
import { HealthDot } from '../components/HealthDot';
import { GlobalSearch } from '../components/GlobalSearch';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { ThemeToggle } from '../components/ThemeToggle';
import { Icon, IconButton, TabBar } from '../ui';
import { canAdministerSystem } from '../lib/roles';
import { navGroupsFor, tabBarItems, type NavGroup } from './navigation';
import '../styles/layout.css';
import '../styles/components/GlobalSearch.css';

interface SidebarNavProps {
  groups: NavGroup[];
  onNavigate: () => void;
}

const SidebarNav: React.FC<SidebarNavProps> = ({ groups, onNavigate }) => (
  <nav className="sidebar-nav" aria-label="Hauptnavigation">
    {groups.map((group) => (
      <div key={group.id} className="nav-group">
        {group.label && (
          <h2 className="nav-group__label" id={`nav-group-${group.id}`}>
            {group.label}
          </h2>
        )}
        <ul
          className="nav-group__list"
          aria-labelledby={group.label ? `nav-group-${group.id}` : undefined}
        >
          {group.entries.map((entry) => (
            <li key={entry.to}>
              <NavLink
                to={entry.to}
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                onClick={onNavigate}
              >
                <Icon name={entry.icon} className="nav-icon" />
                {entry.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
    ))}
  </nav>
);

export const MainLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const { runningEntry, refreshRunningEntry, pauseTracking, resumeTracking } = useTimeTracking();
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const hamburgerRef = useRef<HTMLButtonElement>(null);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const openSidebar = useCallback(() => setIsSidebarOpen(true), []);
  const closeSidebar = useCallback(() => {
    setIsSidebarOpen(false);
    hamburgerRef.current?.focus();
  }, []);
  const handleNavClick = useCallback(() => setIsSidebarOpen(false), []);

  // Playbook 4.11: the drawer closes on Escape and returns focus.
  useEffect(() => {
    if (!isSidebarOpen) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeSidebar();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [isSidebarOpen, closeSidebar]);

  const role = user?.role;
  const groups = navGroupsFor(role);
  const displayName = user?.first_name || user?.email;

  return (
    <div className="main-layout">
      <OfflineIndicator />

      <header className="main-header">
        <div className="header-content">
          <button
            ref={hamburgerRef}
            type="button"
            className="header-action header-action--menu"
            onClick={openSidebar}
            aria-label="Navigation öffnen"
            aria-expanded={isSidebarOpen}
            aria-controls="main-sidebar"
          >
            <Icon name="menu" />
          </button>

          <Link to="/dashboard" className="logo">
            Goldsmith ERP
          </Link>

          <GlobalSearch />

          {/* LV-01: below 600px only the bell stays in the header; Scanner,
              name and "Abmelden" move into the drawer (.sidebar-account). */}
          <div className="user-menu">
            <Link to="/scanner" className="header-action header-desktop-only">
              <Icon name="scan" />
              Scanner
            </Link>
            <ThemeToggle variant="header" className="header-desktop-only" />
            <NotificationBell />
            <span className="user-name header-desktop-only">{displayName}</span>
            <button
              type="button"
              onClick={handleLogout}
              className="header-action header-desktop-only"
            >
              Abmelden
            </button>
          </div>
        </div>
      </header>

      <div
        className={`sidebar-overlay${isSidebarOpen ? ' open' : ''}`}
        onClick={closeSidebar}
        aria-hidden="true"
      />

      <div className="main-content-wrapper">
        <aside id="main-sidebar" className={`main-sidebar${isSidebarOpen ? ' open' : ''}`}>
          <div className="sidebar-close-row">
            <IconButton icon="close" label="Navigation schließen" onClick={closeSidebar} />
          </div>

          <SidebarNav groups={groups} onNavigate={handleNavClick} />

          {/* Account block: the mobile home of the header user menu (LV-01). */}
          <div className="sidebar-account" data-testid="sidebar-account">
            <span className="sidebar-account__name">{displayName}</span>
            <Link to="/scanner" className="nav-link" onClick={handleNavClick}>
              <Icon name="scan" className="nav-icon" />
              Scanner
            </Link>
            <button type="button" onClick={handleLogout} className="sidebar-account__logout">
              Abmelden
            </button>
          </div>

          {canAdministerSystem(role) && (
            <div className="sidebar-health">
              <HealthDot />
            </div>
          )}
        </aside>

        <main className="main-content">
          {/* Page-level ErrorBoundary (A5): a page crash leaves header,
              sidebar, timer, scan FAB and bell alive. */}
          <ErrorBoundary variant="page">
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>

      <footer className="main-footer">
        <p>&copy; {new Date().getFullYear()} Goldsmith ERP. Alle Rechte vorbehalten.</p>
      </footer>

      <TabBar label="Schnellzugriff" items={tabBarItems(role)} className="main-tab-bar" />

      <TimerWidget
        runningEntry={runningEntry}
        onStop={() => refreshRunningEntry()}
        onRefresh={refreshRunningEntry}
        onPause={pauseTracking}
        onResume={resumeTracking}
      />
      <ScanFab />
      <ScanOverlay />
      <HidBurstNudge />
    </div>
  );
};
