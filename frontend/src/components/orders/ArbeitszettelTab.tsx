// ArbeitszettelTab: the production work sheet in the Arbeit tab.
// Touch-friendly fields (44px, Field primitive), pre-filled from the order;
// only changed fields are sent on save.
//
// W4-03: the save is a useMutation; the saved order is written into the
// order-detail query (queryKeys.orders.detail) so the page updates without
// a refetch, and `onOrderUpdated` still reports it to the parent. The form
// resets from the order during render when a newer version arrives (no
// syncing useEffect).
import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ordersApi } from '../../api/orders';
import { queryKeys } from '../../api/queryKeys';
import type { OrderType } from '../../types';
import { useToast } from '../../contexts';
import { getErrorMessage } from '../../lib/errors';
import { Button, Field } from '../../ui';
import { LocationPicker } from '../LocationPicker';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALLOY_OPTIONS = [
  { value: '', label: '— Legierung wählen —' },
  { value: 'Au999', label: 'Au999 — Feingold 24 Karat' },
  { value: 'Au750', label: 'Au750 — Gelbgold 18 Karat' },
  { value: 'Au585', label: 'Au585 — Gelbgold 14 Karat' },
  { value: 'Au375', label: 'Au375 — Gelbgold 9 Karat' },
  { value: 'WG750', label: 'WG750 — Weißgold 18 Karat' },
  { value: 'WG585', label: 'WG585 — Weißgold 14 Karat' },
  { value: 'RG750', label: 'RG750 — Rotgold 18 Karat' },
  { value: 'RG585', label: 'RG585 — Rotgold 14 Karat' },
  { value: 'Ag999', label: 'Ag999 — Feinsilber' },
  { value: 'Ag925', label: 'Ag925 — Sterling Silber' },
  { value: 'Ag800', label: 'Ag800 — Silber 800' },
  { value: 'Pt950', label: 'Pt950 — Platin 950' },
  { value: 'Pt900', label: 'Pt900 — Platin 900' },
  { value: 'Pd950', label: 'Pd950 — Palladium 950' },
];

