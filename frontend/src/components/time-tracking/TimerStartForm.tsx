// TimerStartForm — "Zeiterfassung starten" panel of the TimerWidget (W4-03).
//
// Orders and activities come from shared queries (orderPickerQuery shares
// the dashboard's order list; activitiesQuery the context's). Mounted only
// while the panel is open, so the collapsed FAB never fetches.
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { activitiesQuery, orderPickerQuery } from '../../api/timeTrackingQueries';
import { timeTrackingApi } from '../../api/time-tracking';
import { getDeviceLocationId, setDeviceLocationId } from '../../lib/deviceLocation';
import { getErrorMessage } from '../../lib/errors';
import { Button, Field, IconButton } from '../../ui';
import { LocationPicker } from '../LocationPicker';

export interface TimerStartFormProps {
  onClose: () => void;
  /** Called after a successful start (or when one was already running). */
  onStarted: () => void;
}

function isAlreadyRunning(err: unknown): boolean {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' && (detail.includes('bereits eine laufende') || detail.includes('already'));
}

export const TimerStartForm: React.FC<TimerStartFormProps> = ({ onClose, onStarted }) => {
  const orders = useQuery(orderPickerQuery());
  const activities = useQuery(activitiesQuery(false));
  const [orderId, setOrderId] = useState<number | null>(null);
  const [activityId, setActivityId] = useState<number | null>(null);
  // Preselect the device's remembered Standort; the goldsmith just confirms it.
  const [locationId, setLocationId] = useState<number | null>(() => getDeviceLocationId());
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadError =
    orders.isError || activities.isError
      ? 'Aufträge oder Aktivitäten konnten nicht geladen werden.'
      : null;

  const handleStart = async () => {
    if (!orderId || !activityId) return;
    setIsStarting(true);
    setError(null);
    try {
      await timeTrackingApi.start({
        order_id: orderId,
        activity_id: activityId,
        location_id: locationId ?? undefined,
      });
      // Remember this device's Standort for next time (or forget it if cleared).
      setDeviceLocationId(locationId);
      onStarted();
    } catch (err) {
      if (isAlreadyRunning(err)) {
        onStarted();
        return;
      }
      console.error('Timer konnte nicht gestartet werden', { orderId, activityId, err });
      setError(getErrorMessage(err, 'Timer konnte nicht gestartet werden'));
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <section className="timer-widget timer-widget--start-form" aria-labelledby="timer-start-title">
      <div className="timer-header-row">
        <h3 id="timer-start-title">Zeiterfassung starten</h3>
        <IconButton icon="close" label="Schließen" onClick={onClose} />
      </div>

      {(error ?? loadError) && (
        <p className="timer-error" role="alert">
          {error ?? loadError}
        </p>
      )}

      <div className="timer-start-form">
        <Field label="Auftrag" name="timer-order-select">
          <select
            id="timer-order-select"
            value={orderId ?? ''}
            onChange={(e) => setOrderId(Number(e.target.value) || null)}
            disabled={orders.isPending}
          >
            <option value="">{orders.isPending ? 'Wird geladen…' : 'Auftrag wählen'}</option>
            {(orders.data ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                #{o.id} – {o.title}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Aktivität" name="timer-activity-select">
          <select
            id="timer-activity-select"
            value={activityId ?? ''}
            onChange={(e) => setActivityId(Number(e.target.value) || null)}
            disabled={activities.isPending}
          >
            <option value="">{activities.isPending ? 'Wird geladen…' : 'Aktivität wählen'}</option>
            {(activities.data ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </Field>

        <LocationPicker value={locationId} onChange={(location) => setLocationId(location?.id ?? null)} />

        <Button
          size="lg"
          block
          icon="clock"
          loading={isStarting}
          disabled={!orderId || !activityId}
          onClick={() => void handleStart()}
        >
          Timer starten
        </Button>
      </div>
    </section>
  );
};

export default TimerStartForm;
