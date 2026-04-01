/**
 * CustomerPortalPage
 *
 * Public self-service page — no login required.
 * Customers enter their order/repair reference number and email address
 * to check the current status of their piece.
 *
 * Design: glass morphism card on dark gradient background.
 * Mobile-first: every interactive element meets the 44×44px touch target minimum.
 */

import React, { useState } from 'react';
import '../styles/portal.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface PortalStatusResponse {
  reference_number: string;
  record_type: 'order' | 'repair';
  status_key: string;
  status_label: string;
  item_title: string;
  current_step: number;
  total_steps: number;
  step_label: string;
  pipeline_labels: string[];
  estimated_completion: string | null;
  is_complete: boolean;
  lookup_token?: string;
}

// ── Badge helpers ──────────────────────────────────────────────────────────────

function getBadgeClass(statusKey: string, isComplete: boolean): string {
  if (statusKey === 'cancelled') return 'portal-status-badge portal-status-badge--cancelled';
  if (isComplete) return 'portal-status-badge portal-status-badge--complete';
  if (
    statusKey === 'waiting_for_fitting' ||
    statusKey === 'quoted' ||
    statusKey === 'approved'
  ) return 'portal-status-badge portal-status-badge--waiting';
  return 'portal-status-badge portal-status-badge--in-progress';
}

function getProgressClass(isComplete: boolean): string {
  return isComplete
    ? 'portal-progress-fill portal-progress-fill--complete'
    : 'portal-progress-fill';
}

function getDotClass(dotIndex: number, currentStep: number, isComplete: boolean): string {
  // dotIndex is 0-based, currentStep is 1-based
  if (isComplete) return 'portal-step-dot portal-step-dot--done-complete';
  if (dotIndex < currentStep - 1) return 'portal-step-dot portal-step-dot--done';
  if (dotIndex === currentStep - 1) return 'portal-step-dot portal-step-dot--current';
  return 'portal-step-dot';
}

// ── Diamond ring SVG icon ─────────────────────────────────────────────────────

const RingIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M8.5 3h7l1.5 4H7L8.5 3zm-1.6 5h10.2l-5.1 9L6.9 8zM12 10l-3 5.3A7 7 0 1 0 12 10zm0 2a5 5 0 1 1 0 10A5 5 0 0 1 12 12z"/>
  </svg>
);

// ── Sub-components ────────────────────────────────────────────────────────────

interface StatusResultProps {
  data: PortalStatusResponse;
  onReset: () => void;
}

const StatusResult: React.FC<StatusResultProps> = ({ data, onReset }) => {
  const progressPercent =
    data.total_steps > 0
      ? Math.round((Math.max(0, data.current_step) / data.total_steps) * 100)
      : 0;

  const recordTypeLabel = data.record_type === 'repair' ? 'Reparatur' : 'Auftrag';

  return (
    <div className="portal-result">
      <button className="portal-back-btn" onClick={onReset} type="button">
        ← Neue Suche
      </button>

      <div className="portal-result-header">
        <div>
          <div className="portal-ref-number">
            {recordTypeLabel} {data.reference_number}
          </div>
          <div className="portal-item-title">{data.item_title}</div>
        </div>
        <span className={getBadgeClass(data.status_key, data.is_complete)}>
          <span className="portal-status-badge-dot" aria-hidden="true" />
          {data.status_label}
        </span>
      </div>

      {/* Progress bar */}
      <div className="portal-progress-section" role="status" aria-label={`Schritt ${data.current_step} von ${data.total_steps}: ${data.step_label}`}>
        <div className="portal-step-info">
          <span className="portal-step-text">
            {data.current_step > 0
              ? `Schritt ${data.current_step} von ${data.total_steps}`
              : 'Storniert'}
          </span>
          <span className="portal-step-label">{data.step_label}</span>
        </div>

        <div className="portal-progress-track" role="progressbar" aria-valuenow={progressPercent} aria-valuemin={0} aria-valuemax={100}>
          <div
            className={getProgressClass(data.is_complete)}
            style={{ width: `${progressPercent}%` }}
          />
        </div>

        <div className="portal-steps-row" aria-hidden="true">
          {data.pipeline_labels.map((_, i) => (
            <div
              key={i}
              className={getDotClass(i, data.current_step, data.is_complete)}
              title={data.pipeline_labels[i]}
            />
          ))}
        </div>
      </div>

      {/* Detail rows */}
      <div className="portal-details">
        <div className="portal-detail-row">
          <span className="portal-detail-icon" aria-hidden="true">
            {data.record_type === 'repair' ? '🔧' : '💍'}
          </span>
          <span className="portal-detail-label">Typ</span>
          <span className="portal-detail-value">{recordTypeLabel}</span>
        </div>

        <div className="portal-detail-row">
          <span className="portal-detail-icon" aria-hidden="true">📋</span>
          <span className="portal-detail-label">Status</span>
          <span className="portal-detail-value">{data.status_label}</span>
        </div>

        {data.estimated_completion && (
          <div className="portal-detail-row">
            <span className="portal-detail-icon" aria-hidden="true">📅</span>
            <span className="portal-detail-label">Voraussichtlich fertig</span>
            <span className="portal-detail-value">{data.estimated_completion}</span>
          </div>
        )}

        {data.is_complete && data.status_key !== 'cancelled' && (
          <div className="portal-detail-row">
            <span className="portal-detail-icon" aria-hidden="true">✅</span>
            <span className="portal-detail-label">Bereit zur Abholung</span>
            <span className="portal-detail-value" style={{ color: '#4ade80' }}>
              Ihr Stueck wartet auf Sie
            </span>
          </div>
        )}
      </div>

      {/* Contact footer */}
      <div className="portal-contact-footer">
        Bei Fragen kontaktieren Sie uns gerne:{' '}
        <a href="mailto:info@goldschmiede.de">info@goldschmiede.de</a>
        {' '}oder telefonisch unter{' '}
        <a href="tel:+4900000000">+49 0 000 000</a>
      </div>
    </div>
  );
};

