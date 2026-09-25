// Time Tracking Context — a thin wrapper over TanStack Query (W4-03).
//
// Decision (docs/technical/FRONTEND_DATA_LAYER.md, "When to keep a context"):
// the context stays because many screens (MainLayout's TimerWidget, ScanFab,
// ScanOverlay, ScannerPage, TimeTrackingTab) need the SAME cross-page timer
// state and the same start/stop/switch/pause commands. It no longer holds a
// copy of server data:
//
//   * the running timer is the query `runningEntryQuery(userId)`
//     (api/timeTrackingQueries.ts, key ['timer', 'running', userId]);
//   * activities are `activitiesQuery()` (key ['timer', 'activities', …]);
//   * commands are useMutation; they write the returned entry into the cache
//     and invalidate the ['timer'] root (entry lists, activity usage) and
//     ['dashboard'].
//
// Realtime: a `time_tracking_updates` hint invalidates ['timer'] in
// lib/realtimeInvalidation.ts (the one bridge); this provider registers no
// socket handler of its own. Polling (5 s) runs only while a timer runs
// (FE-19). Everything is keyed per user (FE-07): after logout the query is
// disabled and `runningEntry` is null.
//
// The only UI state kept here is the last command error (`error`).
import React, { createContext, useCallback, useContext, useState, ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { timeTrackingApi } from '../api/time-tracking';
import { queryKeys } from '../api/queryKeys';
import { activitiesQuery, runningEntryQuery } from '../api/timeTrackingQueries';
import { getErrorMessage } from '../lib/errors';
// Side effect: applies the stored Werkbank-Modus root class at app start.
import '../lib/benchMode';
import { useAuth } from './AuthContext';
import { TimeEntry, Activity, TimeEntryStopInput } from '../types';

// Context Type
interface TimeTrackingContextType {
  // State
  runningEntry: TimeEntry | null;
  activities: Activity[];
  isLoading: boolean;
  error: string | null;

  // Methods
  startTracking: (orderId: number, activityId: number, location?: string) => Promise<void>;
  stopTracking: (entryId: string, stopData: TimeEntryStopInput) => Promise<void>;
  /**
   * H18 — atomic stop-old + start-new via POST /time-tracking/{entry_id}/switch.
   * A 409 TIMER_POSSIBLY_STALE surfaces as a thrown error with `.code` set,
   * so `ActionHandlers.switch_timer` can render the Mittagspause modal (A11.5).
   */
  switchTracking: (
    orderId: number,
    activityId: number,
    options?: { location?: string; idempotencyKey?: string }
  ) => Promise<TimeEntry>;
  refreshRunningEntry: () => Promise<TimeEntry | null>;
  refreshActivities: () => Promise<void>;
  clearError: () => void;
  /** D-15: manually pause the running entry. 409 if already paused. */
  pauseTracking: () => Promise<void>;
  /** D-15: end the manual pause. 409 if not paused. */
  resumeTracking: () => Promise<void>;
}

const TimeTrackingContext = createContext<TimeTrackingContextType | undefined>(undefined);

interface TimeTrackingProviderProps {
  children: ReactNode;
}

interface StaleTimerError extends Error {
  code: 'TIMER_POSSIBLY_STALE';
  detail: unknown;
}

/** Map a 409 TIMER_POSSIBLY_STALE from /switch to an error with `.code`. */
function toStaleTimerError(err: unknown): StaleTimerError | null {
  const response = (err as { response?: { status?: number; data?: { detail?: unknown } } })
    ?.response;
  const detail = response?.data?.detail;
  if (
    response?.status !== 409 ||
    !detail ||
    typeof detail !== 'object' ||
    (detail as { code?: string }).code !== 'TIMER_POSSIBLY_STALE'
  ) {
    return null;
  }
  const staleError = new Error(
    'Timer läuft auffällig lange — Mittagspause abziehen?',
  ) as StaleTimerError;
  staleError.code = 'TIMER_POSSIBLY_STALE';
  staleError.detail = detail;
  return staleError;
}

/** Guard errors (plain Error, German text) keep their message; HTTP errors are mapped. */
function commandErrorMessage(err: unknown, fallback: string): string {
  const isHttp = typeof err === 'object' && err !== null && ('response' in err || 'isAxiosError' in err);
  if (!isHttp && err instanceof Error && err.message.length > 0) return err.message;
  return getErrorMessage(err, fallback);
}

type SwitchVariables = {
  entryId: string;
  orderId: number;
  activityId: number;
  location?: string;
  idempotencyKey: string;
};

function useTimerMutations(userId: number | null) {
  const queryClient = useQueryClient();
  const runningKey = queryKeys.timer.running(userId);

  const setRunning = useCallback(
    (entry: TimeEntry | null) => queryClient.setQueryData(runningKey, entry),
    // runningKey is derived from userId only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, userId],
  );
  const invalidate = useCallback(
    () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.timer.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all }),
      ]),
    [queryClient],
  );
  const onEntry = async (entry: TimeEntry | null) => {
    setRunning(entry);
    await invalidate();
  };

  const start = useMutation({
    mutationFn: (input: { orderId: number; activityId: number; location?: string }) =>
      timeTrackingApi.start({
        order_id: input.orderId,
        activity_id: input.activityId,
        location: input.location,
      }),
    onSuccess: onEntry,
  });
  const stop = useMutation({
    mutationFn: (input: { entryId: string; stopData: TimeEntryStopInput }) =>
      timeTrackingApi.stop(input.entryId, input.stopData),
    onSuccess: () => onEntry(null),
  });
  const pause = useMutation({
    mutationFn: (entryId: string) => timeTrackingApi.pause(entryId),
    onSuccess: onEntry,
  });
  const resume = useMutation({
    mutationFn: (entryId: string) => timeTrackingApi.resume(entryId),
    onSuccess: onEntry,
  });
  const switchTimer = useMutation({
    mutationFn: (v: SwitchVariables) =>
      timeTrackingApi.switchTimer(
        v.entryId,
        { new_order_id: v.orderId, activity_id: v.activityId, location: v.location },
        v.idempotencyKey,
      ),
    onSuccess: onEntry,
  });

  const isPending =
    start.isPending || stop.isPending || pause.isPending || resume.isPending || switchTimer.isPending;
  return { start, stop, pause, resume, switchTimer, isPending, invalidate };
}

