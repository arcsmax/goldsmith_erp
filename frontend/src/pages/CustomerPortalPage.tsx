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
import React, { useState } from 'react';
import { PortalStatusResult, type PortalStatusResponse } from '../components/portal/PortalStatusResult';
import { Button, Field } from '../ui';
import '../styles/portal.css';

/** Shown until workshop branding is available to logged-out visitors (open item). */
const WORKSHOP_NAME = 'Goldschmiede';
const LOOKUP_URL = '/api/v1/portal/lookup';

const MESSAGES = {
  notFound:
    'Wir haben keinen Auftrag mit dieser Nummer und E-Mail-Adresse gefunden. Bitte prüfen Sie beide Angaben.',
  tooMany: 'Zu viele Anfragen. Bitte warten Sie einen Moment und versuchen Sie es dann erneut.',
  failed: 'Das hat leider nicht geklappt. Bitte versuchen Sie es später noch einmal.',
  offline: 'Keine Verbindung. Bitte prüfen Sie Ihre Internetverbindung.',
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
        <p className="portal-workshop-name">{WORKSHOP_NAME}</p>
        <p className="portal-tagline">Auftragsstatus</p>
      </header>

      <main className="portal-card">
        {result ? (
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
        <p>
          Fragen? Schreiben Sie uns an{' '}
          <a href="mailto:info@goldschmiede.de">info@goldschmiede.de</a> oder rufen Sie uns an:{' '}
          <a href="tel:+4900000000">+49 0 000 000</a>
        </p>
      </footer>
    </div>
  );
};

export default CustomerPortalPage;
