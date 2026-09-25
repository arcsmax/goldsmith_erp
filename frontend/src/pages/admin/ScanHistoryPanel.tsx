// Scan-Verlauf search across pieces and users (ADMIN / GOLDSMITH; scan
// tracking, 2026-09 audit, SC-03). "Where is ring 42?" → type ORDER:42, the
// order number, a repair or bag number, or any scanned text; optionally a
// time window. Every row links to the piece.
//
// Data: scanHistorySearchQuery (GET /scan/history), refreshed live by the
// `scan_updates` hint. The backend refuses VIEWER; the caller mounts this
// panel only for ADMIN / GOLDSMITH.
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { usersApi } from '../../api';
import { scanHistorySearchQuery, type ScanHistoryRow } from '../../api/scanner';
import { queryKeys, type ScanHistorySearchParams } from '../../api/queryKeys';
import { describeActionId, formatScanTime } from '../../components/scanner/scanHistory';
import { useOptionalAuth } from '../../contexts/AuthContext';
import { getErrorMessage } from '../../lib/errors';
import { canAdministerSystem } from '../../lib/roles';
import { Button, Card, EmptyState, Field, PageState, type PageStateValue } from '../../ui';
import '../../styles/components/ScanTracking.css';

const PAGE_SIZE = 25;
// GET /users/ requires Permission.USER_VIEW, which only ADMIN holds
// (core/permissions.py ROLE_PERMISSIONS) — GOLDSMITH, who can also open
// this panel, would 403. The dropdown is ADMIN-only; GOLDSMITH keeps the
// free-text "Nummer oder Code" search.
const USER_LIST_LIMIT = 100;

interface SearchForm {
  q: string;
  /** Selected user id as a string ('' = alle Mitarbeiter:innen), because
   *  <select> values are always strings. */
  user: string;
  from: string;
  to: string;
}

const EMPTY_FORM: SearchForm = { q: '', user: '', from: '', to: '' };

/** Local date input (YYYY-MM-DD) → ISO bounds of that day. */
function dayStart(value: string): string | undefined {
  return value ? new Date(`${value}T00:00:00`).toISOString() : undefined;
}

function dayEnd(value: string): string | undefined {
  return value ? new Date(`${value}T23:59:59.999`).toISOString() : undefined;
}

export function toSearchParams(form: SearchForm, offset: number): ScanHistorySearchParams {
  const q = form.q.trim();
  const userId = form.user.trim() === '' ? null : Number(form.user);
  return {
    ...(q ? { q } : {}),
    ...(userId !== null && Number.isFinite(userId) ? { user: userId } : {}),
    ...(form.from ? { from: dayStart(form.from) } : {}),
    ...(form.to ? { to: dayEnd(form.to) } : {}),
    limit: PAGE_SIZE,
    offset,
  };
}

/** Display label for a staff user in the filter dropdown: full name, falling
 *  back to email when either name part is missing (mirrors MainLayout's
 *  header displayName pattern). */
function userDisplayName(user: { first_name?: string | null; last_name?: string | null; email: string }): string {
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ').trim();
  return name.length > 0 ? name : user.email;
}

function pieceLink(row: ScanHistoryRow): string | null {
  if (!row.resolved_id) return null;
  if (row.resolved_type === 'order') return `/orders/${row.resolved_id}`;
  if (row.resolved_type === 'repair') return `/repairs/${row.resolved_id}`;
  return null;
}

const HistoryRow: React.FC<{ row: ScanHistoryRow }> = ({ row }) => {
  const link = pieceLink(row);
  const piece = row.resolved_type ? `${row.resolved_type.toUpperCase()}:${row.resolved_id}` : row.raw_payload;
  return (
    <li className="piece-scan-row" data-testid={`scan-history-row-${row.id}`}>
      <span className="piece-scan-row__action">
        {link !== null ? <Link to={link}>{piece}</Link> : piece}
        {' · '}
        {describeActionId(row.action_taken, row.action_result)}
      </span>
      <span className="piece-scan-row__meta">
        <time dateTime={row.scanned_at} className="piece-scan-row__time">
          {formatScanTime(row.scanned_at)}
        </time>
        {' · '}
        {row.user_name}
        {' · '}
        {row.location ?? 'Standort unbekannt'}
      </span>
    </li>
  );
};

