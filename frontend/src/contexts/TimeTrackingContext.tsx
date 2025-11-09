// Time Tracking Context - Global time tracking state management
import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { timeTrackingApi } from '../api/timeTracking';
import { activitiesApi } from '../api/activities';
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
  refreshRunningEntry: () => Promise<void>;
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
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);

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
   * Start polling for running entry
   */
  const startPolling = useCallback(() => {
    // Clear any existing interval
    if (pollingInterval) {
      clearInterval(pollingInterval);
    }

    // Poll every 5 seconds
    const interval = setInterval(() => {
      refreshRunningEntry();
    }, 5000);

    setPollingInterval(interval);
  }, [pollingInterval, refreshRunningEntry]);

  /**
   * Stop polling
   */
  const stopPolling = useCallback(() => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      setPollingInterval(null);
    }
  }, [pollingInterval]);

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
        await Promise.all([
          refreshRunningEntry(),
          refreshActivities(),
        ]);

        // If there's a running entry, start polling
        const entry = await refreshRunningEntry();
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

  const value: TimeTrackingContextType = {
    runningEntry,
    activities,
    isLoading,
    error,
    startTracking,
    stopTracking,
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
