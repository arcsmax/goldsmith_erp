/**
 * CustomerPortalPage — public self-service status lookup (playbook 5.6, W4-03).
 *
 * No login, no staff providers, no query client: the page mounts outside the
 * authenticated shell (App.tsx, FE-01) and makes exactly one request, the
 * lookup. The backend 404s the whole portal router while
 * CUSTOMER_PORTAL_ENABLED is off; a disabled portal therefore reads the same
 * as an unknown reference ("nicht gefunden"), so nothing is enumerable.
 *
 * Customer-facing: formal "Sie", plain language, large type, same tokens as
 * the app, only customer-safe data (see PortalStatusResult).
 */
import React, { useEffect, useState } from 'react';
import { PortalStatusResult, type PortalStatusResponse } from '../components/portal/PortalStatusResult';
import { logError } from '../lib/logError';
import { Button, Field } from '../ui';
import '../styles/portal.css';

/** Fallback name while the workshop-contact fetch is in flight or fails —
 * the real name/phone/email come from the public workshop-contact endpoint
 * (W7 hygiene: this used to be a hardcoded placeholder, "Goldschmiede" /
 * info@goldschmiede.de / +49 0 000 000, that never matched any real shop). */
const FALLBACK_WORKSHOP_NAME = 'Goldschmiede';
const LOOKUP_URL = '/api/v1/portal/lookup';
const WORKSHOP_CONTACT_URL = '/api/v1/portal/workshop-contact';

interface WorkshopContact {
  name: string;
  phone: string | null;
  email: string | null;
}

/** `tel:` hrefs only tolerate digits, leading "+", and a few separators —
 * strip everything else out of a free-text phone number for the href
 * while keeping the original, human-formatted text as the link's label. */
function telHref(phone: string): string {
  return phone.replace(/[^\d+]/g, '');
}

/**
 * LV3-04: `/workshop-contact` sits behind the same
 * `_require_portal_enabled` router dependency as every other portal
 * endpoint (SEC-10/D-03: the whole router 404s while
 * `CUSTOMER_PORTAL_ENABLED` is off). A 404 here is therefore never "no
 * contact configured" (`WorkshopSettingsService.public_contact` always
 * returns a row) — it's the feature-flag signal, an expected state the
 * page should render, not an error to log.
 */
type WorkshopContactResult =
  | { status: 'ok'; contact: WorkshopContact }
  | { status: 'portal_disabled' }
  | { status: 'unavailable' };

async function fetchWorkshopContact(): Promise<WorkshopContactResult> {
  try {
    const response = await fetch(WORKSHOP_CONTACT_URL, {
      // A6: same rule as the lookup request — never send a staff session
      // cookie to a public, logged-out page.
      credentials: 'omit',
    });
    if (response.status === 404) return { status: 'portal_disabled' };
    if (!response.ok) return { status: 'unavailable' };
    return { status: 'ok', contact: (await response.json()) as WorkshopContact };
  } catch (err) {
    logError('CustomerPortalPage.loadWorkshopContact', err);
    return { status: 'unavailable' };
  }
}

const MESSAGES = {
  notFound:
    'Wir haben keinen Auftrag mit dieser Nummer und E-Mail-Adresse gefunden. Bitte prüfen Sie beide Angaben.',
  tooMany: 'Zu viele Anfragen. Bitte warten Sie einen Moment und versuchen Sie es dann erneut.',
  failed: 'Das hat leider nicht geklappt. Bitte versuchen Sie es später noch einmal.',
  offline: 'Keine Verbindung. Bitte prüfen Sie Ihre Internetverbindung.',
  portalDisabled: 'Das Kundenportal ist derzeit nicht aktiv.',
} as const;

type LookupResult = { ok: true; data: PortalStatusResponse } | { ok: false; message: string };

