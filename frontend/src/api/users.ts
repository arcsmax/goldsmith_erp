// Users API Service (Admin)
import apiClient from './client';
import { UserType, UserCreateInput, UserUpdateInput } from '../types';

export const usersApi = {
  /**
   * Get all users (Admin only)
   */
  getAll: async (skip: number = 0, limit: number = 100): Promise<UserType[]> => {
    const response = await apiClient.get<UserType[]>('/users/', {
      params: { skip, limit },
    });
    return response.data;
  },

  /**
   * Get single user by ID (Admin only)
   */
  getById: async (id: number): Promise<UserType> => {
    const response = await apiClient.get<UserType>(`/users/${id}`);
    return response.data;
  },

  /**
   * Create new user (Admin only)
   */
  create: async (user: UserCreateInput): Promise<UserType> => {
    const response = await apiClient.post<UserType>('/users/', user);
    return response.data;
  },

  /**
   * Update user (Admin only)
   */
  update: async (id: number, user: UserUpdateInput): Promise<UserType> => {
    const response = await apiClient.put<UserType>(`/users/${id}`, user);
    return response.data;
  },

  /**
   * Update current user profile
   */
  updateMe: async (user: UserUpdateInput): Promise<UserType> => {
    const response = await apiClient.put<UserType>('/users/me', user);
    return response.data;
  },

  /**
   * Deactivate user (Admin only)
   */
  deactivate: async (id: number): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.delete<{ success: boolean; message: string }>(
      `/users/${id}`
    );
    return response.data;
  },

  /**
   * Activate user (Admin only)
   */
  activate: async (id: number): Promise<UserType> => {
    const response = await apiClient.post<UserType>(`/users/${id}/activate`);
    return response.data;
  },
};
