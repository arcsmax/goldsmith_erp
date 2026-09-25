/**
 * TanStack Query options for the admin system page (W4-03).
 * See docs/technical/FRONTEND_DATA_LAYER.md.
 *
 * Keys live under the `['admin']` root so one invalidation refreshes every
 * admin panel. Kept next to api/admin.ts (the admin page is the only
 * consumer); fold into queryKeys.ts when a second screen needs them.
 */
import { queryOptions } from '@tanstack/react-query';
import { fetchTheme } from '../hooks/useTheme';
import { logError } from '../lib/logError';
import {
  getEmailConfig,
  getOutbox,
  getSystemInfo,
  getWorkshopSettings,
  type OutboxStatus,
} from './admin';

/** The system status refreshes itself every minute. */
export const SYSTEM_INFO_REFRESH_MS = 60_000;

export const adminKeys = {
  all: ['admin'] as const,
  systemInfo: () => [...adminKeys.all, 'system-info'] as const,
  workshopSettings: () => [...adminKeys.all, 'workshop-settings'] as const,
  emailConfig: () => [...adminKeys.all, 'email-config'] as const,
  outboxAll: () => [...adminKeys.all, 'outbox'] as const,
  outbox: (status: OutboxStatus) => [...adminKeys.outboxAll(), status] as const,
  theme: () => [...adminKeys.all, 'theme'] as const,
};

/** Log with context and rethrow, so the query still shows its error state. */
function logged<T>(context: string, fetcher: () => Promise<T>): () => Promise<T> {
  return async () => {
    try {
      return await fetcher();
    } catch (err) {
      logError(context, err);
      throw err;
    }
  };
}

export const systemInfoQuery = () =>
  queryOptions({
    queryKey: adminKeys.systemInfo(),
    queryFn: logged('admin.systemInfo', getSystemInfo),
    refetchInterval: SYSTEM_INFO_REFRESH_MS,
  });

export const workshopSettingsQuery = () =>
  queryOptions({
    queryKey: adminKeys.workshopSettings(),
    queryFn: logged('admin.workshopSettings', getWorkshopSettings),
  });

export const emailConfigQuery = () =>
  queryOptions({
    queryKey: adminKeys.emailConfig(),
    queryFn: logged('admin.emailConfig', getEmailConfig),
  });

export const outboxQuery = (status: OutboxStatus) =>
  queryOptions({
    queryKey: adminKeys.outbox(status),
    queryFn: logged(`admin.outbox.${status}`, () => getOutbox(status)),
  });

export const themeQuery = () =>
  queryOptions({
    queryKey: adminKeys.theme(),
    queryFn: logged('admin.theme', fetchTheme),
    // The editor previews unsaved colours; never overwrite the draft by a
    // background refetch.
    refetchOnWindowFocus: false,
  });
