/**
 * CalendarEventModal (W4-03): create or edit a stored calendar event.
 *
 * Built on the src/ui Modal (focus trap, Escape, focus return, full screen
 * below 600px) and Field. A dirty form asks before closing; delete asks for
 * confirmation in a danger Dialog and sits apart from the save action.
 * `onSave` / `onDelete` throw on failure; the error is shown in the dialog.
 */
import React, { useId, useRef, useState } from 'react';
import type {
  CalendarEvent,
  CalendarEventCreate,
  CalendarEventType,
  CalendarEventUpdate,
} from '../types';
import { getErrorMessage } from '../lib/errors';
import { EVENT_TYPE_LABELS } from './calendar/calendarGrid';
import { Button, Dialog, Field, Modal } from '../ui';

interface Props {
  /** When provided the modal is in edit mode; otherwise create mode. */
  event?: CalendarEvent;
  /** Pre-filled start date (YYYY-MM-DD) when creating from a day click */
  defaultDate?: string;
  onSave: (data: CalendarEventCreate | CalendarEventUpdate) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

const TITLE_MAX_LENGTH = 200;
const NOTES_MAX_LENGTH = 2000;

/** "2026-03-15T14:00:00Z" → "2026-03-15T14:00" for <input type="datetime-local"> */
function isoToLocal(iso?: string | null): string {
  return iso ? iso.substring(0, 16) : '';
}

function dateToLocalDatetime(date?: string): string {
  return date ? `${date}T00:00` : '';
}

function localToIso(local: string): string {
  return local ? new Date(local).toISOString() : '';
}

interface EventForm {
  title: string;
  eventType: CalendarEventType;
  start: string;
  end: string;
  allDay: boolean;
  notes: string;
}

function initialForm(event?: CalendarEvent, defaultDate?: string): EventForm {
  return {
    title: event?.title ?? '',
    eventType: event?.event_type ?? 'workshop_task',
    start: event ? isoToLocal(event.start_datetime) : dateToLocalDatetime(defaultDate),
    end: isoToLocal(event?.end_datetime),
    allDay: event?.all_day ?? false,
    notes: event?.description ?? '',
  };
}

function toPayload(form: EventForm): CalendarEventCreate | CalendarEventUpdate {
  return {
    title: form.title.trim(),
    event_type: form.eventType,
    start_datetime: form.allDay ? `${form.start.substring(0, 10)}T00:00:00.000Z` : localToIso(form.start),
    end_datetime: form.end && !form.allDay ? localToIso(form.end) : undefined,
    all_day: form.allDay,
    description: form.notes.trim() || undefined,
  };
}

type FieldErrors = Partial<Record<'title' | 'start', string>>;

function validateForm(form: EventForm): FieldErrors {
  return {
    ...(form.title.trim() ? {} : { title: 'Titel fehlt. Bitte eine Terminbezeichnung eingeben.' }),
    ...(form.start ? {} : { start: 'Startdatum fehlt. Bitte ein Datum wählen.' }),
  };
}

export const CalendarEventModal: React.FC<Props> = ({
  event,
  defaultDate,
  onSave,
  onDelete,
  onClose,
}) => {
  const isEdit = Boolean(event);
  const formId = useId();
  const titleRef = useRef<HTMLInputElement>(null);
  const [initial] = useState(() => initialForm(event, defaultDate));
  const [form, setForm] = useState<EventForm>(initial);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const isDirty = (Object.keys(form) as (keyof EventForm)[]).some((k) => form[k] !== initial[k]);
  const update = <K extends keyof EventForm>(key: K, value: EventForm[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors = validateForm(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setError(null);
    setIsSaving(true);
    try {
      await onSave(toPayload(form));
      onClose();
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Termin konnte nicht gespeichert werden.'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!onDelete) return;
    setIsDeleting(true);
    try {
      await onDelete();
      onClose();
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Termin konnte nicht gelöscht werden.'));
    } finally {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const footer = (
    <>
      {isEdit && onDelete && (
        <Button
          variant="ghost"
          icon="trash"
          className="event-modal__delete"
          onClick={() => setShowDeleteConfirm(true)}
          disabled={isSaving}
        >
          Termin löschen
        </Button>
      )}
      <Button variant="secondary" onClick={onClose} disabled={isSaving}>
        Abbrechen
      </Button>
      <Button type="submit" form={formId} loading={isSaving}>
        {isEdit ? 'Termin speichern' : 'Termin anlegen'}
      </Button>
    </>
  );

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title={isEdit ? 'Termin bearbeiten' : 'Neuer Termin'}
        initialFocusRef={titleRef}
        isDirty={isDirty && !isSaving}
        footer={footer}
      >
        <form id={formId} onSubmit={handleSubmit} className="event-form" noValidate>
          <Field label="Titel" name="title" required error={fieldErrors.title}>
            <input
              id="event-title"
              ref={titleRef}
              type="text"
              value={form.title}
              onChange={(e) => update('title', e.target.value)}
              maxLength={TITLE_MAX_LENGTH}
            />
          </Field>

          <Field label="Typ" name="event_type">
            <select
              id="event-type"
              value={form.eventType}
              onChange={(e) => update('eventType', e.target.value as CalendarEventType)}
            >
              {(Object.entries(EVENT_TYPE_LABELS) as [CalendarEventType, string][]).map(
                ([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ),
              )}
            </select>
          </Field>

          <label className="event-form__checkbox" htmlFor="event-allday">
            <input
              id="event-allday"
              type="checkbox"
              checked={form.allDay}
              onChange={(e) => update('allDay', e.target.checked)}
            />
            Ganztägig
          </label>

          <Field label={form.allDay ? 'Datum' : 'Beginn'} name="start" required error={fieldErrors.start}>
            {form.allDay ? (
              <input
                id="event-start"
                type="date"
                value={form.start.substring(0, 10)}
                onChange={(e) => update('start', `${e.target.value}T00:00`)}
              />
            ) : (
              <input
                id="event-start"
                type="datetime-local"
                value={form.start}
                onChange={(e) => update('start', e.target.value)}
              />
            )}
          </Field>

          {!form.allDay && (
            <Field label="Ende" name="end">
              <input
                id="event-end"
                type="datetime-local"
                value={form.end}
                onChange={(e) => update('end', e.target.value)}
                min={form.start}
              />
            </Field>
          )}

          <Field label="Notizen" name="notes" help="Optional.">
            <textarea
              id="event-notes"
              value={form.notes}
              onChange={(e) => update('notes', e.target.value)}
              rows={3}
              maxLength={NOTES_MAX_LENGTH}
            />
          </Field>

          {error && (
            <p className="event-form__error" role="alert">
              {error}
            </p>
          )}
        </form>
      </Modal>

      <Dialog
        open={showDeleteConfirm}
        title="Termin löschen"
        message="Möchten Sie diesen Termin wirklich löschen? Das lässt sich nicht rückgängig machen."
        confirmLabel="Löschen"
        variant="danger"
        loading={isDeleting}
        onConfirm={() => void handleDelete()}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
};

export default CalendarEventModal;
