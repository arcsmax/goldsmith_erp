// Time entry form (manual entry and edit) on the src/ui Modal + Field (W4-03).
//
// Orders and activities come from the shared picker queries. In edit mode
// the destructive "Eintrag löschen" sits in the footer, away from the
// frequent "Eintrag speichern" (playbook P4), and asks via ConfirmDialog
// in the page.
import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { activitiesQuery, orderPickerQuery } from '../../api/timeTrackingQueries';
import { LocationPicker } from '../LocationPicker';
import { Button, Field, Modal } from '../../ui';
import type { TimeEntry, TimeEntryCreateInput, TimeEntryUpdateInput } from '../../types';
import '../../styles/time-tracking.css';

interface TimeEntryFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: TimeEntryCreateInput | TimeEntryUpdateInput) => Promise<void>;
  entry?: TimeEntry | null;
  isLoading?: boolean;
  /** Edit mode only: delete this entry (the page confirms first). */
  onDelete?: (entry: TimeEntry) => void;
}

interface FormData {
  order_id: string;
  activity_id: string;
  start_date: string;
  start_time: string;
  end_date: string;
  end_time: string;
  location: string;
  location_id: number | null;
  notes: string;
  complexity_rating: string;
  quality_rating: string;
  rework_required: boolean;
}

type FormErrors = Partial<Record<'order_id' | 'activity_id' | 'start_time' | 'end_time', string>>;

const COMPLEXITY_OPTIONS = ['Sehr einfach', 'Einfach', 'Mittel', 'Komplex', 'Sehr komplex'];
const QUALITY_OPTIONS = ['Schlecht', 'Unterdurchschnittlich', 'Durchschnittlich', 'Gut', 'Exzellent'];

function emptyForm(now = new Date()): FormData {
  return {
    order_id: '',
    activity_id: '',
    start_date: now.toISOString().split('T')[0],
    start_time: now.toTimeString().slice(0, 5),
    end_date: now.toISOString().split('T')[0],
    end_time: '',
    location: '',
    location_id: null,
    notes: '',
    complexity_rating: '',
    quality_rating: '',
    rework_required: false,
  };
}

function formFromEntry(entry: TimeEntry): FormData {
  const startDate = new Date(entry.start_time);
  const endDate = entry.end_time ? new Date(entry.end_time) : new Date();
  return {
    order_id: entry.order_id.toString(),
    activity_id: entry.activity_id.toString(),
    start_date: startDate.toISOString().split('T')[0],
    start_time: startDate.toTimeString().slice(0, 5),
    end_date: endDate.toISOString().split('T')[0],
    end_time: entry.end_time ? endDate.toTimeString().slice(0, 5) : '',
    location: entry.location || '',
    location_id: entry.location_id ?? null,
    notes: entry.notes || '',
    complexity_rating: entry.complexity_rating?.toString() || '',
    quality_rating: entry.quality_rating?.toString() || '',
    rework_required: entry.rework_required || false,
  };
}

const combineDateTime = (date: string, time: string): string => `${date}T${time}:00`;

function durationMinutes(form: FormData): number | null {
  if (!form.end_time) return null;
  const start = new Date(combineDateTime(form.start_date, form.start_time));
  const end = new Date(combineDateTime(form.end_date, form.end_time));
  return Math.floor((end.getTime() - start.getTime()) / 60000);
}

