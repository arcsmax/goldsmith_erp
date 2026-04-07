// Active Timer Widget Component
import React, { useState, useEffect } from 'react';
import { useStopwatch } from 'react-timer-hook';
import { timeTrackingApi, ordersApi, activitiesApi } from '../../api';
import { OrderType, Activity, TimeEntry } from '../../types';
import { useToast, useConfirm } from '../../contexts';
import '../../styles/time-tracking.css';

interface TimerState {
  entryId: string | null;
  orderId: number | null;
  activityId: number | null;
  location: string;
  notes: string;
  startTime: string | null;
}

const STORAGE_KEY = 'goldsmith_active_timer';

export const ActiveTimerWidget: React.FC = () => {
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const [orders, setOrders] = useState<OrderType[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [timerState, setTimerState] = useState<TimerState>({
    entryId: null,
    orderId: null,
    activityId: null,
    location: '',
    notes: '',
    startTime: null,
  });
  const [isExpanded, setIsExpanded] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { seconds, minutes, hours, isRunning, start, pause, reset } = useStopwatch({
    autoStart: false,
  });

  // Load orders, activities, and check for running entry on mount
  useEffect(() => {
    fetchOrders();
    fetchActivities();
    restoreFromServerOrStorage();
  }, []);

  const fetchOrders = async () => {
    try {
      const data = await ordersApi.getAll({ limit: 100 }); // dropdown — pre-filtered to active orders below
      const ordersList = Array.isArray(data) ? data : data.items || [];
      // Filter for active orders only
      const activeOrders = ordersList.filter(
        (o: OrderType) => o.status === 'in_progress' || o.status === 'new'
      );
      setOrders(activeOrders);
    } catch (err: any) {
      console.error('Failed to fetch orders:', err);
    }
  };

  const fetchActivities = async () => {
    try {
      const data = await activitiesApi.getAll();
      setActivities(data);
    } catch (err: any) {
      console.error('Failed to fetch activities:', err);
    }
  };

  /** Resume the stopwatch with the correct elapsed time from a start timestamp. */
  const resumeStopwatchFrom = (startTime: string) => {
    const elapsed = Date.now() - new Date(startTime).getTime();
    const offsetDate = new Date();
    offsetDate.setSeconds(offsetDate.getSeconds() + Math.floor(elapsed / 1000));
    reset(offsetDate, true); // reset to offset and auto-start
  };

  const restoreFromServerOrStorage = async () => {
    // 1. Check server for a running entry (authoritative source)
    try {
      const running = await timeTrackingApi.getRunning();
      if (running && running.id && !running.end_time) {
        const serverState: TimerState = {
          entryId: running.id,
          orderId: running.order_id,
          activityId: running.activity_id,
          location: running.location || '',
          notes: running.notes || '',
          startTime: running.start_time,
        };
        setTimerState(serverState);
        saveTimerToStorage(serverState);
        resumeStopwatchFrom(running.start_time);
        setIsExpanded(true);
        return;
      }
      // Server responded OK but no running entry — clear any stale localStorage
      clearTimerFromStorage();
      return;
    } catch (err) {
      // Server unreachable — fall through to localStorage as offline fallback
      console.warn('Could not fetch running entry from server:', err);
    }

    // 2. Offline fallback: restore from localStorage (only if server was unreachable)
    try {
      const savedTimer = localStorage.getItem(STORAGE_KEY);
      if (savedTimer) {
        const state: TimerState = JSON.parse(savedTimer);
        setTimerState(state);
        if (state.startTime) {
          resumeStopwatchFrom(state.startTime);
          setIsExpanded(true);
        }
      }
    } catch (err) {
      console.error('Failed to restore timer from storage:', err);
      localStorage.removeItem(STORAGE_KEY);
    }
  };

  const saveTimerToStorage = (state: TimerState) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (err) {
      console.error('Failed to save timer to storage:', err);
    }
  };

  const clearTimerFromStorage = () => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      console.error('Failed to clear timer from storage:', err);
    }
  };

  const handleStartTimer = async () => {
    if (!timerState.orderId || !timerState.activityId) {
      setError('Bitte wählen Sie einen Auftrag und eine Aktivität.');
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      const startTime = new Date().toISOString();

      // Create time entry in backend
      const entry = await timeTrackingApi.start({
        order_id: timerState.orderId,
        activity_id: timerState.activityId,
        location: timerState.location || undefined,
      });

      const newState: TimerState = {
        ...timerState,
        entryId: entry.id,
        startTime,
      };

      setTimerState(newState);
      saveTimerToStorage(newState);

      // Start the stopwatch
      start();
      setIsExpanded(true);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Starten des Timers');
    } finally {
      setIsLoading(false);
    }
  };

  const handlePauseTimer = () => {
    pause();
  };

  const handleResumeTimer = () => {
    start();
  };

  const handleStopTimer = async () => {
    if (!timerState.entryId) return;

    const confirmed = await showConfirm({
      title: 'Timer stoppen',
      message: 'Mochten Sie den Timer wirklich stoppen und die Zeiterfassung beenden?',
      confirmLabel: 'Stoppen',
      variant: 'danger',
    });

    if (!confirmed) return;

    try {
      setIsLoading(true);
      setError(null);

      // Stop the time entry in backend (sets end_time)
      await timeTrackingApi.stop(timerState.entryId, {});

      // Reset timer to 00:00:00, don't auto-start
      reset(undefined, false);
      setTimerState({
        entryId: null,
        orderId: null,
        activityId: null,
        location: '',
        notes: '',
        startTime: null,
      });
      clearTimerFromStorage();

      showToast('Zeiterfassung erfolgreich gespeichert!', 'success');
    } catch (err: any) {
      const detail = err.response?.data?.detail || '';
      // "already stopped" means the entry was stopped elsewhere — still clean up locally
      if (detail.includes('bereits gestoppt') || err.response?.status === 400) {
        reset(undefined, false);
        setTimerState({
          entryId: null, orderId: null, activityId: null,
          location: '', notes: '', startTime: null,
        });
        clearTimerFromStorage();
        showToast('Zeiterfassung war bereits beendet.', 'info');
      } else {
        setError(detail || 'Fehler beim Stoppen des Timers');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const formatTime = (h: number, m: number, s: number): string => {
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s
      .toString()
      .padStart(2, '0')}`;
  };

  const formatDuration = (): string => {
    return formatTime(hours, minutes, seconds);
  };

  const getSelectedOrder = (): OrderType | undefined => {
    return orders.find((o) => o.id === timerState.orderId);
  };

  const getSelectedActivity = (): Activity | undefined => {
    return activities.find((a) => a.id === timerState.activityId);
  };

  if (!isExpanded && isRunning) {
    // Minimized view when timer is running
    return (
      <div className="timer-widget minimized">
        <div className="timer-minimal-content" onClick={() => setIsExpanded(true)}>
          <span className="timer-minimal-icon">⏱️</span>
          <span className="timer-minimal-display">{formatDuration()}</span>
          <span className="timer-minimal-order">
            {getSelectedOrder()?.title || 'Auftrag #' + timerState.orderId}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className={`timer-widget ${isRunning ? 'running' : 'stopped'}`}>
      <div className="timer-header">
        <h2>⏱️ Zeiterfassung</h2>
        {isRunning && (
          <button
            className="btn-minimize"
            onClick={() => setIsExpanded(false)}
            title="Minimieren"
          >
            ▼
          </button>
        )}
      </div>

      {error && <div className="timer-error">❌ {error}</div>}

      {!isRunning ? (
        // Timer Setup Form
        <div className="timer-setup">
          <div className="timer-form">
            <div className="form-group">
              <label htmlFor="order-select">
                Auftrag <span className="required">*</span>
              </label>
              <select
                id="order-select"
                value={timerState.orderId || ''}
                onChange={(e) =>
                  setTimerState({ ...timerState, orderId: Number(e.target.value) || null })
                }
                disabled={isLoading}
              >
                <option value="">-- Auftrag wählen --</option>
                {orders.map((order) => (
                  <option key={order.id} value={order.id}>
                    #{order.id} - {order.title}
                    {order.customer && ` (${order.customer.first_name} ${order.customer.last_name})`}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="activity-select">
                Aktivität <span className="required">*</span>
              </label>
              <select
                id="activity-select"
                value={timerState.activityId || ''}
                onChange={(e) =>
                  setTimerState({ ...timerState, activityId: Number(e.target.value) || null })
                }
                disabled={isLoading}
              >
                <option value="">-- Aktivität wählen --</option>
                {activities.map((activity) => (
                  <option key={activity.id} value={activity.id}>
                    {activity.icon && `${activity.icon} `}
                    {activity.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={async () => {
                  const name = window.prompt('Neue Aktivität erstellen:\nName:');
                  if (!name?.trim()) return;
                  try {
                    await activitiesApi.create({
                      name: name.trim(),
                      category: 'fabrication',
                      icon: '🔧',
                      color: '#d97706',
                    });
                    await fetchActivities();
                  } catch (err) {
                    console.error('Fehler beim Erstellen:', err);
                  }
                }}
                style={{ padding: '0.5rem', minHeight: '44px', marginLeft: '0.5rem', borderRadius: '8px', cursor: 'pointer' }}
                title="Neue Aktivität erstellen"
              >
                + Neu
              </button>
            </div>

            <div className="form-group">
              <label htmlFor="location-input">Standort (optional)</label>
              <input
                type="text"
                id="location-input"
                value={timerState.location}
                onChange={(e) => setTimerState({ ...timerState, location: e.target.value })}
                placeholder="z.B. Werkbank 1, Tresor"
                disabled={isLoading}
              />
            </div>

            <div className="form-group">
              <label htmlFor="notes-input">Notizen (optional)</label>
              <textarea
                id="notes-input"
                value={timerState.notes}
                onChange={(e) => setTimerState({ ...timerState, notes: e.target.value })}
                rows={2}
                placeholder="Notizen zur Arbeit..."
                disabled={isLoading}
              />
            </div>

            <button
              className="btn-start-timer"
              onClick={handleStartTimer}
              disabled={isLoading || !timerState.orderId || !timerState.activityId}
            >
              {isLoading ? 'Wird gestartet...' : '▶️ Timer starten'}
            </button>
          </div>
        </div>
      ) : (
        // Running Timer Display
        <div className="timer-active">
          <div className="timer-display">{formatDuration()}</div>

          <div className="timer-info">
            <div className="timer-info-row">
              <span className="info-label">Auftrag:</span>
              <span className="info-value">
                #{timerState.orderId} - {getSelectedOrder()?.title}
              </span>
            </div>
            <div className="timer-info-row">
              <span className="info-label">Aktivität:</span>
              <span className="info-value">
                {getSelectedActivity()?.icon && `${getSelectedActivity()?.icon} `}
                {getSelectedActivity()?.name}
              </span>
            </div>
            {timerState.location && (
              <div className="timer-info-row">
                <span className="info-label">Standort:</span>
                <span className="info-value">{timerState.location}</span>
              </div>
            )}
            {timerState.notes && (
              <div className="timer-info-row">
                <span className="info-label">Notizen:</span>
                <span className="info-value">{timerState.notes}</span>
              </div>
            )}
          </div>

          <div className="timer-controls">
            {!isRunning ? (
              <button className="btn-timer btn-resume" onClick={handleResumeTimer}>
                ▶️ Fortsetzen
              </button>
            ) : (
              <button className="btn-timer btn-pause" onClick={handlePauseTimer}>
                ⏸️ Pause
              </button>
            )}
            <button
              className="btn-timer btn-stop"
              onClick={handleStopTimer}
              disabled={isLoading}
            >
              ⏹️ Stoppen & Speichern
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
