// Customer typeahead for the Werkstatt board: type two letters, pick a
// customer from the suggestions (buttons, so Tab/Enter work), clear with
// "Kunde entfernen". The board filters by the picked customer's id.
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { customersApi } from '../../api/customers';
import { queryKeys } from '../../api/queryKeys';
import { getErrorMessage } from '../../lib/errors';
import { useDebouncedValue } from '../../lib/useDebouncedValue';
import type { CustomerListItem } from '../../types';
import { Button } from '../../ui/Button';
import { Field } from '../../ui/Field';

const MIN_QUERY_LENGTH = 2;
const MAX_QUERY_LENGTH = 100;
const MAX_SUGGESTIONS = 8;

export interface PickedCustomer {
  id: number;
  name: string;
}

export interface CustomerFilterProps {
  value: PickedCustomer | null;
  onChange: (customer: PickedCustomer | null) => void;
}

export function customerName(customer: CustomerListItem): string {
  const person = `${customer.first_name} ${customer.last_name}`.trim();
  return customer.company_name ? `${customer.company_name} (${person})` : person;
}

export function CustomerFilter({ value, onChange }: CustomerFilterProps) {
  const [input, setInput] = useState('');
  const query = useDebouncedValue(input.trim().slice(0, MAX_QUERY_LENGTH));
  const isSearching = value === null && query.length >= MIN_QUERY_LENGTH;
  const suggestions = useQuery({
    queryKey: queryKeys.customers.search(query, MAX_SUGGESTIONS),
    queryFn: () => customersApi.search(query, MAX_SUGGESTIONS),
    enabled: isSearching,
  });

  if (value) {
    return (
      <div className="workshop-filter__picked">
        <span>
          Kunde: <strong>{value.name}</strong>
        </span>
        <Button variant="ghost" icon="close" onClick={() => onChange(null)}>
          Kunde entfernen
        </Button>
      </div>
    );
  }

  const pick = (customer: CustomerListItem) => {
    setInput('');
    onChange({ id: customer.id, name: customerName(customer) });
  };

  return (
    <div className="workshop-filter__customer">
      <Field label="Kunde" name="workshop-customer" inputMode="search" help="Mindestens zwei Buchstaben">
        <input
          type="search"
          placeholder="Name oder Firma …"
          maxLength={MAX_QUERY_LENGTH}
          autoComplete="off"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
      </Field>
      {isSearching && suggestions.isError && (
        <p className="workshop-filter__note" role="alert">
          {getErrorMessage(suggestions.error, 'Kunden konnten nicht gesucht werden.')}
        </p>
      )}
      {isSearching && suggestions.data && (
        <ul className="workshop-filter__suggestions" aria-label="Vorschläge">
          {suggestions.data.length === 0 && <li className="workshop-filter__note">Kein Kunde gefunden</li>}
          {suggestions.data.map((customer) => (
            <li key={customer.id}>
              <Button variant="ghost" block onClick={() => pick(customer)}>
                {customerName(customer)}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
