// Standorte (W8): the workshop locations behind every "Standort" dropdown
// (timer, time-entry form, order). ADMIN adds, renames, reorders and
// deactivates them here. Deactivating never deletes: old time entries and
// orders keep their location, the dropdown just stops offering it.
import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { allLocationsQuery } from '../../api/locationQueries';
import {
  createLocation,
  deactivateLocation,
  LOCATION_KIND_LABELS,
  LOCATION_KINDS,
  updateLocation,
  type LocationKind,
  type LocationUpdateInput,
  type WorkshopLocation,
} from '../../api/locations';
import { queryKeys } from '../../api/queryKeys';
import { useConfirm } from '../../contexts/ToastContext';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import {
  Button,
  Card,
  DataTable,
  Field,
  IconButton,
  usePromptDialog,
  type Column,
  type PageStateValue,
} from '../../ui';

const SORT_STEP = 10;
const NAME_MAX = 50;
const LOAD_ERROR = 'Standorte konnten nicht geladen werden.';
const SAVE_ERROR = 'Standort konnte nicht gespeichert werden.';

type Patch = { id: number; data: LocationUpdateInput };

/** New sort orders after moving row `index` by `delta` (only changed rows). */
export function reorderPatches(rows: WorkshopLocation[], index: number, delta: -1 | 1): Patch[] {
  const target = index + delta;
  if (target < 0 || target >= rows.length) return [];
  const next = [...rows];
  [next[index], next[target]] = [next[target], next[index]];
  return next
    .map((row, i) => ({ id: row.id, sort: (i + 1) * SORT_STEP, current: row.sort_order }))
    .filter((r) => r.sort !== r.current)
    .map((r) => ({ id: r.id, data: { sort_order: r.sort } }));
}

const AddLocationForm: React.FC<{ onSaved: () => void }> = ({ onSaved }) => {
  const [name, setName] = useState('');
  const [kind, setKind] = useState<LocationKind>('bench');
  const create = useMutation({
    mutationFn: () => createLocation({ name: name.trim(), kind }),
    onSuccess: () => {
      setName('');
      onSaved();
    },
    onError: (err) => logError('LocationsPanel.create', err),
  });

  return (
    <form
      className="admin-locations__add"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) create.mutate();
      }}
    >
      <Field
        label="Name"
        name="location_name"
        required
        error={create.isError ? getErrorMessage(create.error, SAVE_ERROR) : undefined}
      >
        <input
          id="location_name"
          type="text"
          value={name}
          maxLength={NAME_MAX}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <Field label="Art" name="location_kind">
        <select
          id="location_kind"
          value={kind}
          onChange={(e) => setKind(e.target.value as LocationKind)}
        >
          {LOCATION_KINDS.map((k) => (
            <option key={k} value={k}>
              {LOCATION_KIND_LABELS[k]}
            </option>
          ))}
        </select>
      </Field>
      <Button type="submit" icon="plus" disabled={!name.trim()} loading={create.isPending}>
        Standort hinzufügen
      </Button>
    </form>
  );
};

