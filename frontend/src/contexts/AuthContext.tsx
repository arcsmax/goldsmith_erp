// Authentication Context - Global auth state management
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authApi } from '../api';
import { PROBE_FREE_PATHS } from '../api/client';
import {
  UserType,
  UserRole,
  LoginCredentials,
  UserCreateInput,
  AuthContextType,
} from '../types';
import { logError } from '../lib/logError';

const HTTP_UNAUTHORIZED = 401;

function isUnauthorized(err: unknown): boolean {
  const status = (err as { response?: { status?: number } } | null)?.response?.status;
  return status === HTTP_UNAUTHORIZED;
}

function shouldSkipSessionProbe(hasCachedUser: boolean): boolean {
  return !hasCachedUser && PROBE_FREE_PATHS.includes(window.location.pathname);
}

/** localStorage keys holding the previous user's session data (FE-07). */
const PER_USER_STORAGE_KEYS = [
  'user',
  'running_time_entry',
  // Legacy unscoped scan activity; per-user keys
  // (scanner_last_activity_id:<id>) are intentionally kept.
  'scanner_last_activity_id',
];

/** Service-worker runtime caches holding authenticated API responses. */
const AUTHENTICATED_CACHE_PREFIX = 'api-';

/**
 * FE-07 / FE-11 — on a shared bench tablet the next user must not see the
 * previous user's timer, orders, prices or materials. Clears per-user
 * localStorage and the SW API caches (static assets stay cached).
 */
export function clearPerUserClientState(): void {
  for (const key of PER_USER_STORAGE_KEYS) {
    try {
      localStorage.removeItem(key);
    } catch (err) {
      console.error('Failed to clear local session key:', key, err);
    }
  }
  if (typeof caches === 'undefined') return;
  void caches
    .keys()
    .then((names) =>
      Promise.all(
        names
          .filter((name) => name.startsWith(AUTHENTICATED_CACHE_PREFIX))
          .map((name) => caches.delete(name)),
      ),
    )
    .catch((err: unknown) => {
      console.error('Failed to clear API caches on logout:', err);
    });
}

// Create the context
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Provider Props
interface AuthProviderProps {
  children: ReactNode;
}

/**
 * AuthProvider Component
 * Manages authentication state and provides auth methods to the app
 */
export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<UserType | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Check if user is authenticated
  const isAuthenticated = !!user;

  /**
   * Check whether the current user holds at least one of the given roles.
   * Accepts a single role string or an array of role strings.
   */
  const hasRole = (roles: UserRole | UserRole[]): boolean => {
    if (!user) return false;
    const userRoleUpper = user.role?.toUpperCase() as UserRole;
    const roleList = Array.isArray(roles) ? roles : [roles];
    return roleList.some(r => r.toUpperCase() === userRoleUpper);
  };

  const isAdmin = user?.role?.toUpperCase() === 'ADMIN';

  /**
   * Listen for session-expired events dispatched by the API client interceptor
   * when token refresh fails. This bridges the gap between the non-React
   * interceptor and React context state.
   */
  useEffect(() => {
    const handleSessionExpired = () => {
      clearPerUserClientState();
      setUser(null);
    };
    window.addEventListener('auth:session-expired', handleSessionExpired);
    return () => window.removeEventListener('auth:session-expired', handleSessionExpired);
  }, []);

  /**
   * Initialize auth state on mount
   * Check if token exists and fetch user data
   */
  useEffect(() => {
    const initializeAuth = async () => {
      // Restore cached user for instant render (will be validated below)
      const savedUser = localStorage.getItem('user');
      if (savedUser) {
        try {
          setUser(JSON.parse(savedUser));
        } catch {
          localStorage.removeItem('user');
        }
      }

      if (shouldSkipSessionProbe(savedUser !== null)) {
        setIsLoading(false);
        return;
      }

      // Validate the HttpOnly cookie by calling the server
      try {
        const currentUser = await authApi.getCurrentUser();
        setUser(currentUser);
        localStorage.setItem('user', JSON.stringify(currentUser));
      } catch (err) {
        // 401 = no (or expired) session: the expected answer, stay quiet.
        // Anything else (network, 5xx) must stay visible (LV-21).
        if (!isUnauthorized(err)) {
          logError('AuthContext.sessionProbe', err);
        }
        setUser(null);
        localStorage.removeItem('user');
      }

      setIsLoading(false);
    };

    initializeAuth();
  }, []);

  /**
   * Login user with credentials
   */
  const login = async (credentials: LoginCredentials): Promise<void> => {
    try {
      setIsLoading(true);
      // Login and get token
      await authApi.login(credentials);

      // Fetch user data
      const currentUser = await authApi.getCurrentUser();
      setUser(currentUser);

      // Save to localStorage
      localStorage.setItem('user', JSON.stringify(currentUser));
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Register new user
   */
  const register = async (userData: UserCreateInput): Promise<void> => {
    try {
      setIsLoading(true);
      // Register user
      await authApi.register(userData);

      // Auto-login after registration
      await login({
        email: userData.email,
        password: userData.password,
      });
    } catch (error) {
      console.error('Registration failed:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Logout user
   */
  const logout = (): void => {
    authApi.logout();
    clearPerUserClientState();
    setUser(null);
  };

  /**
   * Refresh user data from server
   */
  const refreshUser = async (): Promise<void> => {
    try {
      const currentUser = await authApi.getCurrentUser();
      setUser(currentUser);
      localStorage.setItem('user', JSON.stringify(currentUser));
    } catch (error) {
      console.error('Failed to refresh user:', error);
      throw error;
    }
  };

  const value: AuthContextType = {
    user,
    isAuthenticated,
    isLoading,
    login,
    register,
    logout,
    refreshUser,
    hasRole,
    isAdmin: isAdmin ?? false,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

/**
 * useAuth Hook
 * Custom hook to access auth context
 */
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

/**
 * useOptionalAuth — like useAuth but returns null outside an AuthProvider.
 * For components that are also rendered standalone (e.g. ScanOverlay in
 * tests) and only need the user id opportunistically.
 */
export const useOptionalAuth = (): AuthContextType | null => {
  return useContext(AuthContext) ?? null;
};
