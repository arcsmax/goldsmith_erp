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
