// Time Tracking Context - Global time tracking state management
import React, { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from 'react';
import { timeTrackingApi } from '../api/time-tracking';
import { activitiesApi } from '../api/activities';
import apiClient from '../api/client';
import { useAuth } from './AuthContext';
import { useWebSocket, type WebSocketMessage } from '../hooks/useWebSocket';
import {
  TimeEntry,
  Activity,
  TimeEntryStartInput,
  TimeEntryStopInput,
} from '../types';

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
   * H18 — atomic stop-old + start-new via the dedicated
   * POST /time-tracking/{entry_id}/switch endpoint. The service-layer
   * `switch_timer` enforces per-user scope (A5.1) and the stale-timer
   * guard (A5.2) in a single transaction + single pubsub event.
   *
   * A 409 TIMER_POSSIBLY_STALE surfaces as a thrown error with `.code`
   * set, so `ActionHandlers.switch_timer` can render the Mittagspause
   * modal (A11.5).
   */
  switchTracking: (
    orderId: number,
    activityId: number,
    options?: { location?: string; idempotencyKey?: string }
  ) => Promise<TimeEntry>;
  refreshRunningEntry: () => Promise<TimeEntry | null>;
  refreshActivities: () => Promise<void>;
  clearError: () => void;
}

// Create the context
const TimeTrackingContext = createContext<TimeTrackingContextType | undefined>(undefined);

// Provider Props
interface TimeTrackingProviderProps {
  children: ReactNode;
}

/**
 * TimeTrackingProvider Component
 * Manages time tracking state and provides methods to the app
 */
