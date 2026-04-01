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
  // Use the axios baseURL so auth header is automatically included via interceptor.
  // We open the URL directly so the browser triggers a file download.
  const baseUrl = (apiClient.defaults.baseURL ?? '').replace(/\/$/, '');
  const token = localStorage.getItem('access_token');
  // Build a temporary anchor with the auth token as a query param would expose it,
  // so we fetch and create a blob URL instead.
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
      window.open(`${baseUrl}/import/customers/template`, '_blank');
    });
  void baseUrl; // suppress unused-var lint
  void token;
};