/**
 * TimeTrackingProvider — cross-page timer state over the query cache.
 * Must sit inside the session's QueryClientProvider (App.tsx: AppQueryProvider).
 */
export const TimeTrackingProvider: React.FC<TimeTrackingProviderProps> = ({ children }) => {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [error, setError] = useState<string | null>(null);

  const runningQuery = useQuery(runningEntryQuery(userId));
  const activitiesResult = useQuery({ ...activitiesQuery(true), enabled: userId !== null });
  const mutations = useTimerMutations(userId);

  const runningEntry = userId === null ? null : runningQuery.data ?? null;
  const activities = userId === null ? [] : activitiesResult.data ?? [];

  /** Run a command, keep its German error for `error`, rethrow for the caller. */
  const run = async <T,>(fallback: string, command: () => Promise<T>): Promise<T> => {
    setError(null);
    try {
      return await command();
    } catch (err) {
      const stale = toStaleTimerError(err);
      if (stale) {
        setError(stale.message);
        throw stale;
      }
      console.error(fallback, { userId, err });
      setError(commandErrorMessage(err, fallback));
      throw err;
    }
  };

  const startTracking = (orderId: number, activityId: number, location?: string) =>
    run('Zeiterfassung konnte nicht gestartet werden', async () => {
      if (runningEntry) {
        throw new Error('Es läuft bereits eine Zeiterfassung. Bitte stoppen Sie diese zuerst.');
      }
      await mutations.start.mutateAsync({ orderId, activityId, location });
    });

  const stopTracking = (entryId: string, stopData: TimeEntryStopInput) =>
    run('Zeiterfassung konnte nicht gestoppt werden', async () => {
      await mutations.stop.mutateAsync({ entryId, stopData });
    });

  const pauseTracking = async (): Promise<void> => {
    if (!runningEntry) return;
    await run('Pausieren fehlgeschlagen', () => mutations.pause.mutateAsync(runningEntry.id));
  };

  const resumeTracking = async (): Promise<void> => {
    if (!runningEntry) return;
    await run('Fortsetzen fehlgeschlagen', () => mutations.resume.mutateAsync(runningEntry.id));
  };

  const switchTracking = (
    orderId: number,
    activityId: number,
    options?: { location?: string; idempotencyKey?: string },
  ) =>
    run('Timer konnte nicht gewechselt werden', async () => {
      if (!runningEntry) {
        throw new Error('Kein laufender Timer — Wechsel nicht möglich.');
      }
      return mutations.switchTimer.mutateAsync({
        entryId: runningEntry.id,
        orderId,
        activityId,
        location: options?.location,
        idempotencyKey: options?.idempotencyKey ?? crypto.randomUUID(),
      });
    });

  const refreshRunningEntry = useCallback(async (): Promise<TimeEntry | null> => {
    if (userId === null) return null;
    try {
      const result = await runningQuery.refetch();
      return result.data ?? null;
    } catch (err) {
      // Background refresh: the query keeps its error state for the UI.
      console.error('Laufender Timer konnte nicht aktualisiert werden', { userId, err });
      return null;
    }
  }, [runningQuery, userId]);

  const refreshActivities = useCallback(async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.timer.activities(true) });
  }, [queryClient]);

  const value: TimeTrackingContextType = {
    runningEntry,
    activities,
    isLoading: (userId !== null && runningQuery.isPending) || mutations.isPending,
    error:
      error ??
      (activitiesResult.isError ? 'Aktivitäten konnten nicht geladen werden' : null),
    startTracking,
    stopTracking,
    switchTracking,
    refreshRunningEntry,
    refreshActivities,
    clearError: () => setError(null),
    pauseTracking,
    resumeTracking,
  };

  return (
    <TimeTrackingContext.Provider value={value}>
      {children}
    </TimeTrackingContext.Provider>
  );
};

/**
 * useTimeTracking Hook
 * Custom hook to access time tracking context
 */
export const useTimeTracking = (): TimeTrackingContextType => {
  const context = useContext(TimeTrackingContext);
  if (context === undefined) {
    throw new Error('useTimeTracking must be used within a TimeTrackingProvider');
  }
  return context;
};
