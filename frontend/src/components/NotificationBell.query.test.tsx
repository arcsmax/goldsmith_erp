// NotificationBell (W4-03): list in a Sheet, mark-as-read via useMutation.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithQuery } from '../test/queryWrapper';

const mocks = vi.hoisted(() => ({
  getUnreadCount: vi.fn(),
  getNotifications: vi.fn(),
  markAsRead: vi.fn(),
  markAllRead: vi.fn(),
}));
vi.mock('../api/notifications', () => ({ notificationsApi: mocks }));

import { NotificationBell } from './NotificationBell';

const NOTE = {
  id: 3,
  title: 'Frist morgen',
  message: 'Auftrag Demo ist morgen fällig',
  severity: 'urgent',
  is_read: false,
  created_at: new Date().toISOString(),
};

afterEach(() => {
  vi.clearAllMocks();
});

describe('NotificationBell (query)', () => {
  it('opens the list in a dialog with severity as text and marks an item read', async () => {
    mocks.getUnreadCount.mockResolvedValue({ unread_count: 1 });
    mocks.getNotifications.mockResolvedValue([NOTE]);
    mocks.markAsRead.mockResolvedValue({ ...NOTE, is_read: true });
    renderWithQuery(<NotificationBell />, { route: null });

    const trigger = await screen.findByRole('button', { name: 'Benachrichtigungen — 1 ungelesen' });
    await userEvent.click(trigger);

    expect(await screen.findByRole('dialog', { name: 'Benachrichtigungen' })).toBeInTheDocument();
    expect(await screen.findByText('Dringend')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Als gelesen markieren: Frist morgen' }));
    await waitFor(() => expect(mocks.markAsRead).toHaveBeenCalledWith(3));
    await waitFor(() => expect(mocks.getUnreadCount).toHaveBeenCalledTimes(2));
  });

  it('shows an empty state when there are no notifications', async () => {
    mocks.getUnreadCount.mockResolvedValue({ unread_count: 0 });
    mocks.getNotifications.mockResolvedValue([]);
    renderWithQuery(<NotificationBell />, { route: null });

    await userEvent.click(await screen.findByRole('button', { name: 'Benachrichtigungen' }));
    expect(await screen.findByText('Keine Benachrichtigungen')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Alle als gelesen markieren' })).toBeDisabled();
  });
});
