import React, { useState, useEffect, useCallback } from 'react';
import { TimeEntry, TimeEntryStopInput } from '../types';
import { timeTrackingApi } from '../api/timeTracking';
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
  const [showStopDialog, setShowStopDialog] = useState(false);
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

  const handlePauseResume = async () => {
    if (!runningEntry) return;

    try {
      if (isPaused) {
        // Resume - just update UI state
        setIsPaused(false);
      } else {
        // Pause - add interruption
        setIsPaused(true);
        await timeTrackingApi.addInterruption(runningEntry.id, {
          reason: 'manual_pause',
          duration_minutes: 0, // Will be calculated on resume
        });
      }
    } catch (err) {
      console.error('Failed to pause/resume:', err);
      setError('Pause/Resume fehlgeschlagen');
      setIsPaused(!isPaused); // Revert state
    }
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
    } catch (err) {
      console.error('Failed to stop timer:', err);
      setError('Timer stoppen fehlgeschlagen');
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

  if (!runningEntry) {
    return null; // Don't show widget if no timer running
  }

  return (
    <>
      {/* Timer Widget (Sticky) */}
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
