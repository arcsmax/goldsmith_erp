// IntakeCustomerPicker — find the customer or quick-create a walk-in
// (W2-12, FE-17). Quick-create asks for name and a phone number only: at the
// counter the phone is the one contact a walk-in reliably leaves, and the
// backend requires at least one contact channel (W2-10).
import React, { useState } from 'react';
import axios from 'axios';
import { customersApi } from '../../api/customers';
import type { CustomerListItem } from '../../types';
import { logError } from '../../lib/logError';
import { CustomerTypeahead } from '../consultation/CustomerTypeahead';

export interface PickedCustomer {
  id: number;
  first_name: string;
  last_name: string;
  phone?: string | null;
}

interface IntakeCustomerPickerProps {
  customer: PickedCustomer | null;
  onChange: (customer: PickedCustomer | null) => void;
  error?: string;
  onSearchError: () => void;
}

const QUICK_MESSAGES = {
  nameMissing: 'Name fehlt. Bitte Vor- und Nachname eingeben.',
  phoneMissing: 'Telefon fehlt. Bitte eine Rückrufnummer eingeben.',
  failed: 'Kunde konnte nicht angelegt werden. Bitte erneut versuchen.',
} as const;

function apiDetail(err: unknown): string | undefined {
  const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
  return typeof detail === 'string' ? detail : undefined;
}

const QuickCreate: React.FC<{ onCreated: (c: PickedCustomer) => void; onCancel: () => void }> = ({
  onCreated,
  onCancel,
}) => {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const handleCreate = async () => {
    if (!firstName.trim() || !lastName.trim()) return setError(QUICK_MESSAGES.nameMissing);
    if (!phone.trim()) return setError(QUICK_MESSAGES.phoneMissing);
    setError(null);
    setIsSaving(true);
    try {
      const created = await customersApi.create({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone: phone.trim(),
      });
      onCreated(created);
    } catch (err) {
      logError('IntakeCustomerPicker.create', err);
      setError(apiDetail(err) ?? QUICK_MESSAGES.failed);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="intake-quick-create">
      <div className="intake-field-row">
        <label className="intake-field">
          <span>Vorname</span>
          <input value={firstName} onChange={(e) => setFirstName(e.target.value)} autoComplete="off" />
        </label>
        <label className="intake-field">
          <span>Nachname</span>
          <input value={lastName} onChange={(e) => setLastName(e.target.value)} autoComplete="off" />
        </label>
        <label className="intake-field">
          <span>Telefon</span>
          <input
            type="tel"
            inputMode="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            autoComplete="off"
          />
        </label>
      </div>
      {error && (
        <p className="intake-error" role="alert">
          {error}
        </p>
      )}
      <div className="intake-actions">
        <button type="button" className="btn-secondary" onClick={onCancel} disabled={isSaving}>
          Abbrechen
        </button>
        <button type="button" className="btn-primary" onClick={handleCreate} disabled={isSaving}>
          {isSaving ? 'Wird angelegt…' : 'Kunde anlegen'}
        </button>
      </div>
    </div>
  );
};

export const IntakeCustomerPicker: React.FC<IntakeCustomerPickerProps> = ({
  customer,
  onChange,
  error,
  onSearchError,
}) => {
  const [isCreating, setIsCreating] = useState(false);

  if (customer) {
    return (
      <div className="intake-customer-card">
        <p className="intake-customer-card__name">
          {customer.first_name} {customer.last_name}
        </p>
        {customer.phone && <p className="intake-customer-card__meta">{customer.phone}</p>}
        <button type="button" className="btn-secondary" onClick={() => onChange(null)}>
          Andere Kundin oder anderen Kunden wählen
        </button>
      </div>
    );
  }

  if (isCreating) {
    return (
      <QuickCreate
        onCreated={(created) => {
          setIsCreating(false);
          onChange(created);
        }}
        onCancel={() => setIsCreating(false)}
      />
    );
  }

  return (
    <div className="intake-customer-search">
      <label className="intake-field" htmlFor="intake-customer-search">
        <span>Kundin oder Kunde suchen</span>
      </label>
      <div className="intake-customer-search__row">
        <CustomerTypeahead
          inputId="intake-customer-search"
          onSelect={(c: CustomerListItem) => onChange(c)}
          onError={onSearchError}
        />
        <button type="button" className="btn-secondary" onClick={() => setIsCreating(true)}>
          Neuer Kunde
        </button>
      </div>
      {error && (
        <p className="intake-error" role="alert" id="intake-customer-error">
          {error}
        </p>
      )}
    </div>
  );
};

export default IntakeCustomerPicker;
