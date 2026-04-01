// Users Page Component (Admin only)
import React, { useEffect, useState } from 'react';
import { usersApi } from '../api';
import { UserType, UserCreateInput, UserUpdateInput } from '../types';
import { UserFormModal } from '../components/users/UserFormModal';
import '../styles/pages.css';

export const UsersPage: React.FC = () => {
  const [users, setUsers] = useState<UserType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isFormLoading, setIsFormLoading] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserType | null>(null);

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

  const handleCreateUser = async (data: UserCreateInput) => {
    try {
      setIsFormLoading(true);
      await usersApi.create(data);
      await fetchUsers();
      setIsModalOpen(false);
      alert('Benutzer erfolgreich erstellt!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Erstellen des Benutzers');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleUpdateUser = async (data: UserUpdateInput) => {
    if (!selectedUser) return;

    try {
      setIsFormLoading(true);
      await usersApi.update(selectedUser.id, data);
      await fetchUsers();
      setIsModalOpen(false);
      setSelectedUser(null);
      alert('Benutzer erfolgreich aktualisiert!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Aktualisieren des Benutzers');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleFormSubmit = async (data: UserCreateInput | UserUpdateInput) => {
    if (selectedUser) {
      await handleUpdateUser(data as UserUpdateInput);
    } else {
      await handleCreateUser(data as UserCreateInput);
    }
  };

  const handleDeactivateUser = async (user: UserType) => {
    const confirmed = window.confirm(
      `Möchten Sie den Benutzer "${user.email}" wirklich deaktivieren?\n\nDer Benutzer kann sich danach nicht mehr anmelden.`
    );
    if (!confirmed) return;

    try {
      await usersApi.deactivate(user.id);
      await fetchUsers();
      alert('Benutzer erfolgreich deaktiviert.');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Deaktivieren des Benutzers');
    }
  };

  const handleActivateUser = async (user: UserType) => {
    const confirmed = window.confirm(
      `Möchten Sie den Benutzer "${user.email}" wieder aktivieren?`
    );
    if (!confirmed) return;

    try {
      await usersApi.activate(user.id);
      await fetchUsers();
      alert('Benutzer erfolgreich aktiviert.');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Aktivieren des Benutzers');
    }
  };

  const openCreateModal = () => {
    setSelectedUser(null);
    setIsModalOpen(true);
  };

  const openEditModal = (user: UserType) => {
    setSelectedUser(user);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedUser(null);
  };

  const getRoleLabel = (role: string) => {
    const labels: Record<string, string> = {
      ADMIN: 'Administrator',
      GOLDSMITH: 'Goldschmied',
      VIEWER: 'Betrachter',
      USER: 'Benutzer',
    };
    return labels[role] || role;
  };

  if (isLoading) {
    return <div className="page-loading">Lade Benutzer...</div>;
  }

  if (error) {
    return (
      <div className="page-error">
        <p>{error}</p>
        <p className="error-hint">
          Hinweis: Dieser Bereich ist nur fur Administratoren zuganglich.
        </p>
      </div>
    );
  }

  return (
    <div className="page-container">
      <header className="page-header">
        <div>
          <h1>Benutzerverwaltung</h1>
          <p style={{ color: '#666', margin: '0.5rem 0 0 0' }}>
            {users.length} Benutzer &bull;{' '}
            {users.filter((u) => u.is_active).length} aktiv
          </p>
        </div>
        <button className="btn-primary" onClick={openCreateModal}>
          + Neuer Benutzer
        </button>
      </header>

      {users.length === 0 ? (
        <div className="empty-state">
          <p>Keine Benutzer vorhanden.</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table users-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>E-Mail</th>
                <th>Vorname</th>
                <th>Nachname</th>
                <th>Rolle</th>
                <th>Status</th>
                <th>Erstellt</th>
                <th>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td data-label="ID">#{user.id}</td>
                  <td data-label="E-Mail">{user.email}</td>
                  <td data-label="Vorname">{user.first_name || '-'}</td>
                  <td data-label="Nachname">{user.last_name || '-'}</td>
                  <td data-label="Rolle">
                    <span className={`status-badge status-${user.role.toLowerCase()}`}>
                      {getRoleLabel(user.role)}
                    </span>
                  </td>
                  <td data-label="Status">
                    <span
                      className={`status-badge ${
                        user.is_active ? 'status-completed' : 'status-new'
                      }`}
                    >
                      {user.is_active ? 'Aktiv' : 'Inaktiv'}
                    </span>
                  </td>
                  <td data-label="Erstellt">
                    {new Date(user.created_at).toLocaleDateString('de-DE')}
                  </td>
                  <td data-label="Aktionen">
                    <div className="users-page-actions" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <button
                        className="btn-icon btn-edit"
                        onClick={() => openEditModal(user)}
                        title="Bearbeiten"
                        style={{ minWidth: '44px', minHeight: '44px' }}
                      >
                        Bearbeiten
                      </button>
                      {user.is_active ? (
                        <button
                          className="btn-icon btn-delete"
                          onClick={() => handleDeactivateUser(user)}
                          title="Benutzer deaktivieren"
                          style={{ minWidth: '44px', minHeight: '44px' }}
                        >
                          Deaktivieren
                        </button>
                      ) : (
                        <button
                          className="btn-icon"
                          onClick={() => handleActivateUser(user)}
                          title="Benutzer aktivieren"
                          style={{
                            minWidth: '44px',
                            minHeight: '44px',
                            background: '#dcfce7',
                            color: '#166534',
                            border: '1px solid #bbf7d0',
                          }}
                        >
                          Aktivieren
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <UserFormModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onSubmit={handleFormSubmit}
        user={selectedUser}
        isLoading={isFormLoading}
      />
    </div>
  );
};
