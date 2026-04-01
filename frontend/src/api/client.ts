// API Client Configuration
import axios, {
  AxiosInstance,
  AxiosError,
  InternalAxiosRequestConfig,
} from 'axios';

// Base API URL - uses proxy in development via vite.config.ts
const BASE_URL = '/api/v1';

// Create axios instance with default config
const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  // withCredentials ensures HttpOnly cookies (access_token) are sent
  // automatically with every request — required for cookie-based auth.
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ---------------------------------------------------------------------------
// Token refresh state
// ---------------------------------------------------------------------------

/**
 * True while a refresh request is in flight.
 * Any other 401s that arrive during this window are queued, not sent to /refresh
 * again — preventing a refresh storm.
 */
let isRefreshing = false;

/**
 * Queue of resolve/reject callbacks from requests that arrived while a refresh
 * was already in flight.  Once the refresh settles, we drain the queue so all
 * pending requests retry (or fail) with the new token.
 */
type QueueEntry = {
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
};
let failedQueue: QueueEntry[] = [];

/** Drain the queue after a refresh attempt. */
function processQueue(error: unknown, token: string | null): void {
  for (const entry of failedQueue) {
    if (error) {
      entry.reject(error);
    } else if (token) {
      entry.resolve(token);
    }
  }
  failedQueue = [];
}

// ---------------------------------------------------------------------------
// Request interceptor — attach current access token
// ---------------------------------------------------------------------------
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error)
);

// ---------------------------------------------------------------------------
// Response interceptor — transparent token refresh on 401
// ---------------------------------------------------------------------------
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // --- 401 handling ---
    if (error.response?.status === 401) {
      // Never retry the refresh endpoint itself — that would be an infinite loop.
      // The auth router is mounted at /api/v1 with no /auth sub-prefix, so the
      // actual path is /api/v1/refresh (not /api/v1/auth/refresh).
      const isRefreshEndpoint = originalRequest.url?.includes('/refresh');
      if (isRefreshEndpoint) {
        // Refresh failed — clear storage and redirect to login
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }

      // If we already retried this specific request, stop here.
      if (originalRequest._retry) {
        return Promise.reject(error);
      }

      if (isRefreshing) {
        // Another refresh is in flight — queue this request and wait.
        return new Promise<unknown>((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              if (originalRequest.headers) {
                originalRequest.headers.Authorization = `Bearer ${token}`;
              }
              resolve(apiClient(originalRequest));
            },
            reject,
          });
        });
      }

      // Mark the original request as retried so it does not loop.
      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // Attempt token refresh.  The current token is sent via the request
        // interceptor above (it is still in localStorage at this point).
        // The auth router is mounted at /api/v1 with no /auth sub-prefix.
        // The actual backend path is POST /api/v1/refresh.
        const refreshResponse = await apiClient.post<{
          access_token: string;
          token_type: string;
        }>('/refresh');

        const newToken = refreshResponse.data.access_token;

        // Persist the new token
        localStorage.setItem('access_token', newToken);

        // Drain the queue with the new token
        processQueue(null, newToken);

        // Retry the original request with the fresh token
        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
        }
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed — reject all queued requests and force re-login
        processQueue(refreshError, null);
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    // --- 403 Forbidden ---
    if (error.response?.status === 403) {
      console.error('Access forbidden:', error.response.data);
    }

    // --- 500 Internal Server Error ---
    if (error.response?.status === 500) {
      console.error('Server error:', error.response.data);
    }

    return Promise.reject(error);
  }
);

export default apiClient;
