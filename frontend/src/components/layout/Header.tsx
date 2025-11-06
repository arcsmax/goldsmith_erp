/**
 * Header Component
 */
import { useAuthStore } from '@/store/authStore';
import { useNavigate } from 'react-router-dom';
import './Header.css';

export default function Header() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="header">
      <div className="header-content">
        <div className="header-left">
          <h1 className="header-title">Goldsmith ERP</h1>
        </div>

        <div className="header-right">
          <div className="user-info">
            <div className="user-avatar">
              {user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="user-details">
              <div className="user-name">
                {user?.first_name || user?.last_name
                  ? `${user.first_name} ${user.last_name}`.trim()
                  : user?.email}
              </div>
              <div className="user-role">{user?.role}</div>
            </div>
          </div>

          <button onClick={handleLogout} className="logout-button" title="Abmelden">
            Abmelden
          </button>
        </div>
      </div>
    </header>
  );
}
