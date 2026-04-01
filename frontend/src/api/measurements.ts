// Measurements API Service — Maßbibliothek für Kunden
import apiClient from './client';

export const measurementsApi = {
  getForCustomer: (customerId: number) =>
    apiClient.get(`/customers/${customerId}/measurements`),

  add: (customerId: number, data: any) =>
    apiClient.post(`/customers/${customerId}/measurements`, data),

  update: (measurementId: number, data: any) =>
    apiClient.put(`/measurements/${measurementId}`, data),

  remove: (measurementId: number) =>
    apiClient.delete(`/measurements/${measurementId}`),

  getRingSize: (customerId: number, hand: string, finger: string) =>
    apiClient.get(`/customers/${customerId}/ring-size`, {
      params: { hand, finger },
    }),
};
