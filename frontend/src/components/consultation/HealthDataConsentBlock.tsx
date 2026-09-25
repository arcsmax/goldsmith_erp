// HealthDataConsentBlock — "Einwilligung Gesundheitsdaten" gate for the
// No-Go step's allergy chips (see StyleNoGoStep.tsx).
//
// Allergies are Art. 9 health data (GDPR-02 / GDPR-11): the backend rejects
// an ALLERGY no-go with 422 until an active HEALTH_DATA consent exists for
// the customer (services/consent_service.py, api/routers/customers.py —
// create_customer_no_go). Before this block existed, the wizard let a
// goldsmith tap a "Schnellauswahl Allergien" chip straight into that 422,
// surfaced only as a generic "No-Go konnte nicht angelegt werden" toast.
//
// This mirrors ConsentPanel.tsx's grant form (method + note), scoped to the
// one HEALTH_DATA purpose so the wizard doesn't need the full multi-purpose
// panel. The parent (StyleNoGoStep) owns the consent list fetch and passes
// the active record down; this component only renders the granted/pending
// state and performs the grant.
import React, { useState } from 'react';
import { Button, Field } from '../../ui';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import {
  CONSENT_METHOD_LABELS,
  ConsentMethod,
  ConsentRecord,
  consentsApi,
} from '../../api/consents';

export interface HealthDataConsentBlockProps {
  customerId: number;
  /** The customer's active HEALTH_DATA consent, or null if none exists yet. */
  consent: ConsentRecord | null;
  /** Called with the newly granted consent record right after the POST succeeds. */
  onGranted: (consent: ConsentRecord) => void;
}

const formatDateTime = (iso: string): string => new Date(iso).toLocaleString('de-DE');

export const HealthDataConsentBlock: React.FC<HealthDataConsentBlockProps> = ({
  customerId,
  consent,
  onGranted,
}) => {
  const [method, setMethod] = useState<ConsentMethod>('in_person');
  const [note, setNote] = useState('');
  const [isGranting, setIsGranting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGrant = async () => {
    setIsGranting(true);
    setError(null);
    try {
      const granted = await consentsApi.grant(customerId, {
        purpose: 'health_data',
        method,
        note: note.trim() || undefined,
      });
      onGranted(granted);
      setNote('');
    } catch (err) {
      logError('HealthDataConsentBlock.grant', err);
      setError(getErrorMessage(err, 'Einwilligung konnte nicht gespeichert werden.'));
    } finally {
      setIsGranting(false);
    }
  };

  if (consent) {
    return (
      <div className="wizard-field consent-block consent-block--granted">
        <span className="ui-field__label">Einwilligung Gesundheitsdaten</span>
        <p className="field-hint">
          Erteilt am {formatDateTime(consent.granted_at)} ({CONSENT_METHOD_LABELS[consent.method]})
        </p>
      </div>
    );
  }

  return (
    <div className="wizard-field consent-block consent-block--pending">
      <span className="ui-field__label">Einwilligung Gesundheitsdaten</span>
      <p className="field-hint">
        Allergien sind Gesundheitsdaten (Art. 9 DSGVO) und dürfen nur mit
        ausdrücklicher Einwilligung der Kundin/des Kunden gespeichert werden.
        Bitte zuerst hier bestätigen, bevor Allergie-No-Gos angelegt werden
        können.
      </p>
      {error && <p className="consent-block__error">{error}</p>}
      <div className="wizard-field-row">
        <Field label="Methode" name="health_consent_method">
          <select
            id="health_consent_method"
            value={method}
            onChange={(e) => setMethod(e.target.value as ConsentMethod)}
            disabled={isGranting}
          >
            {(Object.keys(CONSENT_METHOD_LABELS) as ConsentMethod[]).map((m) => (
              <option key={m} value={m}>
                {CONSENT_METHOD_LABELS[m]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Notiz" name="health_consent_note" help="Optional">
          <input
            id="health_consent_note"
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            disabled={isGranting}
            maxLength={500}
          />
        </Field>
      </div>
      <Button type="button" variant="secondary" onClick={() => void handleGrant()} loading={isGranting}>
        Einwilligung bestätigen
      </Button>
    </div>
  );
};
