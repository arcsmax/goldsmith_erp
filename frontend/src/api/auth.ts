// Authentication API Service
import apiClient from './client';
import { AuthResponse, LoginCredentials, UserType } from '../types';

export const authApi = {
  /**
   * Login user and get access token
   */
  login: async (credentials: LoginCredentials): Promise<AuthResponse> => {
    // FastAPI OAuth2PasswordRequestForm expects form data
    const formData = new URLSearchParams();
    formData.append('username', credentials.email);
    formData.append('password', credentials.password);

    const response = await apiClient.post<AuthResponse>('/login/access-token', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    return response.data;
  },

  /**
   * Register new user (public endpoint)
   */
  register: async (userData: {
    email: string;
    password: string;
    first_name?: string;
    last_name?: string;
  }): Promise<UserType> => {
    const response = await apiClient.post<UserType>('/users/register', userData);
    return response.data;
  },

  /**
   * Get current user profile
   */
  getCurrentUser: async (): Promise<UserType> => {
    const response = await apiClient.get<UserType>('/users/me');
    return response.data;
  },

  /**
   * Logout user — clear HttpOnly cookie via server + local user cache
   */
  logout: () => {
    apiClient.post('/logout').catch(() => {});
    localStorage.removeItem('user');
  },
};
