// ConsentPanel — GDPR-02 / GDPR-11 "Einwilligungen" block for the customer
// detail page. Lists every consent record (active + revoked) with grant /
// revoke actions for ADMIN and GOLDSMITH. Mirrors the role-gating pattern of
// CostChangeSection.tsx: the backend's CONSENT_MANAGE permission is only
// granted to those two roles, so the panel skips the fetch entirely (and
// renders nothing) for anyone else rather than surface a 403.
//
// W6: the "Keine E-Mail-Updates" switch records the Art. 21 objection
// (stored server-side as a revoked "E-Mail-Kontakt" consent). While it is on,
// Kundeninfos go out only as PDF for manual hand-over.
import React, { useCallback, useEffect, useState } from 'react';
import { useAuth, useConfirm, useToast } from '../../contexts';
import { logError } from '../../lib/logError';
import { ToggleSetting } from '../ToggleSetting';
import {
  CONSENT_METHOD_LABELS,
  CONSENT_PURPOSES,
  CONSENT_PURPOSE_LABELS,
  ConsentMethod,
  ConsentPurpose,
  ConsentRecord,
  consentsApi,
  extractErrorDetail,
} from '../../api/consents';
import '../../styles/customer-detail.css';
// Pulls .form-group/.form-row/.checkbox-group/.modal-footer used by the
// inline "grant a consent" form below — customer-detail.css only defines a
// scoped .cdetail-masse-form variant of those classes.
import '../../styles/customers.css';

interface ConsentPanelProps {
  customerId: number;
}

const formatDateTime = (iso: string): string => new Date(iso).toLocaleString('de-DE');

