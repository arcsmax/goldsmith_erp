// Admin API Service — system health, backup management
import apiClient from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ComponentHealth {
  status: string;
  latency_ms?: number;
  used_memory_mb?: number;
  free_gb?: number;
  total_gb?: number;
  used_percent?: number;
  error?: string;
}

export interface FullHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  components: {
    database: ComponentHealth;
    redis: ComponentHealth;
    disk: ComponentHealth;
  };
  version: string;
  uptime_seconds: number;
  timestamp: string;
}

export interface BusinessMetrics {
  orders_this_month: number;
  completed_this_month: number;
  error?: string;
}

export interface BackupInfo {
  filename: string | null;
  size_mb: number;
  timestamp: string | null;
  backup_count: number;
  backup_dir: string;
  error?: string;
}

export interface RequestMetrics {
  total_requests: number;
  requests_per_minute: number;
  current_minute_requests: number;
  response_time_ms: {
    p50: number;
    p95: number;
    p99: number;
  };
  errors: {
    '4xx': number;
    '5xx': number;
  };
}

export interface SystemInfo {
  health: FullHealth;
  business_metrics: BusinessMetrics;
  backup: BackupInfo;
  request_metrics: RequestMetrics;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/**
 * Fetch basic health status (no auth required).
 * Used by HealthDot — polls every 60 s.
 */
export const getHealth = async (): Promise<FullHealth> => {
  const response = await apiClient.get<FullHealth>('/health', {
    // Call via absolute path — health endpoint is not under /api/v1
    baseURL: '',
  });
  return response.data;
};

/**
 * Fetch full system info (ADMIN only).
 */
export const getSystemInfo = async (): Promise<SystemInfo> => {
  const response = await apiClient.get<SystemInfo>('/admin/system-info');
  return response.data;
};

/**
 * Trigger a database backup (ADMIN only).
 * Returns immediately with {"status": "started"}.
 */
export const triggerBackup = async (): Promise<{ status: string; note?: string }> => {
  const response = await apiClient.post<{ status: string; note?: string }>(
    '/admin/trigger-backup'
  );
  return response.data;
};

// ---------------------------------------------------------------------------
// Email configuration types & calls (ADMIN only)
// ---------------------------------------------------------------------------

export interface EmailConfig {
  smtp_host: string | null;
  smtp_port: number;
  smtp_user: string | null;
  smtp_from: string | null;
  email_notifications_enabled: boolean;
  password_configured: boolean;
}

export interface EmailConfigUpdate {
  smtp_host?: string | null;
  smtp_port?: number;
  smtp_user?: string | null;
  smtp_password?: string | null;
  smtp_from?: string | null;
  email_notifications_enabled?: boolean;
}

export interface EmailTestResult {
  success: boolean;
  message: string;
}

/** Fetch current SMTP configuration (ADMIN only). */
export const getEmailConfig = async (): Promise<EmailConfig> => {
  const response = await apiClient.get<EmailConfig>('/admin/email-config');
  return response.data;
};

/** Update SMTP configuration (ADMIN only). */
export const updateEmailConfig = async (
  data: EmailConfigUpdate
): Promise<EmailConfig> => {
  const response = await apiClient.put<EmailConfig>('/admin/email-config', data);
  return response.data;
};

/** Send a test email to verify SMTP setup (ADMIN only). */
export const sendTestEmail = async (to: string): Promise<EmailTestResult> => {
  const response = await apiClient.post<EmailTestResult>('/admin/email-test', { to });
  return response.data;
};

// ---------------------------------------------------------------------------
// CSV customer import types & calls (ADMIN only)
// ---------------------------------------------------------------------------

export interface ImportRowError {
  row_number: number;
  field: string | null;
  message: string;
}

export interface ImportResult {
  imported_count: number;
  skipped_count: number;
  error_count: number;
  total_rows: number;
  errors: ImportRowError[];
}

/**
 * Upload a CSV file and import customer records (ADMIN only).
 * Returns a summary with per-row errors.
 */
export const importCustomersCsv = async (file: File): Promise<ImportResult> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<ImportResult>('/import/customers', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

/** Download the CSV import template (ADMIN only). */
export const downloadCustomerCsvTemplate = (): void => {
  // Fetch the CSV template via apiClient (HttpOnly cookie sent automatically)
  // and trigger a file download via a blob URL.
  apiClient
    .get('/import/customers/template', { responseType: 'blob' })
    .then((res) => {
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'kunden-import-vorlage.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    })
    .catch(() => {
      // Fallback: direct link (works if session cookie auth is in place)
      const baseUrl = (apiClient.defaults.baseURL ?? '').replace(/\/$/, '');
      window.open(`${baseUrl}/import/customers/template`, '_blank');
    });
  void token;
};

// ---------------------------------------------------------------------------
// V1.1 Slice 13 — scan-metrics dashboard (ADMIN only)
// ---------------------------------------------------------------------------

/**
 * V1.1 acceptance-gate metrics (spec §14.a rows a–f). All ratios are
 * 0–100 floats; `null` means the window had zero denominator (e.g. fresh
 * install, no eligible rows). The dashboard renders "—" for null.
 */
export interface ScanMetrics {
  scan_adoption_pct_30d: number | null;
  scan_breadth_pct_7d: number | null;
  fab_tap_to_timer_ms_p50: number | null;
  fab_tap_to_timer_ms_p95: number | null;
  alloy_override_count_30d: number;
  camera_fallback_count_30d: number;
  usb_hid_scan_count_30d: number;
  window_days_primary: number;
  window_days_breadth: number;
  computed_at: string;
}

/** Fetch V1.1 scan-adoption gate metrics (ADMIN only). */
export const getScanMetrics = async (): Promise<ScanMetrics> => {
  const response = await apiClient.get<ScanMetrics>('/admin/scan-metrics');
  return response.data;
};