async function lookupStatus(referenceNumber: string, email: string): Promise<LookupResult> {
  const response = await fetch(LOOKUP_URL, {
    method: 'POST',
    // A6: never send auth cookies on this public endpoint. The same-origin
    // default WOULD attach an active staff session cookie — a cross-privilege
    // leak. See docs/fix-plan/2026-04-23/A6-portal-fetch.md.
    credentials: 'omit',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reference_number: referenceNumber.trim(), email: email.trim() }),
  });
  if (response.status === 404) return { ok: false, message: MESSAGES.notFound };
  if (response.status === 429) return { ok: false, message: MESSAGES.tooMany };
  if (!response.ok) return { ok: false, message: MESSAGES.failed };
  return { ok: true, data: (await response.json()) as PortalStatusResponse };
}

export const CustomerPortalPage: React.FC = () => {
  const [referenceNumber, setReferenceNumber] = useState('');
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PortalStatusResponse | null>(null);
  const [contact, setContact] = useState<WorkshopContact | null>(null);
  // null while the feature-flag check is in flight; true/false once known.
  const [isPortalEnabled, setIsPortalEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchWorkshopContact().then((outcome) => {
      if (cancelled) return;
      setIsPortalEnabled(outcome.status !== 'portal_disabled');
      if (outcome.status === 'ok') setContact(outcome.contact);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const outcome = await lookupStatus(referenceNumber, email);
      if (outcome.ok) setResult(outcome.data);
      else setError(outcome.message);
    } catch {
      // Network failure: fetch rejected before any response (no PII logged).
      setError(MESSAGES.offline);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setResult(null);
    setError(null);
    setReferenceNumber('');
    setEmail('');
  };

  const canSubmit = referenceNumber.trim() !== '' && email.trim() !== '';

  return (
    <div className="portal-page">
      <header className="portal-header">
        <p className="portal-workshop-name">{contact?.name || FALLBACK_WORKSHOP_NAME}</p>
        <p className="portal-tagline">Auftragsstatus</p>
      </header>

      <main className="portal-card">
        {isPortalEnabled === false ? (
          <div role="status" aria-labelledby="portal-disabled-title">
            <h1 id="portal-disabled-title" className="portal-form-title">
              Status prüfen
            </h1>
            <p className="portal-form-subtitle">{MESSAGES.portalDisabled}</p>
          </div>
        ) : result ? (
          <PortalStatusResult data={result} onReset={handleReset} />
        ) : (
          <form onSubmit={handleSubmit} noValidate aria-labelledby="portal-form-title">
            <h1 id="portal-form-title" className="portal-form-title">
              Status prüfen
            </h1>
            <p className="portal-form-subtitle">
              Wie weit ist Ihr Schmuckstück? Geben Sie die Nummer von Ihrem Auftragsschein und Ihre E-Mail-Adresse ein.
            </p>

            <Field
              label="Auftragsnummer oder Reparaturnummer"
              name="reference_number"
              required
              help="Zum Beispiel 4287 oder REP-2026-0042."
            >
              <input
                id="portal-ref"
                type="text"
                value={referenceNumber}
                onChange={(e) => setReferenceNumber(e.target.value)}
                autoComplete="off"
                autoCapitalize="characters"
                spellCheck={false}
                disabled={isLoading}
              />
            </Field>

            <Field label="E-Mail-Adresse" name="email" required inputMode="email">
              <input
                id="portal-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                disabled={isLoading}
              />
            </Field>

            {error && (
              <p className="portal-error" role="alert">
                {error}
              </p>
            )}

            <Button type="submit" size="lg" block loading={isLoading} disabled={!canSubmit}>
              {isLoading ? 'Wird gesucht…' : 'Status prüfen'}
            </Button>
          </form>
        )}
      </main>

      <footer className="portal-footer">
        {contact?.email || contact?.phone ? (
          <p>
            Fragen?
            {contact.email && (
              <>
                {' '}
                Schreiben Sie uns an <a href={`mailto:${contact.email}`}>{contact.email}</a>
              </>
            )}
            {contact.email && contact.phone && ' oder rufen Sie uns an: '}
            {!contact.email && contact.phone && ' Rufen Sie uns an: '}
            {contact.phone && <a href={`tel:${telHref(contact.phone)}`}>{contact.phone}</a>}
          </p>
        ) : (
          <p>Fragen? Wenden Sie sich an Ihre Werkstatt.</p>
        )}
      </footer>
    </div>
  );
};

export default CustomerPortalPage;
