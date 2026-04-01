// ArbeitszettelTab — Production Work Sheet for workshop use
// Touch-friendly form with min 44px inputs, German labels throughout.
// All fields are pre-filled from the current order; only changed fields are sent on save.

import React, { useEffect, useState } from 'react';
import { ordersApi } from '../../api/orders';
import { OrderType } from '../../types';
import { useToast } from '../../contexts';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALLOY_OPTIONS = [
  { value: '', label: '-- Legierung wählen --' },
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
  { value: '', label: '-- Oberfläche wählen --' },
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

const LOCATION_OPTIONS = [
  { value: '', label: '-- Standort wählen --' },
  { value: 'werkbank_1', label: 'Werkbank 1' },
  { value: 'werkbank_2', label: 'Werkbank 2' },
  { value: 'werkbank_3', label: 'Werkbank 3' },
  { value: 'schleifbereich', label: 'Schleifbereich' },
  { value: 'galvanik', label: 'Galvanik' },
  { value: 'polierbereich', label: 'Polierbereich' },
  { value: 'fassbereich', label: 'Fassbereich (Steinbesatz)' },
  { value: 'laser', label: 'Laserbereich' },
  { value: 'eingangspruefung', label: 'Eingangsprüfung' },
  { value: 'qualitaetskontrolle', label: 'Qualitätskontrolle' },
  { value: 'ausgabe', label: 'Ausgabe / Abholung' },
  { value: 'tresor', label: 'Tresor' },
  { value: 'externe_bearbeitung', label: 'Externe Bearbeitung' },
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
  onOrderUpdated: (updated: OrderType) => void;
}

interface FormState {
  actual_weight_g: string;
  labor_hours: string;
  alloy: string;
  ring_size_mm: string;
  surface_finish: string;
  current_location: string;
}

function toFormState(order: OrderType): FormState {
  return {
    actual_weight_g: order.actual_weight_g != null ? String(order.actual_weight_g) : '',
    labor_hours: order.labor_hours != null ? String(order.labor_hours) : '',
    alloy: order.alloy ?? '',
    ring_size_mm: order.ring_size_mm != null ? String(order.ring_size_mm) : '',
    surface_finish: order.surface_finish ?? '',
    current_location: order.current_location ?? '',
  };
}

const ArbeitszettelTab: React.FC<ArbeitszettelTabProps> = ({ order, onOrderUpdated }) => {
  const { showToast } = useToast();
  const [form, setForm] = useState<FormState>(() => toFormState(order));
  const [isSaving, setIsSaving] = useState(false);

  // Re-sync form when the order prop changes (e.g. after a save from another tab).
  useEffect(() => {
    setForm(toFormState(order));
  }, [order.id, order.updated_at]);

  const showRingSize = isRingOrder(order);

  const handleChange = (
    field: keyof FormState,
    value: string
  ) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);

    // Build patch — only include fields that differ from the current order value,
    // and coerce empty strings to null for optional numeric/text fields.
    const patch: Record<string, unknown> = {};

    const actualWeight = form.actual_weight_g !== '' ? parseFloat(form.actual_weight_g) : null;
    if (actualWeight !== (order.actual_weight_g ?? null)) {
      patch.actual_weight_g = actualWeight;
    }

    const laborHours = form.labor_hours !== '' ? parseFloat(form.labor_hours) : null;
    if (laborHours !== (order.labor_hours ?? null)) {
      patch.labor_hours = laborHours;
    }

    const alloy = form.alloy !== '' ? form.alloy : null;
    if (alloy !== (order.alloy ?? null)) {
      patch.alloy = alloy;
    }

    if (showRingSize) {
      const ringSizeMm = form.ring_size_mm !== '' ? parseFloat(form.ring_size_mm) : null;
      if (ringSizeMm !== (order.ring_size_mm ?? null)) {
        patch.ring_size_mm = ringSizeMm;
      }
    }

    const surfaceFinish = form.surface_finish !== '' ? form.surface_finish : null;
    if (surfaceFinish !== (order.surface_finish ?? null)) {
      patch.surface_finish = surfaceFinish;
    }

    const currentLocation = form.current_location !== '' ? form.current_location : null;
    if (currentLocation !== (order.current_location ?? null)) {
      patch.current_location = currentLocation;
    }

    if (Object.keys(patch).length === 0) {
      showToast('Keine Änderungen erkannt.', 'info');
      setIsSaving(false);
      return;
    }

    try {
      const updated = await ordersApi.update(order.id, patch as Parameters<typeof ordersApi.update>[1]);
      onOrderUpdated(updated);
      showToast('Arbeitszettel gespeichert.', 'success');
    } catch (err: any) {
      showToast(
        err.response?.data?.detail || 'Fehler beim Speichern des Arbeitszettels.',
        'error'
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="tab-panel">
      <h2>Arbeitszettel</h2>

      <form className="arbeitszettel-form" onSubmit={handleSave} noValidate>
        <div className="arbeitszettel-grid">

          {/* Tatsächliches Gewicht */}
          <div className="arbeitszettel-field">
            <label htmlFor="az-actual-weight" className="az-label">
              Tatsächliches Gewicht (g)
            </label>
            {order.estimated_weight_g != null && (
              <p className="az-reference">
                Soll: {order.estimated_weight_g.toFixed(2)} g
              </p>
            )}
            <input
              id="az-actual-weight"
              className="az-input"
              type="number"
              step="0.01"
              min="0"
              placeholder="0.00"
              value={form.actual_weight_g}
              onChange={(e) => handleChange('actual_weight_g', e.target.value)}
            />
          </div>

          {/* Arbeitsstunden */}
          <div className="arbeitszettel-field">
            <label htmlFor="az-labor-hours" className="az-label">
              Arbeitsstunden (h)
            </label>
            <input
              id="az-labor-hours"
              className="az-input"
              type="number"
              step="0.25"
              min="0"
              placeholder="0.00"
              value={form.labor_hours}
              onChange={(e) => handleChange('labor_hours', e.target.value)}
            />
          </div>

          {/* Legierung */}
          <div className="arbeitszettel-field">
            <label htmlFor="az-alloy" className="az-label">
              Legierung
            </label>
            <select
              id="az-alloy"
              className="az-input az-select"
              value={form.alloy}
              onChange={(e) => handleChange('alloy', e.target.value)}
            >
              {ALLOY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Ringmaß — only shown when order title/description mentions ring */}
          {showRingSize && (
            <div className="arbeitszettel-field">
              <label htmlFor="az-ring-size" className="az-label">
                Ringmaß (mm)
              </label>
              <input
                id="az-ring-size"
                className="az-input"
                type="number"
                step="0.5"
                min="10"
                max="100"
                placeholder="z.B. 17.5"
                value={form.ring_size_mm}
                onChange={(e) => handleChange('ring_size_mm', e.target.value)}
              />
            </div>
          )}

          {/* Oberfläche */}
          <div className="arbeitszettel-field">
            <label htmlFor="az-surface" className="az-label">
              Oberfläche
            </label>
            <select
              id="az-surface"
              className="az-input az-select"
              value={form.surface_finish}
              onChange={(e) => handleChange('surface_finish', e.target.value)}
            >
              {SURFACE_FINISH_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Aktueller Standort */}
          <div className="arbeitszettel-field">
            <label htmlFor="az-location" className="az-label">
              Aktueller Standort
            </label>
            <select
              id="az-location"
              className="az-input az-select"
              value={form.current_location}
              onChange={(e) => handleChange('current_location', e.target.value)}
            >
              {LOCATION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

        </div>

        {/* Sonderwünsche — read-only reminder */}
        {order.special_instructions && (
          <div className="arbeitszettel-field arbeitszettel-field--full">
            <label className="az-label">
              Sonderwünsche (Erinnerung)
            </label>
            <textarea
              className="az-textarea az-textarea--readonly"
              readOnly
              rows={4}
              value={order.special_instructions}
              aria-label="Sonderwünsche (schreibgeschützt)"
            />
            <p className="az-hint">
              Dieses Feld ist schreibgeschützt. Zum Bearbeiten bitte die Auftragsdetails verwenden.
            </p>
          </div>
        )}

        <div className="arbeitszettel-actions">
          <button
            type="submit"
            className="az-save-btn"
            disabled={isSaving}
          >
            {isSaving ? 'Speichern...' : 'Speichern'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default ArbeitszettelTab;
