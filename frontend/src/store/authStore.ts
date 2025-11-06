/**
 * Authentication Store (Zustand)
 */
import { create } from 'zustand';
import { login as apiLogin, logout as apiLogout, User } from '@/lib/api/auth';
import { getErrorMessage } from '@/lib/api/client';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setUser: (user: User) => void;
  clearError: () => void;
  initializeAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });

    try {
      const response = await apiLogin(email, password);

      // Store token
      localStorage.setItem('access_token', response.access_token);

      // Create user object from email (backend doesn't return user info yet)
      const user: User = {
        id: 0, // Will be updated when we have /users/me endpoint
        email,
        first_name: '',
        last_name: '',
        role: 'goldsmith',
        is_active: true,
      };

      localStorage.setItem('user', JSON.stringify(user));

      set({
        user,
        token: response.access_token,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (error) {
      const errorMessage = getErrorMessage(error);
      set({
        user: null,
        token: null,
        isAuthenticated: false,
        isLoading: false,
        error: errorMessage,
      });
      throw error;
    }
  },

  logout: () => {
    apiLogout();
    set({
      user: null,
      token: null,
      isAuthenticated: false,
      error: null,
    });
  },

  setUser: (user: User) => {
    localStorage.setItem('user', JSON.stringify(user));
    set({ user });
  },

  clearError: () => {
    set({ error: null });
  },

  initializeAuth: () => {
    const token = localStorage.getItem('access_token');
    const userStr = localStorage.getItem('user');

    if (token && userStr) {
      try {
        const user = JSON.parse(userStr) as User;
        set({
          user,
          token,
          isAuthenticated: true,
        });
      } catch {
        // Invalid stored data, clear it
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
      }
    }
  },
}));
