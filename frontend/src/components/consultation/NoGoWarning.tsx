// NoGoWarning — debounced No-Go conflict check, embeddable anywhere a form
// collects material/appearance text for a known customer (order intake,
// consultation steps, ...). A warning banner must never break the host
// form: request failures are swallowed into an empty render and logged via
// logError (never a raw console.error — see StyleNoGoStep's comment on why
// PII-bearing request/response bodies must not hit the console).
import React, { useEffect, useState } from 'react';
import { customersApi } from '../../api/customers';
import { NoGoConflict } from '../../types';
import { logError } from '../../lib/logError';

interface NoGoWarningProps {
  customerId?: number | null;
  candidates: string[];
}

const DEBOUNCE_MS = 400;
// Mirrors the backend check-endpoint's own limits (see /customers/{id}/no-gos/check).
// Capping here means a runaway candidates list — e.g. a long free-text
// description — never reaches the API and triggers a 422.
const MAX_CANDIDATES = 50;
const MAX_CANDIDATE_LENGTH = 200;
// Separator used only to build a stable change-detection string key from the
// sanitized candidates array (see candidatesKey below) — never sent anywhere.
const CANDIDATES_KEY_SEPARATOR = '#';

function sanitizeCandidates(candidates: string[]): string[] {
  return candidates
    .map((c) => c.trim())
    .filter((c) => c.length > 0)
    .map((c) => c.slice(0, MAX_CANDIDATE_LENGTH))
    .slice(0, MAX_CANDIDATES);
}

export const NoGoWarning: React.FC<NoGoWarningProps> = ({ customerId, candidates }) => {
  const [conflicts, setConflicts] = useState<NoGoConflict[]>([]);

  const sanitized = sanitizeCandidates(candidates);
  // Content-based key, not the `sanitized` array itself: a new array
  // reference is built every render (candidates is recomputed by the
  // caller on every keystroke), which would reset the debounce timer on
  // every unrelated re-render instead of only when the values actually
  // change.
  const candidatesKey = sanitized.join(CANDIDATES_KEY_SEPARATOR);

  useEffect(() => {
    if (!customerId || sanitized.length === 0) {
      setConflicts([]);
      return;
    }

    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const result = await customersApi.checkNoGoConflicts(customerId, sanitized);
        if (!cancelled) setConflicts(result);
      } catch (err) {
        logError('No-Go-Konflikt-Prüfung fehlgeschlagen', err);
        if (!cancelled) setConflicts([]);
      }
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId, candidatesKey]);

  if (conflicts.length === 0) return null;

  return (
    <div className="no-go-warnings">
      {conflicts.map((conflict) => (
        <div className="no-go-warning-banner" key={conflict.no_go_id}>
          ⚠️ No-Go der Kundin: {conflict.value} ({conflict.matched_against})
        </div>
      ))}
    </div>
  );
};
