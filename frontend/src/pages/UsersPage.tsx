// Users page (admin only) — list template (playbook 5.1) on TanStack Query (W4-03).
//
// GET /users/ is not paged on the server; the admin list is short, so one
// query holds it. Create, update, activate and deactivate are mutations that
// invalidate ['users'].
import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { usersApi } from '../api';
import { queryKeys } from '../api/queryKeys';
import { UserFormModal } from '../components/users/UserFormModal';
import { useToast, useConfirm } from '../contexts';
import { getErrorMessage } from '../lib/errors';
import type { UserType, UserCreateInput, UserUpdateInput } from '../types';
import { Button, DataTable, PageHeader, type Column, type PageStateValue } from '../ui';
import { StatusBadge } from '../ui/StatusBadge';
import '../styles/pages.css';
import '../styles/users.css';

/** GET /users/ is not paged; the workshop has far fewer accounts. */
const USER_LIST_LIMIT = 100;

const ROLE_LABELS: Readonly<Record<string, string>> = {
  ADMIN: 'Administrator',
  GOLDSMITH: 'Goldschmied',
  VIEWER: 'Betrachter',
  USER: 'Benutzer',
};

function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('de-DE');
}

function useUserMutations(onSaved: () => void) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.users.all });

  const create = useMutation({
    mutationFn: (data: UserCreateInput) => usersApi.create(data),
    onSuccess: async () => {
      await invalidate();
      onSaved();
      showToast('Benutzer angelegt', 'success');
    },
    onError: (err) => showToast(getErrorMessage(err, 'Benutzer konnte nicht angelegt werden'), 'error'),
  });

  const update = useMutation({
    mutationFn: ({ id, data }: { id: number; data: UserUpdateInput }) => usersApi.update(id, data),
    onSuccess: async () => {
      await invalidate();
      onSaved();
      showToast('Benutzer gespeichert', 'success');
    },
    onError: (err) =>
      showToast(getErrorMessage(err, 'Benutzer konnte nicht gespeichert werden'), 'error'),
  });

  const deactivate = useMutation({
    mutationFn: (id: number) => usersApi.deactivate(id),
    onSuccess: async () => {
      await invalidate();
      showToast('Benutzer deaktiviert', 'success');
    },
    onError: (err) =>
      showToast(getErrorMessage(err, 'Benutzer konnte nicht deaktiviert werden'), 'error'),
  });

  const activate = useMutation({
    mutationFn: (id: number) => usersApi.activate(id),
    onSuccess: async () => {
      await invalidate();
      showToast('Benutzer aktiviert', 'success');
    },
    onError: (err) => showToast(getErrorMessage(err, 'Benutzer konnte nicht aktiviert werden'), 'error'),
  });

  return { create, update, deactivate, activate };
}

export const UsersPage: React.FC = () => {
  const { showConfirm } = useConfirm();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserType | null>(null);

  const usersQuery = useQuery({
    queryKey: queryKeys.users.list(0, USER_LIST_LIMIT),
    queryFn: () => usersApi.getAll(0, USER_LIST_LIMIT),
  });
  const users = usersQuery.data ?? [];

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedUser(null);
  };
  const { create, update, deactivate, activate } = useUserMutations(closeModal);

  // Errors surface as a toast (onError); the dialog stays open until onSuccess closes it.
  const handleFormSubmit = async (data: UserCreateInput | UserUpdateInput): Promise<void> => {
    if (selectedUser) {
      update.mutate({ id: selectedUser.id, data: data as UserUpdateInput });
    } else {
      create.mutate(data as UserCreateInput);
    }
  };

  const handleDeactivateUser = async (user: UserType) => {
    const confirmed = await showConfirm({
      title: 'Benutzer deaktivieren',
      message: `Möchten Sie den Benutzer „${user.email}“ wirklich deaktivieren? Der Benutzer kann sich danach nicht mehr anmelden.`,
      confirmLabel: 'Deaktivieren',
      variant: 'danger',
    });
    if (confirmed) deactivate.mutate(user.id);
  };

  const handleActivateUser = async (user: UserType) => {
    const confirmed = await showConfirm({
      title: 'Benutzer aktivieren',
      message: `Möchten Sie den Benutzer „${user.email}“ wieder aktivieren?`,
      confirmLabel: 'Aktivieren',
      variant: 'default',
    });
    if (confirmed) activate.mutate(user.id);
  };

  const openCreateModal = () => {
    setSelectedUser(null);
    setIsModalOpen(true);
  };

  const openEditModal = (user: UserType) => {
    setSelectedUser(user);
    setIsModalOpen(true);
  };

  const state: PageStateValue = usersQuery.isPending
    ? { status: 'loading' }
    : usersQuery.isError
      ? {
          status: 'error',
          error: `${getErrorMessage(usersQuery.error, 'Benutzer konnten nicht geladen werden')} Dieser Bereich ist nur für Administratoren zugänglich.`,
          retry: () => void usersQuery.refetch(),
        }
      : users.length === 0
        ? { status: 'empty' }
        : { status: 'ready' };

  const columns: Column<UserType>[] = [
    { key: 'email', header: 'E-Mail', render: (u) => u.email },
    { key: 'first_name', header: 'Vorname', render: (u) => u.first_name || '—', hideBelow: 'tablet' },
    { key: 'last_name', header: 'Nachname', render: (u) => u.last_name || '—', hideBelow: 'tablet' },
    { key: 'role', header: 'Rolle', render: (u) => roleLabel(u.role) },
    {
      key: 'active',
      header: 'Status',
      render: (u) => <StatusBadge kind="user" status={u.is_active ? 'active' : 'inactive'} />,
    },
    {
      key: 'created_at',
      header: 'Erstellt',
      numeric: true,
      hideBelow: 'tablet',
      render: (u) => formatDate(u.created_at),
    },
    {
      key: 'actions',
      header: 'Aktionen',
      render: (u) => (
        <div className="users-page-actions">
          <Button variant="secondary" icon="pencil" onClick={() => openEditModal(u)}>
            Bearbeiten
          </Button>
          {u.is_active ? (
            <Button variant="ghost" onClick={() => void handleDeactivateUser(u)}>
              Deaktivieren
            </Button>
          ) : (
            <Button variant="ghost" icon="check" onClick={() => void handleActivateUser(u)}>
              Aktivieren
            </Button>
          )}
        </div>
      ),
    },
  ];

  const activeCount = users.filter((u) => u.is_active).length;

  return (
    <div className="page-container">
      <PageHeader
        title="Benutzerverwaltung"
        meta={usersQuery.isSuccess ? `${users.length} Benutzer · ${activeCount} aktiv` : undefined}
        primaryAction={
          <Button icon="plus" onClick={openCreateModal}>
            Benutzer anlegen
          </Button>
        }
      />

      <DataTable
        rows={users}
        columns={columns}
        getRowKey={(u) => u.id}
        caption="Benutzer"
        state={state}
        cardTitle={(u) => u.email}
        empty={{
          icon: 'inbox',
          title: 'Noch keine Benutzer',
          body: 'Legen Sie den ersten Benutzer für die Werkstatt an.',
          action: <Button onClick={openCreateModal}>Benutzer anlegen</Button>,
        }}
      />

      <UserFormModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onSubmit={handleFormSubmit}
        user={selectedUser}
        isLoading={create.isPending || update.isPending}
      />
    </div>
  );
};
