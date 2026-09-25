// Standort dropdown (W8). Offers the active workshop locations the ADMIN
// configured under Systemübersicht > Standorte (query queryKeys.locations).
//
// - A deactivated or legacy free-text location that is already stored stays
//   visible as the selected option, so editing old history never loses it.
// - ADMIN sees an inline "Standort hinzufügen" quick-add; the new location
//   is selected right away. Other roles only pick from the list.
import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { activeLocationsQuery } from '../api/locationQueries';
import { createLocation, type WorkshopLocation } from '../api/locations';
import { queryKeys } from '../api/queryKeys';
import { useOptionalAuth } from '../contexts/AuthContext';
import { getErrorMessage } from '../lib/errors';
import { logError } from '../lib/logError';
import { Button, Field } from '../ui';
import '../styles/components/LocationPicker.css';

export interface LocationPickerProps {
  /** Selected location id (null = none or a legacy text value). */
  value: number | null;
  /** Stored name; shown when the id is not among the active locations. */
  currentName?: string | null;
  onChange: (location: WorkshopLocation | null) => void;
  id?: string;
  label?: string;
  help?: string;
  error?: string;
  disabled?: boolean;
}

const NONE = '';
const STORED = 'stored';

const storedLabel = (name: string | null | undefined, value: number | null): string => {
  const base = name?.trim() || (value !== null ? `Standort ${value}` : '');
  return value !== null ? `${base} (deaktiviert)` : `${base} (nicht in der Liste)`;
};

const QuickAdd: React.FC<{ onCreated: (location: WorkshopLocation) => void }> = ({
  onCreated,
}) => {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState('');
  const create = useMutation({
    mutationFn: (newName: string) => createLocation({ name: newName, kind: 'other' }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.locations.all });
      setName('');
      setIsOpen(false);
      onCreated(created);
    },
    onError: (err) => logError('LocationPicker.quickAdd', err),
  });

  if (!isOpen) {
    return (
      <Button variant="ghost" icon="plus" onClick={() => setIsOpen(true)}>
        Standort hinzufügen
      </Button>
    );
  }
  const trimmed = name.trim();
  return (
    <div className="location-picker__add">
      <Field
        label="Neuer Standort"
        name="new_location"
        error={create.isError ? getErrorMessage(create.error, 'Standort konnte nicht angelegt werden.') : undefined}
      >
        <input
          type="text"
          value={name}
          maxLength={50}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <div className="location-picker__add-actions">
        <Button
          variant="secondary"
          onClick={() => {
            setIsOpen(false);
            setName('');
          }}
        >
          Abbrechen
        </Button>
        <Button
          disabled={!trimmed}
          loading={create.isPending}
          onClick={() => create.mutate(trimmed)}
        >
          Standort speichern
        </Button>
      </div>
    </div>
  );
};

export const LocationPicker: React.FC<LocationPickerProps> = ({
  value,
  currentName,
  onChange,
  id = 'location_id',
  label = 'Standort',
  help,
  error,
  disabled = false,
}) => {
  // Optional: the picker also renders in forms tested without an AuthProvider.
  const isAdmin = useOptionalAuth()?.isAdmin ?? false;
  const locations = useQuery(activeLocationsQuery());
  const options = locations.data ?? [];
  const isKnown = value !== null && options.some((loc) => loc.id === value);
  const hasStored = !isKnown && (value !== null || Boolean(currentName?.trim()));
  const selected = isKnown ? String(value) : hasStored ? STORED : NONE;

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = e.target.value;
    if (next === STORED) return;
    onChange(next === NONE ? null : options.find((loc) => String(loc.id) === next) ?? null);
  };

  const loadError = locations.isError
    ? getErrorMessage(locations.error, 'Standorte konnten nicht geladen werden.')
    : undefined;

  return (
    <div className="location-picker">
      <Field label={label} name="location_id" help={help} error={error ?? loadError}>
        <select id={id} value={selected} onChange={handleChange} disabled={disabled}>
          <option value={NONE}>{locations.isPending ? 'Wird geladen…' : 'Kein Standort'}</option>
          {hasStored && <option value={STORED}>{storedLabel(currentName, value)}</option>}
          {options.map((loc) => (
            <option key={loc.id} value={loc.id}>
              {loc.name}
            </option>
          ))}
        </select>
      </Field>
      {isAdmin && !disabled && <QuickAdd onCreated={(created) => onChange(created)} />}
    </div>
  );
};

export default LocationPicker;
