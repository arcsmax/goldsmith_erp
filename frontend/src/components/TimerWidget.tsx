// TimerWidget — the always-mounted timer FAB (W4-03, bench mode).
//
// Props are unchanged, so MainLayout keeps passing TimeTrackingContext's
// runningEntry / refresh / pause / resume. Three states:
//   * collapsed FAB (clock icon, elapsed time while a timer runs);
//   * start form (TimerStartForm, queries mount only while it is open);
//   * expanded controls: "Läuft" + StatusBadge "Pausiert", elapsed time,
//     56px Pause/Weiter and Stopp buttons, and the stop dialog (Modal).
//
// FE-10: there is no client-side pause. The ticker always shows gross
// wall-clock time from start_time; the "Pausiert" badge is the source of
// truth for the server-side pause (D-15), which the server excludes from
// net hours.
import React, { useEffect, useState } from 'react';

import { timeTrackingApi, type RunningTimeEntry } from '../api/time-tracking';
import { getErrorMessage } from '../lib/errors';
import { Button, Icon, IconButton } from '../ui';
import { StatusBadge } from '../ui/StatusBadge';
import { TimeEntryStopInput } from '../types';
import { parseUTC } from '../utils/formatters';
import { RunningTimerEditSheet } from './time-tracking/RunningTimerEditSheet';
import { TimerStartForm } from './time-tracking/TimerStartForm';
import { TimerStopDialog } from './time-tracking/TimerStopDialog';
import '../styles/components/TimerWidget.css';

interface TimerWidgetProps {
  /** activity_name / order_title (GET /running) are shown when present. */
  runningEntry: RunningTimeEntry | null;
  onStop: () => void;
  onRefresh?: () => void;
  /** D-15: manually pause the running entry. Optional so existing callers
   *  (and tests) keep working; the Pause button is hidden without it. */
  onPause?: () => Promise<void> | void;
  /** D-15: end the manual pause. */
  onResume?: () => Promise<void> | void;
}

const TICK_MS = 1000;

/** Server timestamps may be naive or already timezone-aware; parseUTC handles both. */
function parseStart(startTime: string): number {
  return parseUTC(startTime).getTime();
}

function formatElapsed(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  const mmss = `${minutes.toString().padStart(hours > 0 ? 2 : 1, '0')}:${secs.toString().padStart(2, '0')}`;
  return hours > 0 ? `${hours}:${mmss}` : mmss;
}

function useElapsedSeconds(entry: RunningTimeEntry | null): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!entry) return undefined;
    const start = parseStart(entry.start_time);
    const update = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    update();
    const interval = setInterval(update, TICK_MS);
    return () => clearInterval(interval);
  }, [entry]);
  return elapsed;
}

/** "Auftrag #12 – Ring weiten · Polieren" (names from GET /running when present). */
export function describeRunning(entry: RunningTimeEntry): string {
  const job = entry.order_title
    ? `Auftrag #${entry.order_id} – ${entry.order_title}`
    : `Auftrag #${entry.order_id}`;
  return entry.activity_name ? `${job} · ${entry.activity_name}` : job;
}

function isAlreadyStopped(err: unknown): boolean {
  const response = (err as { response?: { status?: number; data?: { detail?: unknown } } })?.response;
  const detail = response?.data?.detail;
  return (typeof detail === 'string' && detail.includes('bereits gestoppt')) || response?.status === 400;
}

