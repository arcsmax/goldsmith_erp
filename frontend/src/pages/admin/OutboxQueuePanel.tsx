// Nachrichten-Warteschlange (ARCH-04 / ARCH-12; W4-03 on queries): customer
// mails the worker could not deliver. "Fehlgeschlagen" rows are retried
// automatically with backoff; "Aufgegeben" rows wait for an admin. Both can
// be sent again here. ADMIN only (route guard; backend OUTBOX_MANAGE).
// Shows ids and error codes only — never recipient, subject or body.
import React from 'react';
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import { retryOutboxMessage, type OutboxList, type OutboxMessage } from '../../api/admin';
import { adminKeys, outboxQuery } from '../../api/adminQueries';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { Button, Card, DataTable, type Column, type PageStateValue } from '../../ui';

const KIND_LABELS: Record<string, string> = {
  customer_update: 'Kundeninfo',
  quote_email: 'Kostenvoranschlag',
};

const LOAD_ERROR = 'Warteschlange konnte nicht geladen werden.';

const formatDateTime = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString('de-DE') : '—';

const targetOf = (m: OutboxMessage): string => {
  const p = m.payload as Record<string, unknown>;
  if (p.update_id != null) return `Kundeninfo #${String(p.update_id)}`;
  if (p.quote_id != null) return `Kostenvoranschlag #${String(p.quote_id)}`;
  return '—';
};

const stateOf = (query: UseQueryResult<OutboxList>): PageStateValue => {
  if (query.isError) {
    return { status: 'error', error: getErrorMessage(query.error, LOAD_ERROR), retry: () => void query.refetch() };
  }
  if (!query.data) return { status: 'loading' };
  return { status: query.data.items.length ? 'ready' : 'empty' };
};

export const OutboxQueuePanel: React.FC = () => {
  const queryClient = useQueryClient();
  const failed = useQuery(outboxQuery('failed'));
  const dead = useQuery(outboxQuery('dead'));

  const refresh = () => void queryClient.invalidateQueries({ queryKey: adminKeys.outboxAll() });

  const retry = useMutation({
    mutationFn: (id: number) => retryOutboxMessage(id),
    onSuccess: () => refresh(),
    onError: (err) => logError('OutboxQueuePanel.retry', err),
  });

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
          loading={retry.isPending && retry.variables === m.id}
          onClick={() => retry.mutate(m.id)}
        >
          Nachricht erneut senden
        </Button>
      ),
    },
  ];

  const refreshAction = (
    <Button variant="ghost" icon="refresh" onClick={refresh}>
      Liste aktualisieren
    </Button>
  );
  const counts = dead.data?.counts ?? failed.data?.counts;

  return (
    <Card title="Nachrichten-Warteschlange" className="admin-panel">
      <p className="admin-panel__intro">
        Kunden-E-Mails, die der Hintergrunddienst nicht zustellen konnte.
        {counts &&
          ` Wartend: ${counts.pending} · Zugestellt: ${counts.sent} · ` +
            `Fehlgeschlagen: ${counts.failed} · Aufgegeben: ${counts.dead}.`}
        {dead.data?.mode === 'inline' &&
          ' Versandmodus: direkt (ohne Hintergrunddienst) — die Liste bleibt leer.'}
      </p>
      {retry.isError && (
        <p className="admin-notice admin-notice--danger" role="alert">
          {getErrorMessage(retry.error, 'Nachricht konnte nicht erneut gesendet werden.')}
        </p>
      )}
      {retry.isSuccess && (
        <p className="admin-panel__hint" role="status">
          Nachricht {retry.variables} wird erneut gesendet.
        </p>
      )}
      <DataTable
        caption="Fehlgeschlagen – wird automatisch wiederholt"
        showCaption
        rows={failed.data?.items ?? []}
        columns={columns}
        getRowKey={(m) => m.id}
        state={stateOf(failed)}
        empty={{ title: 'Keine fehlgeschlagenen Nachrichten', headingLevel: 3, action: refreshAction }}
      />
      <DataTable
        caption="Aufgegeben – nur manuell erneut senden"
        showCaption
        rows={dead.data?.items ?? []}
        columns={columns}
        getRowKey={(m) => m.id}
        state={stateOf(dead)}
        empty={{ title: 'Keine aufgegebenen Nachrichten', headingLevel: 3, action: refreshAction }}
      />
    </Card>
  );
};

export default OutboxQueuePanel;
