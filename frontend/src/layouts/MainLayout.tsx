// Main Layout Component - Layout for authenticated pages
import React from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts';
import '../styles/layout.css';

export const MainLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isActivePath = (path: string) => {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  };

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
            <Link
              to="/dashboard"
              className={`nav-link ${isActivePath('/dashboard') ? 'active' : ''}`}
            >
              <span className="nav-icon">📊</span>
              Dashboard
            </Link>

            <Link
              to="/customers"
              className={`nav-link ${isActivePath('/customers') ? 'active' : ''}`}
            >
              <span className="nav-icon">📇</span>
              Kunden
            </Link>

            <Link
              to="/orders"
              className={`nav-link ${isActivePath('/orders') ? 'active' : ''}`}
            >
              <span className="nav-icon">📋</span>
              Aufträge
            </Link>

            <Link
              to="/materials"
              className={`nav-link ${isActivePath('/materials') ? 'active' : ''}`}
            >
              <span className="nav-icon">💎</span>
              Materialien
            </Link>

            <Link
              to="/users"
              className={`nav-link ${isActivePath('/users') ? 'active' : ''}`}
            >
              <span className="nav-icon">👥</span>
              Benutzer
            </Link>
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
    </div>
  );
};
