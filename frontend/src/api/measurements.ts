// Measurements API Service — Maßbibliothek für Kunden
import apiClient from './client';

export const measurementsApi = {
  getForCustomer: (customerId: number) =>
    apiClient.get(`/customers/${customerId}/measurements`),

  add: (customerId: number, data: any) =>
    apiClient.post(`/customers/${customerId}/measurements`, data),

  getRingSize: (customerId: number, hand: string, finger: string) =>
    apiClient.get(`/customers/${customerId}/ring-size`, {
      params: { hand, finger },
    }),
};
