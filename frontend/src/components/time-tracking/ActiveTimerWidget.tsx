// Active Timer Widget Component
import React, { useState, useEffect } from 'react';
import { useStopwatch } from 'react-timer-hook';
import { timeTrackingApi, ordersApi } from '../../api';
import { OrderType, ActivityType, TimeEntryType } from '../../types';
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
  const [orders, setOrders] = useState<OrderType[]>([]);
  const [activities, setActivities] = useState<ActivityType[]>([]);
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

  // Load orders and activities on mount
  useEffect(() => {
    fetchOrders();
    fetchActivities();
    restoreTimerFromStorage();
  }, []);

  const fetchOrders = async () => {
    try {
      const data = await ordersApi.getAll({ limit: 1000 });
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
      const data = await timeTrackingApi.getAllActivities();
      setActivities(data);
    } catch (err: any) {
      console.error('Failed to fetch activities:', err);
    }
  };

  const restoreTimerFromStorage = () => {
    try {
      const savedTimer = localStorage.getItem(STORAGE_KEY);
      if (savedTimer) {
        const state: TimerState = JSON.parse(savedTimer);
        setTimerState(state);

        // Calculate elapsed time and resume timer
        if (state.startTime) {
          const startDate = new Date(state.startTime);
          const elapsed = Date.now() - startDate.getTime();
          const elapsedSeconds = Math.floor(elapsed / 1000);

          // Create offset timestamp for useStopwatch
          const offsetTimestamp = new Date();
          offsetTimestamp.setSeconds(offsetTimestamp.getSeconds() + elapsedSeconds);

          start();
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
      const entry = await timeTrackingApi.create({
        order_id: timerState.orderId,
        activity_id: timerState.activityId,
        start_time: startTime,
        location: timerState.location || undefined,
        notes: timerState.notes || undefined,
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

    const confirmed = window.confirm(
      'Möchten Sie den Timer wirklich stoppen und die Zeiterfassung beenden?'
    );

    if (!confirmed) return;

    try {
      setIsLoading(true);
      setError(null);

      // Stop the time entry in backend (sets end_time)
      await timeTrackingApi.stop(timerState.entryId);

      // Reset timer
      reset();
      setTimerState({
        entryId: null,
        orderId: null,
        activityId: null,
        location: '',
        notes: '',
        startTime: null,
      });
      clearTimerFromStorage();

      alert('Zeiterfassung erfolgreich gespeichert!');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Stoppen des Timers');
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

  const getSelectedActivity = (): ActivityType | undefined => {
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