// ── Main page component ───────────────────────────────────────────────────────

export const CustomerPortalPage: React.FC = () => {
  const [referenceNumber, setReferenceNumber] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PortalStatusResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const response = await fetch('/api/v1/portal/lookup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reference_number: referenceNumber.trim(),
          email: email.trim(),
        }),
      });

      if (response.status === 404) {
        setError(
          'Auftrag nicht gefunden. Bitte pruefen Sie Ihre Auftragsnummer und E-Mail-Adresse.'
        );
        return;
      }

      if (response.status === 429) {
        setError(
          'Zu viele Anfragen. Bitte warten Sie kurz und versuchen Sie es erneut.'
        );
        return;
      }

      if (!response.ok) {
        setError('Ein Fehler ist aufgetreten. Bitte versuchen Sie es spaeter erneut.');
        return;
      }

      const data: PortalStatusResponse = await response.json();
      setResult(data);
    } catch {
      setError(
        'Verbindung zum Server nicht moeglich. Bitte pruefen Sie Ihre Internetverbindung.'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setResult(null);
    setError(null);
    setReferenceNumber('');
    setEmail('');
  };

  return (
    <main className="portal-page">
      {/* Branding header */}
      <header className="portal-header">
        <div className="portal-brand-mark" aria-hidden="true">
          <RingIcon />
        </div>
        <div className="portal-workshop-name">Goldschmiede</div>
        <div className="portal-tagline">Auftragsstatus prüfen</div>
      </header>

      {/* Glass card */}
      <div className="portal-card" role="region" aria-label="Auftragssuche">
        {result ? (
          <StatusResult data={result} onReset={handleReset} />
        ) : (
          <form onSubmit={handleSubmit} noValidate>
            <h1 className="portal-form-title">Status prüfen</h1>
            <p className="portal-form-subtitle">
              Geben Sie Ihre Auftragsnummer oder Reparaturnummer sowie Ihre E-Mail-Adresse ein.
            </p>

            <div className="portal-field">
              <label htmlFor="portal-ref" className="portal-label">
                Auftragsnummer oder Reparaturnummer
              </label>
              <input
                id="portal-ref"
                className="portal-input"
                type="text"
                value={referenceNumber}
                onChange={(e) => setReferenceNumber(e.target.value)}
                placeholder="z.B. 4287 oder REP-2026-0042"
                autoComplete="off"
                autoCapitalize="characters"
                spellCheck={false}
                required
                disabled={loading}
                aria-required="true"
              />
            </div>

            <div className="portal-field">
              <label htmlFor="portal-email" className="portal-label">
                E-Mail-Adresse
              </label>
              <input
                id="portal-email"
                className="portal-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="ihre@email.de"
                autoComplete="email"
                required
                disabled={loading}
                aria-required="true"
                inputMode="email"
              />
            </div>

            {error && (
              <div className="portal-error" role="alert" aria-live="assertive">
                <span className="portal-error-icon" aria-hidden="true">⚠</span>
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              className="portal-submit-btn"
              disabled={loading || !referenceNumber.trim() || !email.trim()}
              aria-busy={loading}
            >
              {loading ? (
                <>
                  <span className="portal-spinner" aria-hidden="true" />
                  Suche...
                </>
              ) : (
                'Status prüfen'
              )}
            </button>
          </form>
        )}
      </div>

      <footer className="portal-footer">
        Goldschmied ERP &mdash; Kundenstatus-Portal
      </footer>
    </main>
  );
};

export default CustomerPortalPage;
