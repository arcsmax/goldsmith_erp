// IntakeCustomerPicker — find the customer or quick-create a walk-in
// (W2-12, FE-17). Quick-create asks for name and a phone number only: at the
// counter the phone is the one contact a walk-in reliably leaves, and the
// backend requires at least one contact channel (W2-10).
import React, { useState } from 'react';
import axios from 'axios';
import { customersApi } from '../../api/customers';
import type { CustomerListItem } from '../../types';
import { logError } from '../../lib/logError';
import { Button, Field, Icon } from '../../ui';
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
        <Field label="Vorname" name="intake-first-name">
          <input value={firstName} onChange={(e) => setFirstName(e.target.value)} autoComplete="off" />
        </Field>
        <Field label="Nachname" name="intake-last-name">
          <input value={lastName} onChange={(e) => setLastName(e.target.value)} autoComplete="off" />
        </Field>
        <Field label="Telefon" name="intake-phone" inputMode="tel">
          <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="off" />
        </Field>
      </div>
      {error && (
        <p className="ui-field__error" role="alert">
          <Icon name="alert-triangle" />
          <span>{error}</span>
        </p>
      )}
      <div className="intake-actions">
        <Button variant="secondary" onClick={onCancel} disabled={isSaving}>
          Abbrechen
        </Button>
        <Button onClick={handleCreate} loading={isSaving}>
          Kunde anlegen
        </Button>
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
        <Button variant="secondary" onClick={() => onChange(null)}>
          Andere Kundin oder anderen Kunden wählen
        </Button>
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
      <label className="ui-field__label" htmlFor="intake-customer-search">
        Kundin oder Kunde suchen
      </label>
      <div className="intake-customer-search__row">
        <CustomerTypeahead
          inputId="intake-customer-search"
          onSelect={(c: CustomerListItem) => onChange(c)}
          onError={onSearchError}
        />
        <Button variant="secondary" icon="plus" onClick={() => setIsCreating(true)}>
          Neuer Kunde
        </Button>
      </div>
      {error && (
        <p className="ui-field__error" role="alert" id="intake-customer-error">
          <Icon name="alert-triangle" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
};

export default IntakeCustomerPicker;
