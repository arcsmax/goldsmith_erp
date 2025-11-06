export interface MaterialType {
  id: number;
  name: string;
  unit_price: number;
}

export interface OrderType {
  id: number;
  title: string;
  description: string;
  price: number | null;
  status: string;
  customer_id: number;
  created_at: string;
  updated_at: string;
  materials?: MaterialType[];
}

export interface UserType {
  id: number;
  email: string;
  first_name?: string;
  last_name?: string;
  is_active: boolean;
  created_at: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// Customer Types (GDPR-Compliant)
// ═══════════════════════════════════════════════════════════════════════════

export interface Customer {
  id: number;
  customer_number: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  address_line1?: string;
  address_line2?: string;
  postal_code?: string;
  city?: string;
  country: string;
  is_active: boolean;

  // GDPR Compliance
  legal_basis: 'contract' | 'consent' | 'legitimate_interest' | 'legal_obligation';
  consent_marketing: boolean;
  consent_date?: string;
  consent_version?: string;
  data_retention_category: string;
  last_order_date?: string;
  retention_deadline?: string;

  // Privacy Preferences
  data_processing_consent: boolean;
  email_communication_consent: boolean;
  phone_communication_consent: boolean;
  sms_communication_consent: boolean;

  // Soft Delete
  is_deleted: boolean;
  deleted_at?: string;
  deletion_reason?: string;

  // Audit
  created_at: string;
  created_by: number;
  updated_at?: string;
  updated_by?: number;

  // Additional
  notes?: string;
  tags?: string[];
}

export interface CustomerCreate {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  address_line1?: string;
  address_line2?: string;
  postal_code?: string;
  city?: string;
  country?: string;
  legal_basis: 'contract' | 'consent' | 'legitimate_interest';
  consent_marketing?: boolean;
  consent_version?: string;
  consent_ip_address?: string;
  consent_method?: string;
  data_processing_consent?: boolean;
  email_communication_consent?: boolean;
  phone_communication_consent?: boolean;
  sms_communication_consent?: boolean;
  notes?: string;
  tags?: string[];
}

export interface CustomerUpdate {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  address_line1?: string;
  address_line2?: string;
  postal_code?: string;
  city?: string;
  country?: string;
  is_active?: boolean;
  legal_basis?: 'contract' | 'consent' | 'legitimate_interest';
  notes?: string;
  tags?: string[];
}

export interface CustomerList {
  items: Customer[];
  total: number;
  skip: number;
  limit: number;
  has_more: boolean;
}

export interface ConsentUpdate {
  consent_type: 'marketing' | 'email' | 'phone' | 'sms' | 'data_processing';
  consent_value: boolean;
  consent_version?: string;
  ip_address?: string;
  consent_method?: string;
}

export interface ConsentStatus {
  marketing: boolean;
  email_communication: boolean;
  phone_communication: boolean;
  sms_communication: boolean;
  data_processing: boolean;
  consent_date?: string;
  consent_version?: string;
  consent_method?: string;
}

export interface CustomerStatistics {
  total_active_customers: number;
  total_customers: number;
  total_deleted_customers: number;
  marketing_consent_customers: number;
}

export interface AuditLogEntry {
  id: number;
  customer_id: number;
  action: string;
  entity: string;
  entity_id?: number;
  field_name?: string;
  old_value?: string;
  new_value?: string;
  user_id: number;
  user_email?: string;
  timestamp: string;
  ip_address?: string;
  legal_basis?: string;
  purpose?: string;
}