export const ConsentPanel: React.FC<ConsentPanelProps> = ({ customerId }) => {
  const { hasRole } = useAuth();
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const canManage = hasRole(['ADMIN', 'GOLDSMITH']);

  const [consents, setConsents] = useState<ConsentRecord[]>([]);
  const [isLoading, setIsLoading] = useState(canManage);
  const [actionPurpose, setActionPurpose] = useState<ConsentPurpose | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [newPurpose, setNewPurpose] = useState<ConsentPurpose>('health_data');
  const [newMethod, setNewMethod] = useState<ConsentMethod>('in_person');
  const [newNote, setNewNote] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [emailOptOut, setEmailOptOut] = useState<boolean | null>(null);
  const [isSavingOptOut, setIsSavingOptOut] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await consentsApi.list(customerId);
      setConsents(data);
    } catch (err) {
      logError('ConsentPanel.load', err);
      showToast('Einwilligungen konnten nicht geladen werden.', 'error');
    } finally {
      setIsLoading(false);
    }
  }, [customerId, showToast]);

  // Loaded on its own: a failure hides only the switch, never the consents.
  const loadOptOut = useCallback(async () => {
    try {
      setEmailOptOut(await consentsApi.getEmailOptOut(customerId));
    } catch (err) {
      logError('ConsentPanel.loadEmailOptOut', err);
      setEmailOptOut(null);
    }
  }, [customerId]);

  useEffect(() => {
    if (!canManage) {
      setConsents([]);
      setIsLoading(false);
      return;
    }
    void load();
    void loadOptOut();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId, canManage]);

  if (!canManage) return null;

  const activePurposes = new Set(
    consents.filter((c) => !c.revoked_at).map((c) => c.purpose)
  );
  const grantablePurposes = CONSENT_PURPOSES.filter((p) => !activePurposes.has(p));

  const handleRevoke = async (consent: ConsentRecord) => {
    if (actionPurpose) return;
    const label = CONSENT_PURPOSE_LABELS[consent.purpose];
    const confirmed = await showConfirm({
      title: 'Einwilligung widerrufen',
      message: `Möchten Sie die Einwilligung „${label}“ wirklich widerrufen?`,
      confirmLabel: 'Widerrufen',
      variant: 'danger',
    });
    if (!confirmed) return;

    setActionPurpose(consent.purpose);
    try {
      await consentsApi.revoke(customerId, consent.purpose);
      showToast(`Einwilligung „${label}“ wurde widerrufen.`, 'success');
      await load();
    } catch (err) {
      logError('ConsentPanel.revoke', err);
      showToast(
        extractErrorDetail(err) ?? 'Einwilligung konnte nicht widerrufen werden.',
        'error'
      );
    } finally {
      setActionPurpose(null);
    }
  };

  const handleOptOutChange = async (optedOut: boolean) => {
    if (isSavingOptOut) return;
    setIsSavingOptOut(true);
    try {
      const saved = await consentsApi.setEmailOptOut(customerId, optedOut);
      setEmailOptOut(saved);
      showToast(
        saved ? 'Keine E-Mail-Updates gespeichert.' : 'E-Mail-Updates wieder erlaubt.',
        'success'
      );
      await load();
    } catch (err) {
      logError('ConsentPanel.setEmailOptOut', err);
      showToast(
        extractErrorDetail(err) ?? 'Widerspruch konnte nicht gespeichert werden.',
        'error'
      );
    } finally {
      setIsSavingOptOut(false);
    }
  };

  const handleGrant = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setActionPurpose(newPurpose);
    try {
      await consentsApi.grant(customerId, {
        purpose: newPurpose,
        method: newMethod,
        note: newNote.trim() || undefined,
      });
      showToast(`Einwilligung „${CONSENT_PURPOSE_LABELS[newPurpose]}“ wurde erfasst.`, 'success');
      setIsFormOpen(false);
      setNewNote('');
      await load();
    } catch (err) {
      logError('ConsentPanel.grant', err);
      setFormError(extractErrorDetail(err) ?? 'Einwilligung konnte nicht gespeichert werden.');
    } finally {
      setActionPurpose(null);
    }
  };

  return (
    <section className="cdetail-section cdetail-section--full">
      <h3 className="cdetail-section__title">Einwilligungen</h3>

      {emailOptOut !== null && (
        // LV3-05: reuse the shared ToggleSetting primitive (already used by
        // the Werkbank-Modus setting) instead of a bare, unstyled
        // <input type="checkbox"> — label and Art. 21 help text stack
        // properly and the control keeps a real touch target.
        <ToggleSetting
          id="consent-email-opt-out"
          label="Keine E-Mail-Updates"
          description="Widerspruch nach Art. 21 DSGVO: Kundeninfos werden dann nur als PDF zur Übergabe erstellt."
          checked={emailOptOut}
          onChange={(next) => void handleOptOutChange(next)}
          disabled={isSavingOptOut}
        />
      )}

      {isLoading ? (
        <p>Lade Einwilligungen…</p>
      ) : consents.length === 0 ? (
        <div className="cdetail-empty">
          <p>Noch keine Einwilligungen erfasst.</p>
        </div>
      ) : (
        <dl className="cdetail-dl">
          {consents.map((c) => (
            <React.Fragment key={c.id}>
              <dt>{CONSENT_PURPOSE_LABELS[c.purpose]}</dt>
              <dd>
                {c.revoked_at ? (
                  <span>
                    Widerrufen am {formatDateTime(c.revoked_at)} (erteilt{' '}
                    {formatDateTime(c.granted_at)}, {CONSENT_METHOD_LABELS[c.method]})
                  </span>
                ) : (
                  <>
                    <span>
                      Erteilt am {formatDateTime(c.granted_at)} ({CONSENT_METHOD_LABELS[c.method]})
                    </span>{' '}
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => handleRevoke(c)}
                      disabled={actionPurpose === c.purpose}
                    >
                      {actionPurpose === c.purpose ? 'Wird widerrufen…' : 'Einwilligung widerrufen'}
                    </button>
                  </>
                )}
              </dd>
            </React.Fragment>
          ))}
        </dl>
      )}

      {isFormOpen ? (
        <form className="cdetail-panel tab-panel" onSubmit={handleGrant}>
          {formError && <div className="cdetail-error">{formError}</div>}
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="consent-purpose">Zweck</label>
              <select
                id="consent-purpose"
                value={newPurpose}
                onChange={(e) => setNewPurpose(e.target.value as ConsentPurpose)}
                disabled={actionPurpose !== null}
              >
                {grantablePurposes.map((p) => (
                  <option key={p} value={p}>
                    {CONSENT_PURPOSE_LABELS[p]}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="consent-method">Methode</label>
              <select
                id="consent-method"
                value={newMethod}
                onChange={(e) => setNewMethod(e.target.value as ConsentMethod)}
                disabled={actionPurpose !== null}
              >
                {(Object.keys(CONSENT_METHOD_LABELS) as ConsentMethod[]).map((m) => (
                  <option key={m} value={m}>
                    {CONSENT_METHOD_LABELS[m]}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="consent-note">Notiz (optional)</label>
            <input
              type="text"
              id="consent-note"
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
              disabled={actionPurpose !== null}
              maxLength={500}
              placeholder="z. B. Bogen v1"
            />
          </div>
          <div className="modal-footer">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setIsFormOpen(false)}
              disabled={actionPurpose !== null}
            >
              Abbrechen
            </button>
            <button type="submit" className="btn-primary" disabled={actionPurpose !== null}>
              {actionPurpose !== null ? 'Speichern…' : 'Einwilligung speichern'}
            </button>
          </div>
        </form>
      ) : (
        grantablePurposes.length > 0 && (
          <button type="button" className="btn-secondary" onClick={() => setIsFormOpen(true)}>
            Einwilligung erfassen
          </button>
        )
      )}
    </section>
  );
};
