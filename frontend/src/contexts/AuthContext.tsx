// Authentication Context - Global auth state management
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authApi } from '../api';
import {
  UserType,
  UserRole,
  LoginCredentials,
  UserCreateInput,
  AuthContextType,
} from '../types';

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
      setUser(null);
      localStorage.removeItem('user');
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

      // Always validate the HttpOnly cookie by calling the server
      try {
        const currentUser = await authApi.getCurrentUser();
        setUser(currentUser);
        localStorage.setItem('user', JSON.stringify(currentUser));
      } catch {
        // Cookie invalid or expired — clear state
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