export const LocationsPanel: React.FC = () => {
  const queryClient = useQueryClient();
  const { showConfirm } = useConfirm();
  const { prompt, dialog } = usePromptDialog();
  const locations = useQuery(allLocationsQuery());
  const rows = locations.data ?? [];

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.locations.all });

  const patch = useMutation({
    mutationFn: async (patches: Patch[]) => {
      for (const p of patches) await updateLocation(p.id, p.data);
    },
    onSettled: () => void refresh(),
    onError: (err) => logError('LocationsPanel.update', err),
  });
  const deactivate = useMutation({
    mutationFn: (id: number) => deactivateLocation(id),
    onSettled: () => void refresh(),
    onError: (err) => logError('LocationsPanel.deactivate', err),
  });

  const rename = async (loc: WorkshopLocation) => {
    const name = await prompt({
      title: 'Standort umbenennen',
      label: 'Neuer Name',
      defaultValue: loc.name,
      confirmLabel: 'Namen speichern',
    });
    if (name && name !== loc.name) patch.mutate([{ id: loc.id, data: { name } }]);
  };

  const askDeactivate = async (loc: WorkshopLocation) => {
    const ok = await showConfirm({
      title: 'Standort deaktivieren?',
      message: `„${loc.name}“ wird nicht mehr zur Auswahl angeboten. Bestehende Zeiteinträge und Aufträge behalten den Standort.`,
      confirmLabel: 'Standort deaktivieren',
      variant: 'danger',
    });
    if (ok) deactivate.mutate(loc.id);
  };

  const columns: Column<WorkshopLocation>[] = [
    { key: 'name', header: 'Name', render: (l) => l.name },
    { key: 'kind', header: 'Art', render: (l) => LOCATION_KIND_LABELS[l.kind] },
    { key: 'status', header: 'Status', render: (l) => (l.is_active ? 'Aktiv' : 'Deaktiviert') },
    {
      key: 'order',
      header: 'Reihenfolge',
      render: (l) => {
        const index = rows.findIndex((r) => r.id === l.id);
        return (
          <span className="admin-locations__order">
            <IconButton
              icon="chevron-up"
              label={`${l.name} nach oben`}
              disabled={index === 0 || patch.isPending}
              onClick={() => patch.mutate(reorderPatches(rows, index, -1))}
            />
            <IconButton
              icon="chevron-down"
              label={`${l.name} nach unten`}
              disabled={index === rows.length - 1 || patch.isPending}
              onClick={() => patch.mutate(reorderPatches(rows, index, 1))}
            />
          </span>
        );
      },
    },
    {
      key: 'actions',
      header: 'Aktionen',
      align: 'end',
      render: (l) => (
        <span className="admin-locations__actions">
          <Button variant="secondary" icon="pencil" onClick={() => void rename(l)}>
            Standort umbenennen
          </Button>
          {l.is_active ? (
            <Button variant="ghost" icon="archive" onClick={() => void askDeactivate(l)}>
              Standort deaktivieren
            </Button>
          ) : (
            <Button
              variant="ghost"
              icon="refresh"
              onClick={() => patch.mutate([{ id: l.id, data: { is_active: true } }])}
            >
              Standort aktivieren
            </Button>
          )}
        </span>
      ),
    },
  ];

  const state: PageStateValue = locations.isError
    ? {
        status: 'error',
        error: getErrorMessage(locations.error, LOAD_ERROR),
        retry: () => void locations.refetch(),
      }
    : !locations.data
      ? { status: 'loading' }
      : { status: rows.length ? 'ready' : 'empty' };

  const mutationError = patch.error ?? deactivate.error;

  return (
    <Card title="Standorte" className="admin-panel">
      <p className="admin-panel__intro">
        Werkbänke, Tresor und andere Orte für das Feld „Standort“ bei Timer, Zeiteinträgen und
        Aufträgen. Deaktivierte Standorte bleiben im Verlauf erhalten.
      </p>
      {mutationError && (
        <p className="admin-notice admin-notice--danger" role="alert">
          {getErrorMessage(mutationError, SAVE_ERROR)}
        </p>
      )}
      <AddLocationForm onSaved={() => void refresh()} />
      <DataTable
        caption="Standorte"
        rows={rows}
        columns={columns}
        getRowKey={(l) => l.id}
        state={state}
        empty={{
          title: 'Noch keine Standorte',
          body: 'Den ersten Standort hinzufügen, z. B. „Werkbank 1“.',
          headingLevel: 3,
          action: (
            <Button
              variant="secondary"
              icon="plus"
              onClick={() => document.getElementById('location_name')?.focus()}
            >
              Ersten Standort anlegen
            </Button>
          ),
        }}
      />
      {dialog}
    </Card>
  );
};

export default LocationsPanel;
