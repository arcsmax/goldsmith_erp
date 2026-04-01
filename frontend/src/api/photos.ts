// Photos API — order photo endpoints
import apiClient from './client';

export const photosApi = {
  getForOrder: (orderId: number) =>
    apiClient.get(`/orders/${orderId}/photos`),
};
