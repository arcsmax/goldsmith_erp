// Nachrichten-Warteschlange (ARCH-04 / ARCH-12): customer mails the worker
// could not deliver. "Fehlgeschlagen" rows are retried automatically with
// backoff; "Aufgegeben" rows wait for an admin. Both can be sent again here.
// ADMIN only (the page is ADMIN-gated; the backend enforces OUTBOX_MANAGE).
// Shows ids and error codes only — never recipient, subject or body.
import React, { useCallback, useEffect, useState } from 'react';
import { OutboxList, OutboxMessage, getOutbox, retryOutboxMessage } from '../../api/admin';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { Button, DataTable, type Column, type PageStateValue } from '../../ui';

const KIND_LABELS: Record<string, string> = {
  customer_update: 'Kundeninfo',
  quote_email: 'Kostenvoranschlag',
};

const formatDateTime = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString('de-DE') : '—';

const targetOf = (m: OutboxMessage): string => {
  const p = m.payload as Record<string, unknown>;
  if (p.update_id != null) return `Kundeninfo #${String(p.update_id)}`;
  if (p.quote_id != null) return `Kostenvoranschlag #${String(p.quote_id)}`;
  return '—';
};

export const OutboxQueueSection: React.FC = () => {
  const [failed, setFailed] = useState<OutboxList | null>(null);
  const [dead, setDead] = useState<OutboxList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [f, d] = await Promise.all([getOutbox('failed'), getOutbox('dead')]);
      setFailed(f);
      setDead(d);
    } catch (err) {
      logError('OutboxQueueSection.load', err);
      setError(getErrorMessage(err, 'Warteschlange konnte nicht geladen werden.'));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const retry = async (id: number) => {
    setRetrying(id);
    setMessage(null);
    try {
      await retryOutboxMessage(id);
      setMessage(`Nachricht ${id} wird erneut gesendet.`);
      await load();
    } catch (err) {
      logError('OutboxQueueSection.retry', err);
      setError(getErrorMessage(err, 'Nachricht konnte nicht erneut gesendet werden.'));
    } finally {
      setRetrying(null);
    }
  };

  const columns: Column<OutboxMessage>[] = [
    { key: 'id', header: 'Nr.', render: (m) => m.id, numeric: true },
    { key: 'kind', header: 'Art', render: (m) => KIND_LABELS[m.kind] ?? m.kind },
    { key: 'target', header: 'Bezug', render: targetOf },
    { key: 'attempts', header: 'Versuche', render: (m) => m.attempts, numeric: true },
    { key: 'last_error', header: 'Letzter Fehler', render: (m) => m.last_error ?? '—', hideBelow: 'tablet' },
    { key: 'next', header: 'Nächster Versuch', render: (m) => formatDateTime(m.next_attempt_at), numeric: true, hideBelow: 'tablet' },
    {
      key: 'action',
      header: 'Aktion',
      align: 'end',
      render: (m) => (
        <Button
          variant="secondary"
          icon="send"
          loading={retrying === m.id}
          onClick={() => void retry(m.id)}
        >
          Nachricht erneut senden
        </Button>
      ),
    },
  ];

  const stateOf = (list: OutboxList | null): PageStateValue => {
    if (error && !list) return { status: 'error', error, retry: () => void load() };
    if (!list) return { status: 'loading' };
    return { status: list.items.length ? 'ready' : 'empty' };
  };

  const counts = dead?.counts ?? failed?.counts;

  return (
    <div className="admin-section">
      <h2>Nachrichten-Warteschlange</h2>
      <p className="theme-field-hint">
        Kunden-E-Mails, die der Hintergrunddienst nicht zustellen konnte.
        {counts &&
          ` Wartend: ${counts.pending} · Zugestellt: ${counts.sent} · ` +
            `Fehlgeschlagen: ${counts.failed} · Aufgegeben: ${counts.dead}.`}
        {dead?.mode === 'inline' &&
          ' Versandmodus: direkt (ohne Hintergrunddienst) — die Liste bleibt leer.'}
      </p>
      {error && (failed || dead) && (
        <div className="admin-error-banner" role="alert">
          {error}
        </div>
      )}
      {message && (
        <p className="theme-field-hint" role="status">
          {message}
        </p>
      )}
      <DataTable
        caption="Fehlgeschlagen – wird automatisch wiederholt"
        showCaption
        rows={failed?.items ?? []}
        columns={columns}
        getRowKey={(m) => m.id}
        state={stateOf(failed)}
        empty={{ title: 'Keine fehlgeschlagenen Nachrichten', headingLevel: 3, action: <Button variant="ghost" icon="refresh" onClick={() => void load()}>Liste aktualisieren</Button> }}
      />
      <DataTable
        caption="Aufgegeben – nur manuell erneut senden"
        showCaption
        rows={dead?.items ?? []}
        columns={columns}
        getRowKey={(m) => m.id}
        state={stateOf(dead)}
        empty={{ title: 'Keine aufgegebenen Nachrichten', headingLevel: 3, action: <Button variant="ghost" icon="refresh" onClick={() => void load()}>Liste aktualisieren</Button> }}
      />
    </div>
  );
};

export default OutboxQueueSection;