function formatDuration(minutes: number | null): string {
  if (minutes === null) return '–';
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

function validate(form: FormData): FormErrors {
  const errors: FormErrors = {};
  if (!form.order_id) errors.order_id = 'Auftrag fehlt. Bitte einen Auftrag wählen.';
  if (!form.activity_id) errors.activity_id = 'Aktivität fehlt. Bitte eine Aktivität wählen.';
  if (!form.start_time) errors.start_time = 'Startzeit fehlt.';
  const duration = durationMinutes(form);
  if (duration !== null && duration < 0) errors.end_time = 'Endzeit muss nach der Startzeit liegen.';
  return errors;
}

/** Location fields only when new or changed, so an old entry whose
 * Standort was deactivated can still be edited. */
function locationFields(
  form: FormData,
  initial: FormData | null,
): Pick<TimeEntryCreateInput, 'location' | 'location_id'> {
  if (initial && form.location_id === initial.location_id && form.location === initial.location) {
    return {};
  }
  return { location_id: form.location_id, location: form.location || undefined };
}

function toSubmitData(
  form: FormData,
  initial: FormData | null,
): TimeEntryCreateInput | TimeEntryUpdateInput {
  const endDateTime = form.end_time ? combineDateTime(form.end_date, form.end_time) : undefined;
  return {
    order_id: parseInt(form.order_id, 10),
    activity_id: parseInt(form.activity_id, 10),
    start_time: combineDateTime(form.start_date, form.start_time),
    end_time: endDateTime,
    duration_minutes: endDateTime ? durationMinutes(form) || undefined : undefined,
    ...locationFields(form, initial),
    notes: form.notes || undefined,
    complexity_rating: form.complexity_rating ? parseInt(form.complexity_rating, 10) : undefined,
    quality_rating: form.quality_rating ? parseInt(form.quality_rating, 10) : undefined,
    rework_required: form.rework_required || undefined,
  };
}

export const TimeEntryFormModal: React.FC<TimeEntryFormModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  entry,
  isLoading = false,
  onDelete,
}) => {
  const isEditMode = Boolean(entry);
  const orders = useQuery({ ...orderPickerQuery(), enabled: isOpen });
  const activities = useQuery({ ...activitiesQuery(false), enabled: isOpen });
  const [form, setForm] = useState<FormData>(() => emptyForm());
  const [initial, setInitial] = useState<FormData>(form);
  const [errors, setErrors] = useState<FormErrors>({});

  useEffect(() => {
    if (!isOpen) return;
    const next = entry ? formFromEntry(entry) : emptyForm();
    setForm(next);
    setInitial(next);
    setErrors({});
  }, [isOpen, entry]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => {
    const { name, value, type } = e.target;
    const checked = (e.target as HTMLInputElement).checked;
    setForm((prev) => ({ ...prev, [name]: type === 'checkbox' ? checked : value }));
    setErrors((prev) => ({ ...prev, [name]: undefined }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const nextErrors = validate(form);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    await onSubmit(toSubmitData(form, isEditMode ? initial : null));
  };

  const isDirty = JSON.stringify(form) !== JSON.stringify(initial);
  const duration = durationMinutes(form);
  const formId = 'time-entry-form';

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      isDirty={isDirty && !isLoading}
      title={isEditMode ? 'Zeiteintrag bearbeiten' : 'Manueller Zeiteintrag'}
      size="lg"
      className="time-entry-modal"
      footer={
        <>
          {isEditMode && entry && onDelete && (
            <Button
              variant="danger"
              icon="trash"
              className="time-entry-modal__delete"
              onClick={() => onDelete(entry)}
              disabled={isLoading}
            >
              Eintrag löschen
            </Button>
          )}
          <Button variant="secondary" size="lg" onClick={onClose} disabled={isLoading}>
            Abbrechen
          </Button>
          <Button type="submit" size="lg" form={formId} loading={isLoading}>
            {isEditMode ? 'Eintrag speichern' : 'Eintrag anlegen'}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={(e) => void handleSubmit(e)} noValidate>
        <div className="time-entry-form-grid">
          <Field label="Auftrag" name="order_id" required error={errors.order_id}>
            <select id="order_id" value={form.order_id} onChange={handleChange}>
              <option value="">{orders.isPending ? 'Wird geladen…' : 'Auftrag wählen'}</option>
              {(orders.data ?? []).map((order) => (
                <option key={order.id} value={order.id}>
                  #{order.id} – {order.title}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Aktivität" name="activity_id" required error={errors.activity_id}>
            <select id="activity_id" value={form.activity_id} onChange={handleChange}>
              <option value="">{activities.isPending ? 'Wird geladen…' : 'Aktivität wählen'}</option>
              {(activities.data ?? []).map((activity) => (
                <option key={activity.id} value={activity.id}>
                  {activity.name}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Startdatum" name="start_date" required>
            <input type="date" id="start_date" value={form.start_date} onChange={handleChange} />
          </Field>
          <Field label="Startzeit" name="start_time" required error={errors.start_time}>
            <input type="time" id="start_time" value={form.start_time} onChange={handleChange} />
          </Field>
          <Field label="Enddatum" name="end_date">
            <input type="date" id="end_date" value={form.end_date} onChange={handleChange} />
          </Field>
          <Field label="Endzeit" name="end_time" error={errors.end_time}>
            <input type="time" id="end_time" value={form.end_time} onChange={handleChange} />
          </Field>

          {form.end_time && (
            <p className="time-entry-duration" aria-live="polite">
              Dauer: <strong>{formatDuration(duration)}</strong>
            </p>
          )}

          <LocationPicker
            value={form.location_id}
            currentName={form.location}
            onChange={(location) =>
              setForm((prev) => ({
                ...prev,
                location_id: location?.id ?? null,
                location: location?.name ?? '',
              }))
            }
          />

          <Field label="Komplexität (1-5)" name="complexity_rating">
            <select id="complexity_rating" value={form.complexity_rating} onChange={handleChange}>
              <option value="">Nicht bewertet</option>
              {COMPLEXITY_OPTIONS.map((label, index) => (
                <option key={label} value={index + 1}>
                  {index + 1} – {label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Qualität (1-5)" name="quality_rating">
            <select id="quality_rating" value={form.quality_rating} onChange={handleChange}>
              <option value="">Nicht bewertet</option>
              {QUALITY_OPTIONS.map((label, index) => (
                <option key={label} value={index + 1}>
                  {index + 1} – {label}
                </option>
              ))}
            </select>
          </Field>

          <label className="time-entry-check">
            <input
              type="checkbox"
              name="rework_required"
              checked={form.rework_required}
              onChange={handleChange}
            />
            Nacharbeit erforderlich
          </label>
        </div>

        <Field label="Notizen" name="notes" className="time-entry-notes">
          <textarea id="notes" value={form.notes} onChange={handleChange} rows={3} />
        </Field>
      </form>
    </Modal>
  );
};
