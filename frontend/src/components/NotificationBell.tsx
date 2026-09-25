// NotificationBell — header bell with unread badge; the list opens in a
// src/ui Sheet (focus trap, Escape, focus return) instead of a hand-rolled
// dropdown (W4-03).
//
// Data: TanStack Query. The unread count polls every 60 s as a fallback; the
// realtime `notifications` hint invalidates ['notifications']
// (lib/realtimeInvalidation.ts), so the badge and an open list refresh at
// once. This component registers no realtime handler of its own.
import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { notificationsApi } from '../api/notifications';
import { queryKeys } from '../api/queryKeys';
import { getErrorMessage } from '../lib/errors';
import type { Notification, NotificationSeverity } from '../types';
import { Button, EmptyState, Icon, PageState, Sheet, type IconName, type PageStateValue } from '../ui';
import '../styles/notification-bell.css';

const POLL_INTERVAL_MS = 60_000;
const LIST_LIMIT = 10;
const MAX_BADGE_COUNT = 99;

/** Relative time in German ("vor 5 Min."). */
function timeAgo(isoString: string, now = Date.now()): string {
  const diffMinutes = Math.floor((now - new Date(isoString).getTime()) / 60_000);
  if (diffMinutes < 1) return 'gerade eben';
  if (diffMinutes < 60) return `vor ${diffMinutes} Min.`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `vor ${diffHours} Std.`;
  const diffDays = Math.floor(diffHours / 24);
  return diffDays === 1 ? 'gestern' : `vor ${diffDays} Tagen`;
}

/** Severity: tone + icon + German word, never colour alone. */
const SEVERITY: Readonly<Record<NotificationSeverity, { label: string; icon: IconName }>> = {
  urgent: { label: 'Dringend', icon: 'alert-triangle' },
  warning: { label: 'Warnung', icon: 'triangle-alert' },
  info: { label: 'Info', icon: 'circle-help' },
};

function severityMeta(severity: NotificationSeverity) {
  return SEVERITY[severity] ?? SEVERITY.info;
}

const BellIcon: React.FC = () => (
  <svg
    className="notification-bell__icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
  </svg>
);

interface ItemProps {
  notification: Notification;
  onMarkRead: (n: Notification) => void;
}

const NotificationItem: React.FC<ItemProps> = ({ notification, onMarkRead }) => {
  const meta = severityMeta(notification.severity);
  const classes = [
    'notification-item',
    `notification-item--${notification.severity}`,
    notification.is_read ? 'notification-item--read' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <li className={classes}>
      <button
        type="button"
        className="notification-item__inner"
        onClick={() => onMarkRead(notification)}
        aria-label={
          notification.is_read ? notification.title : `Als gelesen markieren: ${notification.title}`
        }
      >
        <span className="notification-item__severity">
          <Icon name={meta.icon} />
          {meta.label}
        </span>
        <span className="notification-item__body">
          <span className="notification-item__title">{notification.title}</span>
          <span className="notification-item__message">{notification.message}</span>
          <span className="notification-item__time">{timeAgo(notification.created_at)}</span>
        </span>
        {!notification.is_read && <span className="notification-item__unread">Neu</span>}
      </button>
    </li>
  );
};

function useNotificationMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all });
  const markRead = useMutation({
    mutationFn: (id: number) => notificationsApi.markAsRead(id),
    onSuccess: invalidate,
  });
  const markAllRead = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: invalidate,
  });
  return { markRead, markAllRead };
}

export const NotificationBell: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const countQuery = useQuery({
    queryKey: queryKeys.notifications.unreadCount(),
    queryFn: () => notificationsApi.getUnreadCount(),
    refetchInterval: POLL_INTERVAL_MS,
  });
  const listQuery = useQuery({
    queryKey: queryKeys.notifications.list(LIST_LIMIT),
    queryFn: () => notificationsApi.getNotifications(LIST_LIMIT),
    enabled: isOpen,
  });
  const { markRead, markAllRead } = useNotificationMutations();

  const unreadCount = countQuery.data?.unread_count ?? 0;
  const hasUnread = unreadCount > 0;
  const notifications = listQuery.data ?? [];
  const mutationError = markRead.error ?? markAllRead.error;

  const handleMarkRead = (n: Notification) => {
    if (!n.is_read) markRead.mutate(n.id);
  };

  const listState: PageStateValue = listQuery.isPending
    ? { status: 'loading' }
    : listQuery.isError
      ? {
          status: 'error',
          error: getErrorMessage(listQuery.error, 'Benachrichtigungen konnten nicht geladen werden.'),
          retry: () => void listQuery.refetch(),
        }
      : { status: 'ready' };

  return (
    <div className="notification-bell">
      <button
        className="notification-bell__trigger"
        onClick={() => setIsOpen(true)}
        aria-label={hasUnread ? `Benachrichtigungen — ${unreadCount} ungelesen` : 'Benachrichtigungen'}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        type="button"
      >
        <BellIcon />
        {hasUnread && (
          <span className="notification-bell__badge" aria-hidden="true">
            {unreadCount > MAX_BADGE_COUNT ? `${MAX_BADGE_COUNT}+` : unreadCount}
          </span>
        )}
      </button>

      <Sheet
        open={isOpen}
        onClose={() => setIsOpen(false)}
        title="Benachrichtigungen"
        description={hasUnread ? `${unreadCount} ungelesen` : undefined}
        dismissOnBackdrop
        footer={
          <Button
            variant="secondary"
            icon="check"
            onClick={() => markAllRead.mutate()}
            disabled={!hasUnread}
            loading={markAllRead.isPending}
          >
            Alle als gelesen markieren
          </Button>
        }
      >
        {mutationError && (
          <p className="notification-sheet__error" role="alert">
            {getErrorMessage(mutationError, 'Benachrichtigung konnte nicht aktualisiert werden.')}
          </p>
        )}
        <PageState state={listState} skeleton="list" skeletonCount={3}>
          {notifications.length === 0 ? (
            <EmptyState
              icon="inbox"
              title="Keine Benachrichtigungen"
              body="Neue Hinweise zu Aufträgen erscheinen hier."
              headingLevel={3}
            />
          ) : (
            <ul className="notification-list">
              {notifications.map((n) => (
                <NotificationItem key={n.id} notification={n} onMarkRead={handleMarkRead} />
              ))}
            </ul>
          )}
        </PageState>
      </Sheet>
    </div>
  );
};

export default NotificationBell;
