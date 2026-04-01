// NotificationBell — header bell icon with unread badge and dropdown panel
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { notificationsApi } from '../api/notifications';
import { Notification, NotificationSeverity } from '../types';
import '../styles/notification-bell.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Returns a human-readable relative time string in German. */
function timeAgo(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMinutes = Math.floor(diffMs / 60_000);

  if (diffMinutes < 1) return 'gerade eben';
  if (diffMinutes < 60) return `vor ${diffMinutes} Min.`;

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `vor ${diffHours} Std.`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return 'gestern';
  return `vor ${diffDays} Tagen`;
}

/**
 * Returns the CSS modifier class for severity.
 * Uses both color and an icon label so colorblind users are not excluded.
 */
function severityClass(severity: NotificationSeverity): string {
  switch (severity) {
    case 'URGENT':
      return 'notification-item--urgent';
    case 'WARNING':
      return 'notification-item--warning';
    case 'INFO':
    default:
      return 'notification-item--info';
  }
}

/** Accessible severity label shown alongside the color indicator dot. */
function severityLabel(severity: NotificationSeverity): string {
  switch (severity) {
    case 'URGENT':
      return '!';
    case 'WARNING':
      return '~';
    case 'INFO':
    default:
      return 'i';
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 60_000; // 60 seconds

export const NotificationBell: React.FC = () => {
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [hasError, setHasError] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const fetchUnreadCount = useCallback(async () => {
    try {
      const data = await notificationsApi.getUnreadCount();
      setUnreadCount(data.unread_count);
      setHasError(false);
    } catch {
      // Silently fail for background polling — do not surface to user
      setHasError(true);
    }
  }, []);

  const fetchNotifications = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await notificationsApi.getNotifications(10);
      setNotifications(data);
      // Recalculate unread count from the freshly loaded list so the badge
      // and dropdown stay in sync without an extra network round-trip.
      setUnreadCount(data.filter((n) => !n.is_read).length);
      setHasError(false);
    } catch {
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Polling — fetch unread count every 60 s
  // ---------------------------------------------------------------------------

  useEffect(() => {
    fetchUnreadCount();

    pollTimerRef.current = setInterval(fetchUnreadCount, POLL_INTERVAL_MS);

    return () => {
      if (pollTimerRef.current !== null) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, [fetchUnreadCount]);

  // ---------------------------------------------------------------------------
  // Dropdown open / close
  // ---------------------------------------------------------------------------

  const openDropdown = useCallback(() => {
    setIsOpen(true);
    fetchNotifications();
  }, [fetchNotifications]);

  const closeDropdown = useCallback(() => {
    setIsOpen(false);
  }, []);

  const toggleDropdown = useCallback(() => {
    if (isOpen) {
      closeDropdown();
    } else {
      openDropdown();
    }
  }, [isOpen, openDropdown, closeDropdown]);

  // Close when clicking outside
  useEffect(() => {
    if (!isOpen) return;

    const handleOutsideClick = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        closeDropdown();
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [isOpen, closeDropdown]);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeDropdown();
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, closeDropdown]);

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const handleMarkAsRead = useCallback(
    async (notification: Notification) => {
      if (notification.is_read) return;
      try {
        await notificationsApi.markAsRead(notification.id);
        setNotifications((prev) =>
          prev.map((n) =>
            n.id === notification.id ? { ...n, is_read: true } : n
          )
        );
        setUnreadCount((prev) => Math.max(0, prev - 1));
      } catch {
        // Non-critical — do not surface error for a read-mark action
      }
    },
    []
  );

  const handleMarkAllRead = useCallback(async () => {
    try {
      await notificationsApi.markAllRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      // Non-critical
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const hasUnread = unreadCount > 0;

  return (
    <div className="notification-bell" ref={containerRef}>
      {/* Bell trigger button */}
      <button
        className="notification-bell__trigger"
        onClick={toggleDropdown}
        aria-label={
          hasUnread
            ? `Benachrichtigungen — ${unreadCount} ungelesen`
            : 'Benachrichtigungen'
        }
        aria-expanded={isOpen}
        aria-haspopup="true"
        type="button"
      >
        {/* Bell SVG — inline so we can control stroke precisely */}
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

        {/* Unread count badge */}
        {hasUnread && (
          <span
            className="notification-bell__badge"
            aria-hidden="true" // count is already in the button aria-label
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      {isOpen && (
        <div
          className="notification-dropdown"
          role="dialog"
          aria-label="Benachrichtigungen"
        >
          {/* Header row */}
          <div className="notification-dropdown__header">
            <span className="notification-dropdown__title">
              Benachrichtigungen
            </span>
            {hasUnread && (
              <span className="notification-dropdown__unread-label">
                {unreadCount} ungelesen
              </span>
            )}
          </div>

          {/* Notification list */}
          <ul className="notification-dropdown__list" role="list">
            {isLoading && (
              <li className="notification-dropdown__state-row">
                <span className="notification-dropdown__spinner" aria-hidden="true" />
                Wird geladen…
              </li>
            )}

            {!isLoading && hasError && (
              <li className="notification-dropdown__state-row notification-dropdown__state-row--error">
                Benachrichtigungen konnten nicht geladen werden.
              </li>
            )}

            {!isLoading && !hasError && notifications.length === 0 && (
              <li className="notification-dropdown__state-row">
                Keine Benachrichtigungen vorhanden.
              </li>
            )}

            {!isLoading &&
              !hasError &&
              notifications.map((notification) => (
                <li
                  key={notification.id}
                  className={[
                    'notification-item',
                    severityClass(notification.severity),
                    notification.is_read ? 'notification-item--read' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                >
                  <button
                    className="notification-item__inner"
                    onClick={() => handleMarkAsRead(notification)}
                    type="button"
                    aria-label={
                      notification.is_read
                        ? notification.title
                        : `Als gelesen markieren: ${notification.title}`
                    }
                  >
                    {/* Severity indicator — color + text label for colorblind safety */}
                    <span
                      className="notification-item__severity"
                      aria-label={`Priorität: ${notification.severity}`}
                      title={notification.severity}
                    >
                      {severityLabel(notification.severity)}
                    </span>

                    <div className="notification-item__body">
                      <span className="notification-item__title">
                        {notification.title}
                      </span>
                      <span className="notification-item__message">
                        {notification.message}
                      </span>
                      <span className="notification-item__time">
                        {timeAgo(notification.created_at)}
                      </span>
                    </div>

                    {/* Unread dot — visually confirms unread state */}
                    {!notification.is_read && (
                      <span
                        className="notification-item__unread-dot"
                        aria-hidden="true"
                      />
                    )}
                  </button>
                </li>
              ))}
          </ul>

          {/* Footer — mark all read */}
          <div className="notification-dropdown__footer">
            <button
              className="notification-dropdown__mark-all"
              onClick={handleMarkAllRead}
              disabled={!hasUnread}
              type="button"
            >
              Alle als gelesen markieren
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationBell;