const TimerWidget: React.FC<TimerWidgetProps> = ({
  runningEntry,
  onStop,
  onRefresh,
  onPause,
  onResume,
}) => {
  const elapsed = useElapsedSeconds(runningEntry);
  const elapsedLabel = formatElapsed(elapsed);
  const [isCollapsed, setIsCollapsed] = useState(true);
  const [showStartForm, setShowStartForm] = useState(false);
  const [showStopDialog, setShowStopDialog] = useState(false);
  const [showEditSheet, setShowEditSheet] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // External "expand timer" events (e.g. tapping a running entry row).
  useEffect(() => {
    const handleExpand = () => {
      setIsCollapsed(false);
      setShowStartForm(false);
    };
    window.addEventListener('timer:expand', handleExpand);
    return () => window.removeEventListener('timer:expand', handleExpand);
  }, []);

  const finishStop = () => {
    setShowStopDialog(false);
    onStop();
    onRefresh?.();
  };

  const handleStopConfirm = async (input: TimeEntryStopInput) => {
    if (!runningEntry) return;
    setIsBusy(true);
    setError(null);
    try {
      await timeTrackingApi.stop(runningEntry.id, input);
      finishStop();
    } catch (err) {
      if (isAlreadyStopped(err)) {
        finishStop();
      } else {
        console.error('Timer konnte nicht gestoppt werden', { entryId: runningEntry.id, err });
        setError(getErrorMessage(err, 'Timer stoppen fehlgeschlagen'));
      }
    } finally {
      setIsBusy(false);
    }
  };

  const runPauseCommand = async (command: (() => Promise<void> | void) | undefined, fallback: string) => {
    if (!command) return;
    setIsBusy(true);
    setError(null);
    try {
      await command();
    } catch (err) {
      setError(getErrorMessage(err, fallback));
    } finally {
      setIsBusy(false);
    }
  };

  const handleFabClick = () => {
    if (runningEntry) {
      setIsCollapsed(false);
      setShowStartForm(false);
    } else {
      setShowStartForm((prev) => !prev);
    }
  };

  if (showStartForm && !runningEntry) {
    return (
      <TimerStartForm
        onClose={() => {
          setShowStartForm(false);
          setIsCollapsed(true);
        }}
        onStarted={() => {
          setShowStartForm(false);
          onRefresh?.();
        }}
      />
    );
  }

  if (isCollapsed || !runningEntry) {
    return (
      <button
        type="button"
        className={`timer-fab ${runningEntry ? 'timer-fab--active' : ''}`}
        onClick={handleFabClick}
        title={runningEntry ? `${elapsedLabel} – Tippen zum Öffnen` : 'Zeiterfassung starten'}
      >
        <Icon name="clock" className="timer-fab-icon" />
        {runningEntry && <span className="timer-fab-time">{elapsedLabel}</span>}
        {runningEntry?.is_paused && <span className="ui-visually-hidden"> Pausiert</span>}
      </button>
    );
  }

  const isPaused = Boolean(runningEntry.is_paused);
  return (
    <>
      <section
        className={`timer-widget ${isPaused ? 'timer-widget--paused' : ''}`}
        aria-label="Laufende Zeiterfassung"
      >
        <div className="timer-widget-content">
          <div className="timer-info">
            <div className="timer-label">
              <Icon name="clock" /> <span>Läuft</span>
            </div>
            {isPaused && <StatusBadge kind="timeEntry" status="paused" size="lg" />}
            <div className="timer-time">{elapsedLabel}</div>
            <div className="timer-activity">{describeRunning(runningEntry)}</div>
            {runningEntry.location && (
              <div className="timer-label">
                <span>Ort: {runningEntry.location}</span>
              </div>
            )}
          </div>

          <div className="timer-controls">
            {isPaused
              ? onResume && (
                  <Button
                    size="lg"
                    variant="secondary"
                    icon="arrow-right"
                    disabled={isBusy}
                    onClick={() => void runPauseCommand(onResume, 'Fortsetzen fehlgeschlagen')}
                  >
                    Weiter
                  </Button>
                )
              : onPause && (
                  <Button
                    size="lg"
                    variant="secondary"
                    icon="pause"
                    disabled={isBusy}
                    onClick={() => void runPauseCommand(onPause, 'Pausieren fehlgeschlagen')}
                  >
                    Pause
                  </Button>
                )}
            <Button
              size="lg"
              variant="secondary"
              icon="pencil"
              disabled={isBusy}
              onClick={() => setShowEditSheet(true)}
            >
              Bearbeiten
            </Button>
            <Button size="lg" icon="check" disabled={isBusy} onClick={() => setShowStopDialog(true)}>
              Stopp
            </Button>
            <IconButton
              icon="chevron-down"
              label="Minimieren"
              size="lg"
              onClick={() => setIsCollapsed(true)}
            />
          </div>
        </div>

        {error && !showStopDialog && (
          <p className="timer-error" role="alert">
            {error}
          </p>
        )}
      </section>

      {showEditSheet && (
        <RunningTimerEditSheet
          entry={runningEntry}
          onClose={() => setShowEditSheet(false)}
          onSaved={() => onRefresh?.()}
        />
      )}

      <TimerStopDialog
        open={showStopDialog}
        elapsedLabel={elapsedLabel}
        isSaving={isBusy}
        error={showStopDialog ? error : null}
        onCancel={() => {
          setShowStopDialog(false);
          setError(null);
        }}
        onConfirm={(input) => void handleStopConfirm(input)}
      />
    </>
  );
};

export default TimerWidget;
