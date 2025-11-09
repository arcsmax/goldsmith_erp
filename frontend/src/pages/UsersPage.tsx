// Users Page Component (Admin only)
import React, { useEffect, useState } from 'react';
import { usersApi } from '../api';
import { UserType } from '../types';
import '../styles/pages.css';

export const UsersPage: React.FC = () => {
  const [users, setUsers] = useState<UserType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await usersApi.getAll();
      setUsers(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Benutzer');
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return <div className="page-loading">Lade Benutzer...</div>;
  }

  if (error) {
    return (
      <div className="page-error">
        <p>{error}</p>
        <p className="error-hint">
          Hinweis: Dieser Bereich ist nur für Administratoren zugänglich.
        </p>
      </div>
    );
  }

  return (
    <div className="page-container">
      <header className="page-header">
        <h1>Benutzerverwaltung</h1>
        <button className="btn-primary">+ Neuer Benutzer</button>
      </header>

      {users.length === 0 ? (
        <div className="empty-state">
          <p>Keine Benutzer vorhanden.</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>E-Mail</th>
                <th>Vorname</th>
                <th>Nachname</th>
                <th>Status</th>
                <th>Erstellt</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>#{user.id}</td>
                  <td>{user.email}</td>
                  <td>{user.first_name || '-'}</td>
                  <td>{user.last_name || '-'}</td>
                  <td>
                    <span
                      className={`status-badge ${
                        user.is_active ? 'status-completed' : 'status-new'
                      }`}
                    >
                      {user.is_active ? 'Aktiv' : 'Inaktiv'}
                    </span>
                  </td>
                  <td>{new Date(user.created_at).toLocaleDateString('de-DE')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
