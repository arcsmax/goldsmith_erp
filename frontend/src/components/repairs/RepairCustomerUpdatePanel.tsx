// RepairCustomerUpdatePanel — pickup-ready Kundeninfo draft on
// RepairDetailPage (DOM-12 / W2-02; W4-03 on TanStack Query and src/ui).
//
// Reaching READY creates a DRAFT CustomerUpdate server-side (see
// RepairService.complete_repair) — nothing is sent to the customer yet.
// This panel shows that draft and lets staff send it with one tap. It
// reuses the SAME CustomerUpdate draft/send mechanism the order-scoped
// Kundeninfo flow uses (api/customer-updates.ts), not a second path.
//
// Only rendered for repairs that could have a draft (status ready or
// picked_up — see _VALID_TRANSITIONS in repair_service.py: READY is only
// reachable once and never reverts, so no earlier status can have one).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { customerUpdatesApi } from '../../api/customer-updates';
import type { CustomerUpdate } from '../../api/customer-updates';
import { repairCustomerUpdatesQuery, repairKeys } from '../../api/repairQueries';
import type { RepairJob } from '../../types';
import { useToast } from '../../contexts';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { Button, Card } from '../../ui';
import { StatusBadge } from '../../ui/StatusBadge';
import { formatRepairDateTime } from './repairFormat';
import { openRepairStatusReport } from './statusReport';

interface RepairCustomerUpdatePanelProps {
  repair: RepairJob;
  /** Called after a send — customer_notified_at only ever changes
   *  server-side on an actual delivered send, so the parent must refetch
   *  rather than have this panel guess the value. */
  onRepairRefresh: () => void;
}

function useSendUpdate(repairId: number, onRepairRefresh: () => void) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: () => customerUpdatesApi.sendRepairUpdate(repairId),
    onSuccess: (result) => {
      queryClient.setQueryData<CustomerUpdate[]>(repairKeys.customerUpdates(repairId), (prev) => [
        result.update,
        ...(prev ?? []).slice(1),
      ]);
      // W6: an Art. 21 opt-out is an expected outcome, not an error.
      const notSentMessage =
        result.reason === 'opted_out'
          ? 'Kunde wünscht keine E-Mail-Updates — bitte als PDF übergeben'
          : 'E-Mail-Versand nicht möglich — Entwurf bleibt erhalten (PDF-Fallback über Kundeninfo)';
      showToast(
        result.delivered ? 'Kunde wurde benachrichtigt' : notSentMessage,
        result.delivered ? 'success' : result.reason === 'opted_out' ? 'info' : 'error',
      );
      // customer_notified_at on the repair changes ONLY when this send was
      // delivered — refetch from the parent rather than duplicating that
      // rule here (see RepairService.send_customer_update).
      onRepairRefresh();
    },
    onError: (err) => {
      logError('Kundeninfo-Update senden fehlgeschlagen', err);
      showToast('Versand fehlgeschlagen', 'error');
    },
  });
}

function useStatusReport(repairId: number) {
  const { showToast } = useToast();
  return useMutation({
    mutationFn: () => openRepairStatusReport(repairId),
    onError: (err) => {
      logError('Statusbericht laden fehlgeschlagen', err);
      showToast('Statusbericht konnte nicht erstellt werden', 'error');
    },
  });
}

export function RepairCustomerUpdatePanel({ repair, onRepairRefresh }: RepairCustomerUpdatePanelProps) {
  const canHaveDraft = repair.status === 'ready' || repair.status === 'picked_up';
  const updates = useQuery({ ...repairCustomerUpdatesQuery(repair.id), enabled: canHaveDraft });
  const send = useSendUpdate(repair.id, onRepairRefresh);
  const report = useStatusReport(repair.id);

  if (!canHaveDraft) return null;

  const update = updates.data?.[0] ?? null;

  return (
    <Card
      title="Kundeninfo — Abholbereit"
      headingLevel={3}
      action={update ? <StatusBadge kind="customerUpdate" status={update.status} /> : undefined}
      className="repair-update-panel"
    >
      <Button variant="secondary" icon="file-text" loading={report.isPending} onClick={() => report.mutate()}>
        Statusbericht (PDF)
      </Button>

      {updates.isPending && <p className="repair-update-panel__muted">Wird geladen…</p>}

      {updates.isError && (
        <p className="repair-update-panel__muted" role="alert">
          {getErrorMessage(updates.error, 'Kundeninfo konnte nicht geladen werden.')}
        </p>
      )}

      {updates.isSuccess && !update && (
        <p className="repair-update-panel__muted">Noch kein Kundeninfo-Entwurf vorhanden.</p>
      )}

      {update && (
        <>
          <p className="repair-update-panel__subject">{update.subject}</p>
          {update.status === 'sent' ? (
            <p className="repair-update-panel__muted">
              Verschickt am {formatRepairDateTime(update.sent_at)}
              {update.delivery_method === 'email' ? ' per E-Mail' : ''}.
            </p>
          ) : (
            <Button icon="send" loading={send.isPending} onClick={() => send.mutate()}>
              Kunde benachrichtigen
            </Button>
          )}
        </>
      )}
    </Card>
  );
}
