/**
 * CalendarEventModal
 *
 * Modal for creating or editing a calendar event.
 * Opened from CalendarPage via the "Neuer Termin" button or by clicking an
 * existing stored event.
 *
 * Design notes (Jason):
 * - All labels in German as per the goldsmith workshop context.
 * - Touch targets >= 44px for workshop use (gloves / paste residue).
 * - The backdrop uses the glass-morphism aesthetic from the design system.
 * - Color-coded event type selector uses the same palette as CalendarPage.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  CalendarEvent,
  CalendarEventCreate,
  CalendarEventType,
  CalendarEventUpdate,
} from '../types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  /** When provided the modal is in edit mode; otherwise create mode. */
  event?: CalendarEvent;
  /** Pre-filled start date (YYYY-MM-DD) when creating from a day click */
  defaultDate?: string;
  onSave: (data: CalendarEventCreate | CalendarEventUpdate) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const EVENT_TYPE_LABELS: Record<CalendarEventType, string> = {
  ORDER_DEADLINE: 'Auftragsdeadline',
  WORKSHOP_TASK: 'Werkstattaufgabe',
  APPOINTMENT: 'Termin',
  REMINDER: 'Erinnerung',
};

/** Convert an ISO datetime string to a local <input type="datetime-local"> value */
function isoToLocal(iso?: string | null): string {
  if (!iso) return '';
  // "2026-03-15T14:00:00Z" → "2026-03-15T14:00"
  return iso.substring(0, 16);
}

/** Convert a date string (YYYY-MM-DD) to a datetime-local value at midnight */
function dateToLocalDatetime(date?: string): string {
  if (!date) return '';
  return `${date}T00:00`;
}

/** Convert a local datetime-local value back to an ISO string */
function localToIso(local: string): string {
  if (!local) return '';
  return new Date(local).toISOString();
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const CalendarEventModal: React.FC<Props> = ({
  event,
  defaultDate,
  onSave,
  onDelete,
  onClose,
}) => {
  const isEdit = Boolean(event);

  const [title, setTitle] = useState(event?.title ?? '');
  const [eventType, setEventType] = useState<CalendarEventType>(
    event?.event_type ?? 'WORKSHOP_TASK'
  );
  const [startDatetime, setStartDatetime] = useState(
    event ? isoToLocal(event.start_datetime) : dateToLocalDatetime(defaultDate)
  );
  const [endDatetime, setEndDatetime] = useState(
    isoToLocal(event?.end_datetime)
  );
  const [allDay, setAllDay] = useState(event?.all_day ?? false);
  const [notes, setNotes] = useState(event?.description ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const titleRef = useRef<HTMLInputElement>(null);

  // Focus the title field when the modal opens
  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError('Bitte einen Titel eingeben.');
      return;
    }
    if (!startDatetime) {
      setError('Bitte ein Startdatum angeben.');
      return;
    }

    setError(null);
    setIsSaving(true);

    try {
      const payload: CalendarEventCreate | CalendarEventUpdate = {
        title: title.trim(),
        event_type: eventType,
        start_datetime: allDay
          ? `${startDatetime.substring(0, 10)}T00:00:00.000Z`
          : localToIso(startDatetime),
        end_datetime: endDatetime ? localToIso(endDatetime) : undefined,
        all_day: allDay,
        description: notes.trim() || undefined,
      };

      await onSave(payload);
      onClose();
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ?? 'Fehler beim Speichern des Termins.'
      );
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
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ?? 'Fehler beim Löschen des Termins.'
      );
    } finally {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="event-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-panel event-modal-panel">
        {/* Modal header */}
        <div className="modal-header">
          <h2 id="event-modal-title" className="modal-title">
            {isEdit ? 'Termin bearbeiten' : 'Neuer Termin'}
          </h2>
          <button
            type="button"
            className="modal-close-btn"
            onClick={onClose}
            aria-label="Schließen"
          >
            &times;
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="event-form" noValidate>
          {/* Title */}
          <div className="form-group">
            <label htmlFor="event-title" className="form-label">
              Titel <span aria-hidden="true">*</span>
            </label>
            <input
              id="event-title"
              ref={titleRef}
              type="text"
              className="form-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Terminbezeichnung"
              maxLength={200}
              required
            />
          </div>

          {/* Event type */}
          <div className="form-group">
            <label htmlFor="event-type" className="form-label">
              Typ
            </label>
            <select
              id="event-type"
              className="form-select"
              value={eventType}
              onChange={(e) => setEventType(e.target.value as CalendarEventType)}
            >
              {(
                Object.entries(EVENT_TYPE_LABELS) as [CalendarEventType, string][]
              ).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {/* All-day toggle */}
          <div className="form-group form-group--inline">
            <input
              id="event-allday"
              type="checkbox"
              className="form-checkbox"
              checked={allDay}
              onChange={(e) => setAllDay(e.target.checked)}
            />
            <label htmlFor="event-allday" className="form-label-inline">
              Ganztägig
            </label>
          </div>

          {/* Start datetime */}
          <div className="form-group">
            <label htmlFor="event-start" className="form-label">
              {allDay ? 'Datum' : 'Beginn'} <span aria-hidden="true">*</span>
            </label>
            {allDay ? (
              <input
                id="event-start"
                type="date"
                className="form-input"
                value={startDatetime.substring(0, 10)}
                onChange={(e) =>
                  setStartDatetime(`${e.target.value}T00:00`)
                }
                required
              />
            ) : (
              <input
                id="event-start"
                type="datetime-local"
                className="form-input"
                value={startDatetime}
                onChange={(e) => setStartDatetime(e.target.value)}
                required
              />
            )}
          </div>

          {/* End datetime (hidden when all_day) */}
          {!allDay && (
            <div className="form-group">
              <label htmlFor="event-end" className="form-label">
                Ende
              </label>
              <input
                id="event-end"
                type="datetime-local"
                className="form-input"
                value={endDatetime}
                onChange={(e) => setEndDatetime(e.target.value)}
                min={startDatetime}
              />
            </div>
          )}

          {/* Notes */}
          <div className="form-group">
            <label htmlFor="event-notes" className="form-label">
              Notizen
            </label>
            <textarea
              id="event-notes"
              className="form-textarea"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Optionale Notizen zum Termin"
              rows={3}
              maxLength={2000}
            />
          </div>

          {/* Error message */}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          {/* Action buttons */}
          <div className="form-actions">
            {isEdit && onDelete && !showDeleteConfirm && (
              <button
                type="button"
                className="btn btn-danger-outline"
                onClick={() => setShowDeleteConfirm(true)}
              >
                Löschen
              </button>
            )}

            {showDeleteConfirm && (
              <div className="delete-confirm">
                <span>Termin wirklich löschen?</span>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={handleDelete}
                  disabled={isDeleting}
                >
                  {isDeleting ? 'Löscht...' : 'Ja, löschen'}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowDeleteConfirm(false)}
                >
                  Abbrechen
                </button>
              </div>
            )}

            <div className="form-actions-right">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
                disabled={isSaving}
              >
                Abbrechen
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={isSaving}
              >
                {isSaving ? 'Speichert...' : isEdit ? 'Speichern' : 'Erstellen'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CalendarEventModal;
