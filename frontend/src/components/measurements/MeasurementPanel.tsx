// MeasurementPanel — Maßbibliothek für Kunden.
//
// Extracted verbatim from CustomerDetailPage's MasseTab (Task 6, V1.1
// consultation wizard) so it can be reused as wizard step 5. CustomerDetailPage
// re-exports the helpers below so `frontend/src/test/MeasurementForm.test.tsx`
// keeps passing unchanged.
//
// Prop decision: MasseTab used more than `customer.id` from its `Customer`
// prop — it also rendered the legacy `ring_size` / `chain_length_cm` /
// `bracelet_length_cm` fields. Rather than invent a new fetch inside this
// component, the prop narrows to `Pick<Customer, 'id' | 'ring_size' |
// 'chain_length_cm' | 'bracelet_length_cm'>`. CustomerDetailPage already
// has the full Customer loaded and passes it straight through (a full
// Customer structurally satisfies the Pick). The consultation wizard only
// carries `consultation.customer_id`, so its step-5 wiring fetches the
// customer via `customersApi.getById` in a thin wrapper before rendering
// this panel — see ConsultationWizardPage.tsx.
import React, { useCallback, useEffect, useState } from 'react';
import { measurementsApi } from '../../api/measurements';
import { Customer, CustomerMeasurement } from '../../types';
// The moved markup below renders with the .cdetail-* classes styled here.
// Import directly so MeasurementPanel is self-contained wherever it's
// embedded (CustomerDetailPage already imports this too — CSS module
// imports dedupe, so this is a no-op there).
import '../../styles/customer-detail.css';

// German UI labels mapped to backend enum values.
// The form must SUBMIT enum values, not the German labels.
export const HAND_OPTIONS: { value: 'left' | 'right'; label: string }[] = [
  { value: 'left', label: 'Links' },
  { value: 'right', label: 'Rechts' },
];

export const FINGER_OPTIONS: {
  value: 'thumb' | 'index' | 'middle' | 'ring' | 'pinky';
  label: string;
}[] = [
  { value: 'thumb', label: 'Daumen' },
  { value: 'index', label: 'Zeigefinger' },
  { value: 'middle', label: 'Mittelfinger' },
  { value: 'ring', label: 'Ringfinger' },
  { value: 'pinky', label: 'Kleiner Finger' },
];

// Values must exactly match the backend MeasurementType enum values.
// The `unit` per type matches what the backend's MeasurementBase validator
// expects (mm for ring/finger, cm for everything else).
export const MEASUREMENT_TYPES: {
  value: import('../../types').MeasurementType;
  label: string;
  unit: 'mm' | 'cm';
}[] = [
  { value: 'ring_size', label: 'Ringgröße (mm)', unit: 'mm' },
  { value: 'chain_length', label: 'Kettenlänge (cm)', unit: 'cm' },
  { value: 'wrist_circumference', label: 'Handgelenkumfang (cm)', unit: 'cm' },
  { value: 'finger_circumference', label: 'Fingerumfang (mm)', unit: 'mm' },
  { value: 'neck_circumference', label: 'Halsumfang (cm)', unit: 'cm' },
  { value: 'ankle_circumference', label: 'Knöchelumfang (cm)', unit: 'cm' },
];

export interface MeasurementFormState {
  type: import('../../types').MeasurementType;
  value: string;
  hand: 'left' | 'right';
  finger: 'thumb' | 'index' | 'middle' | 'ring' | 'pinky';
}

/**
 * Build the request body for POST /customers/{id}/measurements.
 *
 * Pure helper, exported for unit tests. Returns the exact shape the backend
 * MeasurementCreate model expects:
 *   - measurement_type: enum value (NOT the form's `type` key)
 *   - value: parsed float
 *   - unit: derived from the chosen measurement type
 *   - hand/finger: only included for ring_size and finger_circumference
 */
export function buildMeasurementPayload(form: MeasurementFormState): {
  measurement_type: import('../../types').MeasurementType;
  value: number;
  unit: string;
  hand?: 'left' | 'right';
  finger?: 'thumb' | 'index' | 'middle' | 'ring' | 'pinky';
} {
  const typeMeta = MEASUREMENT_TYPES.find((t) => t.value === form.type);
  const unit = typeMeta?.unit ?? 'mm';
  const needsFinger = form.type === 'ring_size' || form.type === 'finger_circumference';

  const payload: ReturnType<typeof buildMeasurementPayload> = {
    measurement_type: form.type,
    value: parseFloat(form.value),
    unit,
  };
  if (needsFinger) {
    payload.hand = form.hand;
    payload.finger = form.finger;
  }
  return payload;
}

/** Extract a human-readable error message from a backend 422 / Axios error. */
export function extractMeasurementErrorMessage(err: unknown): string {
  // Axios error shape: err.response.data.detail (FastAPI 422) or .data.detail string
  const anyErr = err as {
    response?: { data?: { detail?: unknown }; status?: number };
    message?: string;
  };
  const detail = anyErr?.response?.data?.detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : '';
    const msg = first.msg ?? 'Ungültige Eingabe';
    return field ? `${field}: ${msg}` : msg;
  }
  if (typeof detail === 'string') return detail;
  return anyErr?.message ?? 'Speichern fehlgeschlagen';
}

