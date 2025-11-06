/**
 * Customer API Client
 * GDPR-compliant customer management API
 */
import { apiClient, getErrorMessage } from './client';
import type {
  Customer,
  CustomerCreate,
  CustomerUpdate,
  CustomerList,
  ConsentUpdate,
  ConsentStatus,
  CustomerStatistics,
  AuditLogEntry,
} from '../../types';

/**
 * Get list of customers with optional filters
 */
export const getCustomers = async (params?: {
  skip?: number;
  limit?: number;
  is_active?: boolean;
  include_deleted?: boolean;
  order_by?: string;
}): Promise<CustomerList> => {
  const response = await apiClient.get<CustomerList>('/customers', { params });
  return response.data;
};

/**
 * Search customers by query
 */
export const searchCustomers = async (params: {
  query: string;
  skip?: number;
  limit?: number;
  include_deleted?: boolean;
}): Promise<Customer[]> => {
  const response = await apiClient.get<Customer[]>('/customers/search', { params });
  return response.data;
};

/**
 * Get customer by ID
 */
export const getCustomer = async (id: number): Promise<Customer> => {
  const response = await apiClient.get<Customer>(`/customers/${id}`);
  return response.data;
};

/**
 * Get customer by email
 */
export const getCustomerByEmail = async (email: string): Promise<Customer> => {
  const response = await apiClient.get<Customer>(`/customers/by-email/${email}`);
  return response.data;
};

/**
 * Get customer by customer number
 */
export const getCustomerByNumber = async (customerNumber: string): Promise<Customer> => {
  const response = await apiClient.get<Customer>(`/customers/by-number/${customerNumber}`);
  return response.data;
};

/**
 * Create new customer
 */
export const createCustomer = async (data: CustomerCreate): Promise<Customer> => {
  const response = await apiClient.post<Customer>('/customers', data);
  return response.data;
};

/**
 * Update customer
 */
export const updateCustomer = async (id: number, data: CustomerUpdate): Promise<Customer> => {
  const response = await apiClient.put<Customer>(`/customers/${id}`, data);
  return response.data;
};

/**
 * Delete customer (soft or hard delete)
 */
export const deleteCustomer = async (
  id: number,
  hardDelete: boolean = false,
  deletionReason?: string
): Promise<void> => {
  await apiClient.delete(`/customers/${id}`, {
    params: {
      hard_delete: hardDelete,
      deletion_reason: deletionReason,
    },
  });
};

/**
 * Get customer statistics
 */
export const getCustomerStatistics = async (): Promise<CustomerStatistics> => {
  const response = await apiClient.get<CustomerStatistics>('/customers/statistics');
  return response.data;
};

// ═══════════════════════════════════════════════════════════════════════════
// GDPR Consent Management
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Update customer consent
 */
export const updateConsent = async (
  customerId: number,
  data: ConsentUpdate
): Promise<Customer> => {
  const response = await apiClient.post<Customer>(`/customers/${customerId}/consent`, data);
  return response.data;
};

/**
 * Revoke all customer consents
 */
export const revokeAllConsents = async (customerId: number): Promise<Customer> => {
  const response = await apiClient.post<Customer>(`/customers/${customerId}/consent/revoke-all`);
  return response.data;
};

/**
 * Get customer consent status
 */
export const getConsentStatus = async (customerId: number): Promise<ConsentStatus> => {
  const response = await apiClient.get<ConsentStatus>(`/customers/${customerId}/consent`);
  return response.data;
};

// ═══════════════════════════════════════════════════════════════════════════
// GDPR Data Subject Rights
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Export customer data (GDPR Article 15 - Right of Access)
 */
export const exportCustomerData = async (customerId: number): Promise<any> => {
  const response = await apiClient.get(`/customers/${customerId}/export`);
  return response.data;
};

/**
 * Download customer data as JSON file
 */
export const downloadCustomerData = async (customerId: number, customerName: string): Promise<void> => {
  try {
    const data = await exportCustomerData(customerId);

    // Create blob and download
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `customer-data-${customerName}-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch (error) {
    throw new Error(`Failed to download customer data: ${getErrorMessage(error)}`);
  }
};

/**
 * Anonymize customer data
 */
export const anonymizeCustomer = async (
  customerId: number,
  reason: string
): Promise<Customer> => {
  const response = await apiClient.post<Customer>(`/customers/${customerId}/anonymize`, null, {
    params: { reason },
  });
  return response.data;
};

// ═══════════════════════════════════════════════════════════════════════════
// Audit Trail
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Get customer audit logs
 */
export const getCustomerAuditLogs = async (
  customerId: number,
  params?: {
    skip?: number;
    limit?: number;
  }
): Promise<{ items: AuditLogEntry[]; total: number }> => {
  const response = await apiClient.get(`/customers/${customerId}/audit-logs`, { params });
  return response.data;
};

// ═══════════════════════════════════════════════════════════════════════════
// Helper Functions
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Format customer name
 */
export const formatCustomerName = (customer: Customer): string => {
  return `${customer.first_name} ${customer.last_name}`;
};

/**
 * Format customer address
 */
export const formatCustomerAddress = (customer: Customer): string | null => {
  if (!customer.address_line1) return null;

  const parts = [
    customer.address_line1,
    customer.address_line2,
    [customer.postal_code, customer.city].filter(Boolean).join(' '),
    customer.country,
  ].filter(Boolean);

  return parts.join(', ');
};

/**
 * Get customer initials
 */
export const getCustomerInitials = (customer: Customer): string => {
  return `${customer.first_name[0]}${customer.last_name[0]}`.toUpperCase();
};

/**
 * Check if customer has active consent
 */
export const hasMarketingConsent = (customer: Customer): boolean => {
  return customer.consent_marketing;
};

/**
 * Check if customer retention is expiring soon
 */
export const isRetentionExpiringSoon = (customer: Customer, daysThreshold: number = 30): boolean => {
  if (!customer.retention_deadline) return false;

  const deadline = new Date(customer.retention_deadline);
  const now = new Date();
  const daysUntilExpiry = Math.floor((deadline.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));

  return daysUntilExpiry <= daysThreshold && daysUntilExpiry >= 0;
};

/**
 * Check if customer retention has expired
 */
export const isRetentionExpired = (customer: Customer): boolean => {
  if (!customer.retention_deadline) return false;

  const deadline = new Date(customer.retention_deadline);
  const now = new Date();

  return deadline < now;
};

/**
 * Get legal basis label
 */
export const getLegalBasisLabel = (legalBasis: string): string => {
  const labels: Record<string, string> = {
    contract: 'Vertrag',
    consent: 'Einwilligung',
    legitimate_interest: 'Berechtigtes Interesse',
    legal_obligation: 'Rechtliche Verpflichtung',
  };
  return labels[legalBasis] || legalBasis;
};

/**
 * Get legal basis description
 */
export const getLegalBasisDescription = (legalBasis: string): string => {
  const descriptions: Record<string, string> = {
    contract: 'Datenverarbeitung zur Vertragserfüllung',
    consent: 'Datenverarbeitung mit ausdrücklicher Einwilligung',
    legitimate_interest: 'Datenverarbeitung auf Basis berechtigter Interessen',
    legal_obligation: 'Datenverarbeitung aufgrund gesetzlicher Verpflichtung',
  };
  return descriptions[legalBasis] || legalBasis;
};