const SURFACE_FINISH_OPTIONS = [
  { value: '', label: '— Oberfläche wählen —' },
  { value: 'poliert', label: 'Poliert (Hochglanz)' },
  { value: 'matt', label: 'Matt (gebürstet)' },
  { value: 'satiniert', label: 'Satiniert' },
  { value: 'gehämmert', label: 'Gehämmert' },
  { value: 'strukturiert', label: 'Strukturiert' },
  { value: 'oxidiert', label: 'Oxidiert (geschwärzt)' },
  { value: 'sandgestrahlt', label: 'Sandgestrahlt' },
  { value: 'rhodiniert', label: 'Rhodiniert' },
  { value: 'kombination', label: 'Kombination (poliert/matt)' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isRingOrder(order: OrderType): boolean {
  const title = (order.title ?? '').toLowerCase();
  const description = (order.description ?? '').toLowerCase();
  return title.includes('ring') || description.includes('ring');
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ArbeitszettelTabProps {
  order: OrderType;
  /** Optional: the saved order is also written into the order-detail query. */
  onOrderUpdated?: (updated: OrderType) => void;
}

interface FormState {
  actual_weight_g: string;
  labor_hours: string;
  alloy: string;
  ring_size_mm: string;
  surface_finish: string;
  current_location: string;
  location_id: number | null;
}

function toFormState(order: OrderType): FormState {
  return {
    actual_weight_g: order.actual_weight_g != null ? String(order.actual_weight_g) : '',
    labor_hours: order.labor_hours != null ? String(order.labor_hours) : '',
    alloy: order.alloy ?? '',
    ring_size_mm: order.ring_size_mm != null ? String(order.ring_size_mm) : '',
    surface_finish: order.surface_finish ?? '',
    current_location: order.current_location ?? '',
    location_id: order.location_id ?? null,
  };
}

type OrderPatch = Parameters<typeof ordersApi.update>[1];

function parseOptionalNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
}

const optionalText = (value: string): string | null => (value !== '' ? value : null);

/** Only the fields that differ from the order; empty inputs become null. */
function buildPatch(order: OrderType, form: FormState, showRingSize: boolean): Record<string, unknown> {
  const candidates: Array<[string, unknown, unknown]> = [
    ['actual_weight_g', parseOptionalNumber(form.actual_weight_g), order.actual_weight_g ?? null],
    ['labor_hours', parseOptionalNumber(form.labor_hours), order.labor_hours ?? null],
    ['alloy', optionalText(form.alloy), order.alloy ?? null],
    ['surface_finish', optionalText(form.surface_finish), order.surface_finish ?? null],
  ];
  const locationChanged =
    form.location_id !== (order.location_id ?? null) ||
    optionalText(form.current_location) !== (order.current_location ?? null);
  if (locationChanged) {
    candidates.push(['location_id', form.location_id, undefined]);
    candidates.push(['current_location', optionalText(form.current_location), undefined]);
  }
  if (showRingSize) {
    candidates.push(['ring_size_mm', parseOptionalNumber(form.ring_size_mm), order.ring_size_mm ?? null]);
  }
  return Object.fromEntries(
    candidates.filter(([, next, current]) => next !== current).map(([key, next]) => [key, next]),
  );
}

interface SelectFieldProps {
  id: string;
  label: string;
  value: string;
  options: ReadonlyArray<{ value: string; label: string }>;
  onChange: (value: string) => void;
}

function SelectField({ id, label, value, options, onChange }: SelectFieldProps) {
  return (
    <Field label={label} name={id}>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

const ArbeitszettelTab: React.FC<ArbeitszettelTabProps> = ({ order, onOrderUpdated }) => {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(() => toFormState(order));
  // Re-sync when a newer order arrives (save here, another tab, realtime).
  const orderVersion = `${order.id}:${order.updated_at ?? ''}`;
  const [syncedVersion, setSyncedVersion] = useState(orderVersion);
  if (syncedVersion !== orderVersion) {
    setSyncedVersion(orderVersion);
    setForm(toFormState(order));
  }

  const save = useMutation({
    mutationFn: (patch: OrderPatch) => ordersApi.update(order.id, patch),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.orders.detail(order.id), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all });
      onOrderUpdated?.(updated);
      showToast('Arbeitszettel gespeichert', 'success');
    },
    onError: (err: unknown) =>
      showToast(getErrorMessage(err, 'Arbeitszettel konnte nicht gespeichert werden.'), 'error'),
  });

  const showRingSize = isRingOrder(order);
  const handleChange = (field: Exclude<keyof FormState, 'location_id'>, value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    const patch = buildPatch(order, form, showRingSize);
    if (Object.keys(patch).length === 0) {
      showToast('Keine Änderungen erkannt.', 'info');
      return;
    }
    save.mutate(patch as OrderPatch);
  };

  const estimatedWeightHelp =
    order.estimated_weight_g != null
      ? `Soll: ${order.estimated_weight_g.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} g`
      : undefined;

  return (
    <form className="arbeitszettel-form" onSubmit={handleSave} noValidate>
      <div className="arbeitszettel-grid">
        <Field label="Tatsächliches Gewicht" name="actual_weight_g" inputMode="decimal" suffix="g" help={estimatedWeightHelp}>
          <input
            id="az-actual-weight"
            type="text"
            value={form.actual_weight_g}
            onChange={(e) => handleChange('actual_weight_g', e.target.value)}
          />
        </Field>

        <Field label="Arbeitsstunden" name="labor_hours" inputMode="decimal" suffix="h">
          <input
            id="az-labor-hours"
            type="text"
            value={form.labor_hours}
            onChange={(e) => handleChange('labor_hours', e.target.value)}
          />
        </Field>

        <SelectField
          id="az-alloy"
          label="Legierung"
          value={form.alloy}
          options={ALLOY_OPTIONS}
          onChange={(value) => handleChange('alloy', value)}
        />

        {/* Ringmaß: only when title or description mention a ring. */}
        {showRingSize && (
          <Field label="Ringmaß" name="ring_size_mm" inputMode="decimal" suffix="mm" help="z. B. 17,5">
            <input
              id="az-ring-size"
              type="text"
              value={form.ring_size_mm}
              onChange={(e) => handleChange('ring_size_mm', e.target.value)}
            />
          </Field>
        )}

        <SelectField
          id="az-surface"
          label="Oberfläche"
          value={form.surface_finish}
          options={SURFACE_FINISH_OPTIONS}
          onChange={(value) => handleChange('surface_finish', value)}
        />

        <LocationPicker
          id="az-location"
          label="Aktueller Standort"
          value={form.location_id}
          currentName={form.current_location}
          onChange={(location) =>
            setForm((prev) => ({
              ...prev,
              location_id: location?.id ?? null,
              current_location: location?.name ?? '',
            }))
          }
        />
      </div>

      {/* Sonderwünsche: read-only reminder. */}
      {order.special_instructions && (
        <Field
          label="Sonderwünsche (Erinnerung)"
          name="special_instructions"
          help="Schreibgeschützt. Zum Bearbeiten bitte „Auftrag bearbeiten“ verwenden."
          className="arbeitszettel-field--full"
        >
          <textarea
            id="arbeitszettel-special-instructions"
            readOnly
            rows={4}
            value={order.special_instructions}
          />
        </Field>
      )}

      <div className="arbeitszettel-actions">
        <Button type="submit" variant="primary" loading={save.isPending}>
          Arbeitszettel speichern
        </Button>
      </div>
    </form>
  );
};

export default ArbeitszettelTab;