export const TimeTrackingProvider: React.FC<TimeTrackingProviderProps> = ({ children }) => {
  const [runningEntry, setRunningEntry] = useState<TimeEntry | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /**
   * Fetch running entry from server
   */
  const refreshRunningEntry = useCallback(async () => {
    try {
      const entry = await timeTrackingApi.getRunning();
      setRunningEntry(entry);
      return entry;
    } catch (err) {
      console.error('Failed to fetch running entry:', err);
      // Don't set error here, as this is background polling
      return null;
    }
  }, []);

  /**
   * Fetch activities from server
   */
  const refreshActivities = useCallback(async () => {
    try {
      const allActivities = await activitiesApi.getAll({ sortByUsage: true });
      setActivities(allActivities);
    } catch (err) {
      console.error('Failed to fetch activities:', err);
      setError('Aktivitäten konnten nicht geladen werden');
    }
  }, []);

  /**
   * Start time tracking for an order
   */
  const startTracking = async (
    orderId: number,
    activityId: number,
    location?: string
  ): Promise<void> => {
    try {
      setIsLoading(true);
      setError(null);

      // Check if already tracking
      if (runningEntry) {
        throw new Error('Es läuft bereits eine Zeiterfassung. Bitte stoppen Sie diese zuerst.');
      }

      const startData: TimeEntryStartInput = {
        order_id: orderId,
        activity_id: activityId,
        location,
      };

      const entry = await timeTrackingApi.start(startData);
      setRunningEntry(entry);

      // Start polling for updates
      startPolling();
    } catch (err: any) {
      console.error('Failed to start tracking:', err);
      setError(err.message || 'Zeiterfassung konnte nicht gestartet werden');
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Stop time tracking
   */
  const stopTracking = async (
    entryId: string,
    stopData: TimeEntryStopInput
  ): Promise<void> => {
    try {
      setIsLoading(true);
      setError(null);

      await timeTrackingApi.stop(entryId, stopData);
      setRunningEntry(null);

      // Stop polling
      stopPolling();

      // Refresh activities to update usage counts
      await refreshActivities();
    } catch (err: any) {
      console.error('Failed to stop tracking:', err);
      setError(err.message || 'Zeiterfassung konnte nicht gestoppt werden');
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * H18 — switchTracking via dedicated POST /switch endpoint.
   *
   * Calls the backend's atomic switch_timer service in a single HTTP
   * round-trip. The server does stop-old + start-new in one transaction
   * and publishes a single `time_tracking_updates` event. No risk of a
   * dangling timer on network failure between stop and start (the failure
   * mode the V1.1 stop+start emulation had).
   *
   * A 409 TIMER_POSSIBLY_STALE is forwarded to callers with `.code` set
   * so `ActionHandlers.switch_timer` can render the Mittagspause modal
   * (A11.5).
   *
   * If no timer is running we surface an explicit error rather than
   * silently start one — callers that want the degrade-to-start path
   * (e.g. ActionHandlers) check `runningEntryId` first and dispatch
   * `start_timer` themselves.
   */
  const switchTracking = useCallback(
    async (
      orderId: number,
      activityId: number,
      options?: { location?: string; idempotencyKey?: string }
    ): Promise<TimeEntry> => {
      try {
        setIsLoading(true);
        setError(null);

        if (!runningEntry) {
          throw new Error('Kein laufender Timer — Wechsel nicht möglich.');
        }

        const idempotencyKey = options?.idempotencyKey ?? crypto.randomUUID();
        const response = await apiClient.post<TimeEntry>(
          `/time-tracking/${runningEntry.id}/switch`,
          {
            new_order_id: orderId,
            activity_id: activityId,
            location: options?.location,
          },
          {
            headers: {
              'Idempotency-Key': idempotencyKey,
              'X-Client-Created-At': new Date().toISOString(),
            },
          },
        );
        const entry = response.data;
        setRunningEntry(entry);
        await refreshRunningEntry();
        return entry;
      } catch (err: any) {
        // Forward 409 TIMER_POSSIBLY_STALE to callers with a normalised
        // `.code` field so ActionHandlers.switch_timer can render the
        // Mittagspause modal (A11.5). Today the handler just toasts —
        // V1.2 will split out a dedicated modal.
        const detail = err?.response?.data?.detail;
        if (
          err?.response?.status === 409 &&
          detail &&
          typeof detail === 'object' &&
          (detail as { code?: string }).code === 'TIMER_POSSIBLY_STALE'
        ) {
          const staleError = new Error(
            'Timer läuft auffällig lange — Mittagspause abziehen?',
          );
          (staleError as any).code = 'TIMER_POSSIBLY_STALE';
          (staleError as any).detail = detail;
          setError(staleError.message);
          throw staleError;
        }
        console.error('Failed to switch tracking:', err);
        setError(err.message || 'Timer konnte nicht gewechselt werden');
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [runningEntry, refreshRunningEntry],
  );

  /**
   * Start polling for running entry
   */
  const startPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }
    pollingIntervalRef.current = setInterval(() => {
      refreshRunningEntry();
    }, 5000);
  }, [refreshRunningEntry]);

  /**
   * Stop polling
   */
  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  /**
   * Clear error
   */
  const clearError = () => {
    setError(null);
  };

  /**
   * Initialize on mount
   */
  useEffect(() => {
    const initialize = async () => {
      setIsLoading(true);
      try {
        // Fetch running entry and activities in parallel
        const [entry] = await Promise.all([
          refreshRunningEntry(),
          refreshActivities(),
        ]);

        // If there's a running entry, start polling
        if (entry) {
          startPolling();
        }
      } catch (err) {
        console.error('Failed to initialize time tracking:', err);
      } finally {
        setIsLoading(false);
      }
    };

    initialize();

    // Cleanup on unmount
    return () => {
      stopPolling();
    };
  }, []); // Empty deps - only run on mount

  /**
   * Save running entry to localStorage as backup
   */
  useEffect(() => {
    if (runningEntry) {
      localStorage.setItem('running_time_entry', JSON.stringify(runningEntry));
    } else {
      localStorage.removeItem('running_time_entry');
    }
  }, [runningEntry]);

  /**
   * Slice 11 — Pub/sub refresh on time_tracking_updates.
   *
   * The backend publishes time_tracking_updates events with a `source`
   * field (e.g. "scan") whenever a scan-triggered switch lands. We
   * subscribe and re-fetch the running entry so TimerWidget reflects
   * the new state within 1s even if the pubsub fires from another
   * client session (Meister's laptop pushing a change the Werkbank
   * iPad needs to pick up).
   */
  const { user } = useAuth();
  const handleWsMessage = useCallback(
    (message: WebSocketMessage): void => {
      const type = typeof message.type === 'string' ? message.type : '';
      const channel =
        typeof (message as Record<string, unknown>).channel === 'string'
          ? ((message as Record<string, unknown>).channel as string)
          : '';
      if (
        type === 'time_tracking_updates' ||
        channel === 'time_tracking_updates'
      ) {
        void refreshRunningEntry();
      }
    },
    [refreshRunningEntry],
  );
  useWebSocket({
    userId: user?.id ?? null,
    onMessage: handleWsMessage,
  });

  const value: TimeTrackingContextType = {
    runningEntry,
    activities,
    isLoading,
    error,
    startTracking,
    stopTracking,
    switchTracking,
    refreshRunningEntry,
    refreshActivities,
    clearError,
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