export const ScanHistoryPanel: React.FC = () => {
  const [form, setForm] = useState<SearchForm>(EMPTY_FORM);
  const [submitted, setSubmitted] = useState<SearchForm>(EMPTY_FORM);
  const [offset, setOffset] = useState(0);
  const query = useQuery(scanHistorySearchQuery(toSearchParams(submitted, offset)));

  const auth = useOptionalAuth();
  const isAdmin = canAdministerSystem(auth?.user?.role);
  // Dropdown of staff users (SC-03 follow-up): the search API already
  // supports `user=`, this just surfaces it instead of requiring a
  // memorised id. ADMIN only (see USER_LIST_LIMIT comment above).
  const usersQuery = useQuery({
    queryKey: queryKeys.users.list(0, USER_LIST_LIMIT),
    queryFn: () => usersApi.getAll(0, USER_LIST_LIMIT),
    enabled: isAdmin,
  });
  const staffUsers = [...(usersQuery.data ?? [])].sort((a, b) =>
    userDisplayName(a).localeCompare(userDisplayName(b), 'de'),
  );

  const submit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setSubmitted(form);
    setOffset(0);
  };

  const update =
    (key: keyof SearchForm) =>
    (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value }));

  const renderResults = (): React.ReactNode => {
    if (!query.data) {
      const state: PageStateValue = query.isError
        ? {
            status: 'error',
            error: getErrorMessage(query.error, 'Scan-Verlauf konnte nicht geladen werden.'),
            retry: () => void query.refetch(),
          }
        : { status: 'loading' };
      return <PageState state={state} skeleton="list" skeletonCount={3} />;
    }
    if (query.data.items.length === 0) {
      return (
        <EmptyState
          icon="scan"
          title="Keine Scans gefunden"
          body="Andere Nummer oder einen größeren Zeitraum versuchen."
          headingLevel={3}
          action={
            <Button variant="secondary" onClick={() => { setForm(EMPTY_FORM); setSubmitted(EMPTY_FORM); setOffset(0); }}>
              Suche zurücksetzen
            </Button>
          }
        />
      );
    }
    const { items, total, next_offset: nextOffset } = query.data;
    return (
      <>
        <p className="scan-history-panel__total" role="status">
          {total} Scans
        </p>
        <ul className="piece-scan-list" data-testid="scan-history-results">
          {items.map((row) => (
            <HistoryRow key={row.id} row={row} />
          ))}
        </ul>
        <div className="scan-history-panel__paging">
          {offset > 0 && (
            <Button variant="secondary" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Neuere Scans
            </Button>
          )}
          {nextOffset !== null && nextOffset !== undefined && (
            <Button variant="secondary" onClick={() => setOffset(nextOffset)}>
              Ältere Scans
            </Button>
          )}
        </div>
      </>
    );
  };

  return (
    <Card title="Scan-Verlauf durchsuchen" className="scan-history-panel">
      <form className="scan-history-panel__form" onSubmit={submit} data-testid="scan-history-form">
        <Field
          label="Nummer oder Code"
          name="scan-history-q"
          help="z. B. ORDER:42, 42, R-2026-0001 oder Tütennummer"
        >
          <input id="scan-history-q" type="search" value={form.q} onChange={update('q')} />
        </Field>
        {isAdmin && (
          <Field label="Mitarbeiter:in" name="scan-history-user">
            <select
              id="scan-history-user"
              value={form.user}
              onChange={update('user')}
              disabled={usersQuery.isPending}
              data-testid="scan-history-user-select"
            >
              <option value="">Alle Mitarbeiter:innen</option>
              {staffUsers.map((user) => (
                <option key={user.id} value={user.id}>
                  {userDisplayName(user)}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Von" name="scan-history-from">
          <input id="scan-history-from" type="date" value={form.from} onChange={update('from')} />
        </Field>
        <Field label="Bis" name="scan-history-to">
          <input id="scan-history-to" type="date" value={form.to} onChange={update('to')} />
        </Field>
        <Button type="submit" icon="search" size="lg">
          Scans suchen
        </Button>
      </form>
      {renderResults()}
    </Card>
  );
};

export default ScanHistoryPanel;
