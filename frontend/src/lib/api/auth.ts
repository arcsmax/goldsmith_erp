/**
 * Authentication API
 */
import { apiClient } from './client';

export interface LoginRequest {
  username: string; // Email in OAuth2 password flow
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  is_active: boolean;
}

/**
 * Login with email and password
 */
export const login = async (
  email: string,
  password: string
): Promise<LoginResponse> => {
  // OAuth2 password flow expects form data
  const formData = new FormData();
  formData.append('username', email);
  formData.append('password', password);

  const response = await apiClient.post<LoginResponse>(
    '/login/access-token',
    formData,
    {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    }
  );

  return response.data;
};

/**
 * Get current user (mock - will be replaced with actual endpoint)
 */
export const getCurrentUser = async (): Promise<User> => {
  // TODO: Implement actual endpoint when backend has /users/me
  const response = await apiClient.get<User>('/users/me');
  return response.data;
};

/**
 * Logout (client-side only for now)
 */
export const logout = (): void => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('user');
};
