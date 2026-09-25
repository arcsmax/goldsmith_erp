// RunningTimerEditSheet — "Timer bearbeiten" for the RUNNING timer.
//
// Opened from the TimerWidget and the time-tracking page's running card.
// Activity (ActivityPicker), job (JobPicker, orders), location
// (LocationPicker), notes and the start time; saves the changed fields
// through PATCH /time-tracking/{id} (useMutation). On success the response
// (with activity_name / order_title) is written into the running-timer
// cache so the widget shows the new activity and location at once, then
// the ['timer'] root is invalidated. Mount only while open: it needs the
// QueryClientProvider.
import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { queryKeys } from '../../api/queryKeys';
import { timeTrackingApi, type RunningTimeEntry, type RunningTimeEntryEditInput } from '../../api/time-tracking';
import { getErrorMessage } from '../../lib/errors';
import type { Activity } from '../../types';
import { parseUTC } from '../../utils/formatters';
import { Button, Field, Sheet } from '../../ui';
import ActivityPicker from '../ActivityPicker';
import LocationPicker from '../LocationPicker';
import { JobPicker } from './JobPicker';
import '../../styles/components/RunningTimerEditSheet.css';
import { buildEditPayload, draftFromEntry, resolveStartTime, type EditDraft } from './runningTimerEdit';

export interface RunningTimerEditSheetProps {
  entry: RunningTimeEntry;
  onClose: () => void;
  onSaved?: (entry: RunningTimeEntry) => void;
}

type OpenPicker = 'activity' | 'job' | 'location' | null;

const NOTES_MAX = 2000;

function useEditRunning(entry: RunningTimeEntry, onSaved: (saved: RunningTimeEntry) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RunningTimeEntryEditInput) => timeTrackingApi.editRunning(entry.id, payload),
    onSuccess: async (saved) => {
      queryClient.setQueryData(queryKeys.timer.running(entry.user_id), saved);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.timer.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all }),
      ]);
      onSaved(saved);
    },
    onError: (err) => {
      console.error('Timer konnte nicht bearbeitet werden', { entryId: entry.id, err });
    },
  });
}

interface SummaryRowProps {
  label: string;
  value: string;
  actionLabel: string;
  isOpen: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

const SummaryRow: React.FC<SummaryRowProps> = ({ label, value, actionLabel, isOpen, onToggle, children }) => (
  <section className="timer-edit__row" aria-label={label}>
    <div className="timer-edit__summary">
      <div>
        <span className="timer-edit__label">{label}</span>
        <span className="timer-edit__value">{value}</span>
      </div>
      <Button variant="secondary" icon={isOpen ? 'chevron-up' : 'pencil'} aria-expanded={isOpen} onClick={onToggle}>
        {isOpen ? 'Auswahl schließen' : actionLabel}
      </Button>
    </div>
    {isOpen && <div className="timer-edit__picker">{children}</div>}
  </section>
);

export const RunningTimerEditSheet: React.FC<RunningTimerEditSheetProps> = ({ entry, onClose, onSaved }) => {
  const initial = draftFromEntry(entry);
  const [draft, setDraft] = useState<EditDraft>(initial);
  const [activityName, setActivityName] = useState(entry.activity_name ?? `Aktivität #${entry.activity_id}`);
  const [jobName, setJobName] = useState(
    entry.order_title ? `Auftrag #${entry.order_id} – ${entry.order_title}` : `Auftrag #${entry.order_id}`,
  );
  const [openPicker, setOpenPicker] = useState<OpenPicker>(null);
  const [startError, setStartError] = useState<string | undefined>(undefined);
  const mutation = useEditRunning(entry, (saved) => {
    onSaved?.(saved);
    onClose();
  });

  const update = (patch: Partial<EditDraft>) => setDraft((prev) => ({ ...prev, ...patch }));
  const toggle = (picker: Exclude<OpenPicker, null>) => setOpenPicker((prev) => (prev === picker ? null : picker));
  const isDirty = JSON.stringify(draft) !== JSON.stringify(initial);

  const validateStart = (value: string): string | undefined => {
    if (value === initial.startTime) return undefined;
    const resolved = resolveStartTime(value, parseUTC(entry.start_time));
    return 'error' in resolved ? resolved.error : undefined;
  };

  const handleSave = () => {
    const result = buildEditPayload(entry, draft);
    if ('error' in result) {
      setStartError(result.error);
      return;
    }
    setStartError(undefined);
    if (!result.payload) {
      onClose();
      return;
    }
    mutation.mutate(result.payload);
  };

  const serverError = mutation.isError ? getErrorMessage(mutation.error, 'Änderungen konnten nicht gespeichert werden.') : null;

  return (
    <Sheet
      open
      onClose={onClose}
      title="Timer bearbeiten"
      description="Änderungen gelten für den laufenden Timer und werden im Änderungsprotokoll vermerkt."
      isDirty={isDirty && !mutation.isPending}
      footer={
        <>
          <Button variant="secondary" size="lg" onClick={onClose} disabled={mutation.isPending}>
            Abbrechen
          </Button>
          <Button size="lg" icon="check" loading={mutation.isPending} onClick={handleSave}>
            Änderungen speichern
          </Button>
        </>
      }
    >
      <div className="timer-edit">
        {serverError && (
          <p className="timer-error" role="alert">
            {serverError}
          </p>
        )}

        <SummaryRow
          label="Aktivität"
          value={activityName}
          actionLabel="Aktivität ändern"
          isOpen={openPicker === 'activity'}
          onToggle={() => toggle('activity')}
        >
          <ActivityPicker
            onSelectActivity={(activity: Activity) => {
              update({ activityId: activity.id });
              setActivityName(activity.name);
              setOpenPicker(null);
            }}
            onCancel={() => setOpenPicker(null)}
            showTopActivities
          />
        </SummaryRow>

        <SummaryRow
          label="Auftrag"
          value={jobName}
          actionLabel="Auftrag ändern"
          isOpen={openPicker === 'job'}
          onToggle={() => toggle('job')}
        >
          <JobPicker
            selectedOrderId={draft.orderId}
            onSelect={(orderId, label) => {
              update({ orderId });
              setJobName(label);
              setOpenPicker(null);
            }}
          />
        </SummaryRow>

        <SummaryRow
          label="Ort"
          value={draft.location ?? 'Kein Ort'}
          actionLabel="Ort ändern"
          isOpen={openPicker === 'location'}
          onToggle={() => toggle('location')}
        >
          <LocationPicker
            currentLocation={draft.location}
            onSelectLocation={(location: string) => {
              update({ location });
              setOpenPicker(null);
            }}
            onCancel={() => setOpenPicker(null)}
          />
        </SummaryRow>

        <Field
          label="Startzeit"
          name="timer-edit-start"
          error={startError}
          help="Uhrzeit am Tag, an dem der Timer gestartet wurde. Nicht in der Zukunft, höchstens 24 Stunden zurück."
        >
          <input
            type="time"
            value={draft.startTime}
            onChange={(e) => {
              update({ startTime: e.target.value });
              if (startError) setStartError(validateStart(e.target.value));
            }}
            onBlur={(e) => setStartError(validateStart(e.target.value))}
          />
        </Field>

        <Field label="Notiz" name="timer-edit-notes" help={`Höchstens ${NOTES_MAX} Zeichen.`}>
          <textarea
            rows={3}
            maxLength={NOTES_MAX}
            value={draft.notes}
            onChange={(e) => update({ notes: e.target.value })}
          />
        </Field>
      </div>
    </Sheet>
  );
};

export default RunningTimerEditSheet;
