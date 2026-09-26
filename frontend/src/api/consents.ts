// Consents API Service — GDPR-02 / GDPR-11 per-customer consent records.
//
// Mirrors the backend contract in
// src/goldsmith_erp/models/consent.py and
// src/goldsmith_erp/api/routers/customers.py (consent endpoints section).
// Health data (allergies) is the first consumer: allergies may only be
// stored while an active HEALTH_DATA consent exists for the customer.
import apiClient from './client';

export type ConsentPurpose = 'health_data' | 'photo_use' | 'email_contact' | 'marketing';

export type ConsentMethod = 'in_person' | 'written' | 'portal';

/** All purposes the backend's ConsentPurpose enum supports. */
export const CONSENT_PURPOSES: ConsentPurpose[] = [
  'health_data',
  'photo_use',
  'email_contact',
  'marketing',
];

export const CONSENT_PURPOSE_LABELS: Record<ConsentPurpose, string> = {
  health_data: 'Gesundheitsdaten',
  photo_use: 'Fotonutzung',
  email_contact: 'E-Mail-Kontakt',
  marketing: 'Werbung',
};

export const CONSENT_METHOD_LABELS: Record<ConsentMethod, string> = {
  in_person: 'Vor Ort',
  written: 'Schriftlich',
  portal: 'Online-Portal',
};

export interface ConsentRecord {
  id: number;
  customer_id: number;
  purpose: ConsentPurpose;
  method: ConsentMethod;
  wording_version?: string | null;
  granted_at: string;
  revoked_at?: string | null;
  recorded_by_user_id?: number | null;
  revoked_by_user_id?: number | null;
  note?: string | null;
}

export interface ConsentGrantInput {
  purpose: ConsentPurpose;
  method: ConsentMethod;
  wording_version?: string;
  note?: string;
}

export const consentsApi = {
  /** List all consent records (active and revoked) of a customer. */
  list: async (customerId: number): Promise<ConsentRecord[]> => {
    const response = await apiClient.get<ConsentRecord[]>(
      `/customers/${customerId}/consents`
    );
    return response.data;
  },

  /** Record a consent. Idempotent while one is already active for the purpose. */
  grant: async (customerId: number, data: ConsentGrantInput): Promise<ConsentRecord> => {
    const response = await apiClient.post<ConsentRecord>(
      `/customers/${customerId}/consents`,
      data
    );
    return response.data;
  },

  /** Art. 21 objection "Keine E-Mail-Updates" (W6). */
  getEmailOptOut: async (customerId: number): Promise<boolean> => {
    const response = await apiClient.get<{ email_opt_out: boolean }>(
      `/customers/${customerId}/email-opt-out`
    );
    return response.data.email_opt_out;
  },

  /** Record (true) or lift (false) the "Keine E-Mail-Updates" objection. */
  setEmailOptOut: async (customerId: number, optedOut: boolean): Promise<boolean> => {
    const response = await apiClient.put<{ email_opt_out: boolean }>(
      `/customers/${customerId}/email-opt-out`,
      { email_opt_out: optedOut }
    );
    return response.data.email_opt_out;
  },

  /** Withdraw the active consent for `purpose`. 404 if none is active. */
  revoke: async (customerId: number, purpose: ConsentPurpose): Promise<ConsentRecord> => {
    const response = await apiClient.delete<ConsentRecord>(
      `/customers/${customerId}/consents/${purpose}`
    );
    return response.data;
  },
};

/** Find the currently active (not revoked) record for `purpose`, if any. */
export function findActiveConsent(
  consents: ConsentRecord[],
  purpose: ConsentPurpose
): ConsentRecord | null {
  return consents.find((c) => c.purpose === purpose && !c.revoked_at) ?? null;
}

/**
 * Extract the FastAPI `detail` message from an error response (e.g. the
 * German 422 "Einwilligung ..." message). Never assume the shape — external
 * error payloads are untrusted input.
 */
export function extractErrorDetail(err: unknown): string | undefined {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const detail = (err as any)?.response?.data?.detail;
  return typeof detail === 'string' && detail ? detail : undefined;
}
