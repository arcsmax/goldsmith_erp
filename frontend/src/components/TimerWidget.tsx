import React, { useState, useEffect, useCallback } from 'react';
import { TimeEntry, TimeEntryStopInput, OrderType, Activity } from '../types';
import { timeTrackingApi } from '../api/time-tracking';
import { ordersApi } from '../api/orders';
import { activitiesApi } from '../api/activities';
import '../styles/components/TimerWidget.css';

interface TimerWidgetProps {
  runningEntry: TimeEntry | null;
  onStop: () => void;
  onRefresh?: () => void;
}

interface StopDialogData {
  complexity_rating: number;
  quality_rating: number;
  rework_required: boolean;
  notes: string;
}

const TimerWidget: React.FC<TimerWidgetProps> = ({
  runningEntry,
  onStop,
  onRefresh,
}) => {
  const [elapsedTime, setElapsedTime] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(true);

  // Listen for external "expand timer" events (e.g. clicking a running entry row)
  useEffect(() => {
    const handleExpand = () => { setIsCollapsed(false); setShowStartForm(false); };
    window.addEventListener('timer:expand', handleExpand);
    return () => window.removeEventListener('timer:expand', handleExpand);
  }, []);
  const [showStartForm, setShowStartForm] = useState(false);
  const [showStopDialog, setShowStopDialog] = useState(false);
  // Start form state
  const [orders, setOrders] = useState<OrderType[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(null);
  const [selectedActivityId, setSelectedActivityId] = useState<number | null>(null);
  const [startLoading, setStartLoading] = useState(false);
  const [stopData, setStopData] = useState<StopDialogData>({
    complexity_rating: 3,
    quality_rating: 4,
    rework_required: false,
    notes: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Calculate elapsed time
  useEffect(() => {
    if (!runningEntry || isPaused) return;

    const startTime = new Date(runningEntry.start_time).getTime();

    const updateElapsed = () => {
      const now = Date.now();
      const elapsed = Math.floor((now - startTime) / 1000); // seconds
      setElapsedTime(elapsed);
    };

    // Update immediately
    updateElapsed();

    // Update every second
    const interval = setInterval(updateElapsed, 1000);

    return () => clearInterval(interval);
  }, [runningEntry, isPaused]);

  const formatTime = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  const handlePauseResume = () => {
    if (!runningEntry) return;
    // Pause/resume is a local UI action only — the backend timer keeps running.
    // The actual elapsed time is always calculated from start_time to end_time.
    setIsPaused((prev) => !prev);
  };

  const handleStopClick = () => {
    setShowStopDialog(true);
  };

  const handleStopConfirm = async () => {
    if (!runningEntry) return;

    try {
      setLoading(true);
      setError(null);

      const stopInput: TimeEntryStopInput = {
        complexity_rating: stopData.complexity_rating,
        quality_rating: stopData.quality_rating,
        rework_required: stopData.rework_required,
        notes: stopData.notes || undefined,
      };

      await timeTrackingApi.stop(runningEntry.id, stopInput);

      // Reset state
      setShowStopDialog(false);
      setStopData({
        complexity_rating: 3,
        quality_rating: 4,
        rework_required: false,
        notes: '',
      });

      // Notify parent
      onStop();

      // Refresh if callback provided
      if (onRefresh) {
        onRefresh();
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail || '';
      // If already stopped, treat as success and clean up
      if (detail.includes('bereits gestoppt') || err.response?.status === 400) {
        setShowStopDialog(false);
        onStop();
        if (onRefresh) onRefresh();
      } else {
        console.error('Failed to stop timer:', err);
        setError(detail || 'Timer stoppen fehlgeschlagen');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleStopCancel = () => {
    setShowStopDialog(false);
    setError(null);
  };

  const renderStars = (count: number, value: number, onChange: (val: number) => void) => {
    return (
      <div className="star-rating">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            onClick={() => onChange(star)}
            className={`star ${star <= value ? 'active' : ''}`}
          >
            ★
          </button>
        ))}
      </div>
    );
  };

  const fetchStartFormData = useCallback(async () => {
    try {
      const [o, a] = await Promise.all([
        ordersApi.getAll({ limit: 100 }),
        activitiesApi.getAll(),
      ]);
      setOrders(o);
      setActivities(a);
    } catch (err) {
      console.error('Failed to load form data:', err);
    }
  }, []);

  const handleStartTimer = async () => {
    if (!selectedOrderId || !selectedActivityId) return;
    try {
      setStartLoading(true);
      setError(null);
      await timeTrackingApi.start({
        order_id: selectedOrderId,
        activity_id: selectedActivityId,
      });
      setShowStartForm(false);
      setSelectedOrderId(null);
      setSelectedActivityId(null);
      if (onRefresh) onRefresh();
    } catch (err: any) {
      const detail = err.response?.data?.detail || '';
      if (detail.includes('bereits eine laufende') || detail.includes('already')) {
        // Already running — just close form and refresh to show it
        setShowStartForm(false);
        if (onRefresh) onRefresh();
      } else {
        setError(detail || 'Fehler beim Starten');
      }
    } finally {
      setStartLoading(false);
    }
  };

  const handleFabClick = () => {
    if (runningEntry) {
      // Running entry exists — expand the timer display
      setIsCollapsed(false);
      setShowStartForm(false);
    } else {
      // No running entry — open start form
      setShowStartForm((prev) => !prev);
      if (!showStartForm) fetchStartFormData();
    }
  };

  // Collapsed FAB button — always visible in bottom-right
  if (isCollapsed && !showStartForm) {
    return (
      <button
        className={`timer-fab ${runningEntry ? 'timer-fab--active' : ''}`}
        onClick={handleFabClick}
        title={runningEntry ? `${formatTime(elapsedTime)} — Klicken zum Öffnen` : 'Zeiterfassung starten'}
      >
        <span className="timer-fab-icon">⏱️</span>
        {runningEntry && (
          <span className="timer-fab-time">{formatTime(elapsedTime)}</span>
        )}
      </button>
    );
  }

  // Start form overlay — when no entry is running
  if (showStartForm && !runningEntry) {
    return (
      <div className="timer-widget timer-widget--start-form">
        <div className="timer-header-row">
          <h3>⏱️ Zeiterfassung starten</h3>
          <button
            className="timer-close-btn"
            onClick={() => { setShowStartForm(false); setIsCollapsed(true); }}
            title="Schließen"
          >
            ✕
          </button>
        </div>

        {error && <div className="timer-error">{error}</div>}

        <div className="timer-start-form">
          <label>Auftrag</label>
          <select
            value={selectedOrderId || ''}
            onChange={(e) => setSelectedOrderId(Number(e.target.value) || null)}
          >
            <option value="">-- Auftrag wählen --</option>
            {orders.map((o) => (
              <option key={o.id} value={o.id}>
                #{o.id} - {o.title}
                {o.customer && ` (${o.customer.first_name} ${o.customer.last_name})`}
              </option>
            ))}
          </select>

          <label>Aktivität</label>
          <select
            value={selectedActivityId || ''}
            onChange={(e) => setSelectedActivityId(Number(e.target.value) || null)}
          >
            <option value="">-- Aktivität wählen --</option>
            {activities.map((a) => (
              <option key={a.id} value={a.id}>
                {a.icon && `${a.icon} `}{a.name}
              </option>
            ))}
          </select>

          <button
            className="timer-start-btn"
            onClick={handleStartTimer}
            disabled={startLoading || !selectedOrderId || !selectedActivityId}
          >
            {startLoading ? 'Wird gestartet...' : '▶️ Timer starten'}
          </button>
        </div>
      </div>
    );
  }

  // No running entry and form not open — just show FAB
  if (!runningEntry) {
    return (
      <button
        className="timer-fab"
        onClick={handleFabClick}
        title="Zeiterfassung starten"
      >
        <span className="timer-fab-icon">⏱️</span>
      </button>
    );
  }

  return (
    <>
      {/* Timer Widget (Sticky, expanded) */}
      <div className={`timer-widget ${isPaused ? 'paused' : ''}`}>
        <div className="timer-widget-content">
          <div className="timer-info">
            <div className="timer-label">
              {isPaused ? '⏸️ Pausiert' : '⏱️ Läuft'}
            </div>
            <div className="timer-time">{formatTime(elapsedTime)}</div>
            <div className="timer-activity">
              Auftrag #{runningEntry.order_id}
            </div>
          </div>

          <div className="timer-controls">
            <button
              onClick={handlePauseResume}
              className="timer-button timer-button-pause"
              disabled={loading}
            >
              {isPaused ? '▶️ Fortsetzen' : '⏸️ Pause'}
            </button>
            <button
              onClick={handleStopClick}
              className="timer-button timer-button-stop"
              disabled={loading}
            >
              ⏹️ Stopp
            </button>
            <button
              onClick={() => setIsCollapsed(true)}
              className="timer-button timer-button-collapse"
              title="Minimieren"
            >
              ▼
            </button>
          </div>
        </div>

        {error && <div className="timer-error">{error}</div>}
      </div>

      {/* Stop Dialog */}
      {showStopDialog && (
        <div className="timer-stop-dialog-overlay">
          <div className="timer-stop-dialog">
            <h3>Zeiterfassung beenden</h3>

            <div className="stop-dialog-content">
              <div className="stop-dialog-field">
                <label>Komplexität (1-5)</label>
                {renderStars(
                  5,
                  stopData.complexity_rating,
                  (val) => setStopData({ ...stopData, complexity_rating: val })
                )}
                <span className="rating-hint">
                  Wie schwierig war die Aufgabe?
                </span>
              </div>

              <div className="stop-dialog-field">
                <label>Qualität (1-5)</label>
                {renderStars(
                  5,
                  stopData.quality_rating,
                  (val) => setStopData({ ...stopData, quality_rating: val })
                )}
                <span className="rating-hint">
                  Wie zufrieden sind Sie mit dem Ergebnis?
                </span>
              </div>

              <div className="stop-dialog-field">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={stopData.rework_required}
                    onChange={(e) =>
                      setStopData({ ...stopData, rework_required: e.target.checked })
                    }
                  />
                  Nacharbeit erforderlich
                </label>
              </div>

              <div className="stop-dialog-field">
                <label>Notizen (optional)</label>
                <textarea
                  value={stopData.notes}
                  onChange={(e) =>
                    setStopData({ ...stopData, notes: e.target.value })
                  }
                  placeholder="Zusätzliche Notizen..."
                  rows={3}
                  className="notes-textarea"
                />
              </div>

              <div className="stop-dialog-summary">
                <strong>Zeit:</strong> {formatTime(elapsedTime)}
              </div>
            </div>

            {error && <div className="stop-dialog-error">{error}</div>}

            <div className="stop-dialog-actions">
              <button
                onClick={handleStopCancel}
                className="dialog-button dialog-button-cancel"
                disabled={loading}
              >
                Abbrechen
              </button>
              <button
                onClick={handleStopConfirm}
                className="dialog-button dialog-button-confirm"
                disabled={loading}
              >
                {loading ? 'Speichern...' : 'Stoppen & Speichern'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default TimerWidget;