export const MeasurementPanel: React.FC<{
  customer: Pick<Customer, 'id' | 'ring_size' | 'chain_length_cm' | 'bracelet_length_cm'>;
}> = ({ customer }) => {
  const [measurements, setMeasurements] = useState<CustomerMeasurement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState<MeasurementFormState>({
    type: 'ring_size',
    value: '',
    hand: 'left',
    finger: 'ring',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const loadMeasurements = useCallback(async () => {
    try {
      setIsLoading(true);
      const resp = await measurementsApi.getForCustomer(customer.id);
      setMeasurements(resp.data || []);
    } catch {
      // Backend may not have this endpoint yet — fall back to legacy fields
      setMeasurements([]);
    } finally {
      setIsLoading(false);
    }
  }, [customer.id]);

  useEffect(() => {
    loadMeasurements();
  }, [loadMeasurements]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    try {
      setIsSubmitting(true);
      const payload = buildMeasurementPayload(formData);
      await measurementsApi.add(customer.id, payload);
      setShowForm(false);
      setFormData({ type: 'ring_size', value: '', hand: 'left', finger: 'ring' });
      await loadMeasurements();
    } catch (err) {
      // Surface the backend error so the user knows what went wrong.
      // Silent swallow was the original UX bug.
      setSubmitError(extractMeasurementErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (measurementId: number) => {
    try {
      setDeletingId(measurementId);
      await measurementsApi.remove(measurementId);
      await loadMeasurements();
    } catch {
      // Ignore if endpoint not yet implemented
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="cdetail-panel tab-panel">
      <div className="cdetail-panel__header">
        <h2>Maßbibliothek</h2>
        <button
          className="btn-primary cdetail-btn-add"
          onClick={() => setShowForm((v) => !v)}
        >
          {showForm ? 'Abbrechen' : '+ Maß hinzufügen'}
        </button>
      </div>

      {/* Legacy fields from Customer record */}
      <div className="cdetail-legacy-masse">
        <h3 className="cdetail-section__title">Gespeicherte Maße</h3>
        <div className="cdetail-masse-cards">
          <div className="cdetail-mass-card">
            <span className="cdetail-mass-icon">&#128141;</span>
            <span className="cdetail-mass-label">Ringgröße</span>
            <span className="cdetail-mass-value">
              {customer.ring_size != null ? `${customer.ring_size} mm` : '—'}
            </span>
          </div>
          <div className="cdetail-mass-card">
            <span className="cdetail-mass-icon">&#128278;</span>
            <span className="cdetail-mass-label">Kettenlänge</span>
            <span className="cdetail-mass-value">
              {customer.chain_length_cm != null ? `${customer.chain_length_cm} cm` : '—'}
            </span>
          </div>
          <div className="cdetail-mass-card">
            <span className="cdetail-mass-icon">&#8987;</span>
            <span className="cdetail-mass-label">Armbandlänge</span>
            <span className="cdetail-mass-value">
              {customer.bracelet_length_cm != null ? `${customer.bracelet_length_cm} cm` : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Add measurement form */}
      {showForm && (
        <form className="cdetail-masse-form" onSubmit={handleAdd}>
          <div className="form-group">
            <label>Maßart</label>
            <select
              value={formData.type}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  type: e.target.value as MeasurementFormState['type'],
                })
              }
            >
              {MEASUREMENT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>Wert</label>
            <input
              type="number"
              step="0.1"
              value={formData.value}
              onChange={(e) => setFormData({ ...formData, value: e.target.value })}
              placeholder="z. B. 53.4"
              required
            />
          </div>
          {(formData.type === 'ring_size' || formData.type === 'finger_circumference') && (
            <>
              <div className="form-group">
                <label>Hand</label>
                <select
                  value={formData.hand}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      hand: e.target.value as MeasurementFormState['hand'],
                    })
                  }
                >
                  {HAND_OPTIONS.map((h) => (
                    <option key={h.value} value={h.value}>{h.label}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Finger</label>
                <select
                  value={formData.finger}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      finger: e.target.value as MeasurementFormState['finger'],
                    })
                  }
                >
                  {FINGER_OPTIONS.map((f) => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </select>
              </div>
            </>
          )}
          {submitError && (
            <div
              className="cdetail-masse-form__error"
              role="alert"
              style={{ color: 'var(--color-error, #b91c1c)', marginTop: '0.5rem' }}
            >
              {submitError}
            </div>
          )}
          <div className="cdetail-masse-form__actions">
            <button
              type="submit"
              className="btn-primary"
              disabled={isSubmitting || !formData.value}
            >
              {isSubmitting ? 'Speichern...' : 'Maß speichern'}
            </button>
          </div>
        </form>
      )}

      {/* Dynamic measurements list */}
      {isLoading ? (
        <div className="cdetail-loading">Lade Maße...</div>
      ) : measurements.length > 0 ? (
        <div className="cdetail-masse-list">
          <h3 className="cdetail-section__title">Weitere Maße</h3>
          {measurements.map((m) => (
            <div key={m.id} className="cdetail-mass-card cdetail-mass-card--dynamic">
              <span className="cdetail-mass-label">
                {MEASUREMENT_TYPES.find((t) => t.value === m.measurement_type)?.label || m.measurement_type}
                {m.hand && m.finger && (
                  <span className="cdetail-mass-sublabel">
                    {' '}
                    · {HAND_OPTIONS.find((h) => h.value === m.hand)?.label ?? m.hand}
                    , {FINGER_OPTIONS.find((f) => f.value === m.finger)?.label ?? m.finger}
                  </span>
                )}
              </span>
              <span className="cdetail-mass-value">{m.value} {m.unit}</span>
              <button
                className="cdetail-mass-delete"
                aria-label="Maß löschen"
                disabled={deletingId === m.id}
                onClick={() => handleDelete(m.id)}
              >
                {deletingId === m.id ? '...' : 'Löschen'}
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
};
