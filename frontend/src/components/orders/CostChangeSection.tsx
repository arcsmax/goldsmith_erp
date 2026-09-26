// CostChangeSection — §649 cost-change history, create-form & record-response
// modal (V1.2 Task 5; W4-03 on TanStack Query + src/ui). Mounted in the
// order-detail work tab beside CostBreakdownCard.
//
// Permission model mirrors KundeninfoTab / CostAlertBanner: listCostChanges
// is COST_CHANGE_VIEW and every write is COST_CHANGE_MANAGE, both ADMIN +
// GOLDSMITH only. A VIEWER must never trigger the GET (it 403s backend-side)
// and never see any write action — so the query itself is disabled for the
// role, not just the rendered UI.
//
// Every write invalidates queryKeys.orders.detail(orderId), which refreshes
// this history, the CostAlertBanner's projected cost and the order itself.
import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth, useConfirm, useToast } from '../../contexts';
import { customerUpdatesApi } from '../../api/customer-updates';
import type {
  CostChange,
  CostChangeCreateInput,
  CostChangeRecordResponseInput,
  CostChangeResponseMethod,
} from '../../api/customer-updates';
import { queryKeys } from '../../api/queryKeys';
import { COST_CHANGE_STATUS } from '../../design/status';
import { getErrorMessage } from '../../lib/errors';
import { formatEur, MONEY_CLASS } from '../../lib/format';
import { logError } from '../../lib/logError';
import { formatPercentage } from '../../utils/formatters';
import { Button, Field, Modal, PageState, type PageStateValue } from '../../ui';
import { StatusBadge } from '../../ui/StatusBadge';
import { CostChangeForm } from './CostChangeForm';
import { invalidateOrder } from './orderQueries';
import './cost-change.css';

export interface CostChangeSectionProps {
  orderId: number;
  /** Optional notification after a successful write (the queries refresh themselves). */
  onChanged?: () => void;
}

const RESPONSE_METHOD_LABELS: Record<CostChangeResponseMethod, string> = {
  email_reply: 'E-Mail-Antwort',
  in_person: 'Persönlich',
  phone: 'Telefon',
};

const RESPONSE_EVIDENCE_MIN = 5;
const RESPONSE_EVIDENCE_MAX = 2000;
const RESPONSE_FORM_ID = 'cost-change-response-form';

function sortNewestFirst(costChanges: CostChange[]): CostChange[] {
  return [...costChanges].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
}

async function fetchHistory(orderId: number): Promise<CostChange[]> {
  try {
    return sortNewestFirst(await customerUpdatesApi.listCostChanges(orderId));
  } catch (err) {
    logError('CostChangeSection.loadHistory', err);
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Record-response modal
// ---------------------------------------------------------------------------

interface RecordResponseModalProps {
  costChange: CostChange;
  isSubmitting: boolean;
  onClose: () => void;
  onSubmit: (input: CostChangeRecordResponseInput) => void;
}

/** Mounted with `key={costChange.id}`, so each row starts with a fresh draft. */
function RecordResponseModal({
  costChange,
  isSubmitting,
  onClose,
  onSubmit,
}: RecordResponseModalProps) {
  const [status, setStatus] = useState<'approved' | 'declined'>('approved');
  const [responseMethod, setResponseMethod] = useState<CostChangeResponseMethod>('email_reply');
  const [evidence, setEvidence] = useState('');
  const [error, setError] = useState<string | undefined>(undefined);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    const trimmed = evidence.trim();
    if (trimmed.length < RESPONSE_EVIDENCE_MIN || trimmed.length > RESPONSE_EVIDENCE_MAX) {
      setError(
        `Nachweis muss zwischen ${RESPONSE_EVIDENCE_MIN} und ${RESPONSE_EVIDENCE_MAX} Zeichen lang sein.`
      );
      return;
    }
    setError(undefined);
    onSubmit({ status, response_method: responseMethod, response_evidence: trimmed });
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Antwort erfassen"
      description={`Kostenänderung über ${formatEur(costChange.new_amount)} (netto)`}
      size="sm"
      isDirty={evidence.trim().length > 0 && !isSubmitting}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Abbrechen
          </Button>
          <Button type="submit" form={RESPONSE_FORM_ID} variant="primary" loading={isSubmitting}>
            Antwort speichern
          </Button>
        </>
      }
    >
      <form
        id={RESPONSE_FORM_ID}
        className="cost-change-response-form"
        noValidate
        onSubmit={handleSubmit}
      >
        <Field label="Antwort des Kunden" name="status">
          <select
            id="cost-change-response-status"
            value={status}
            onChange={(e) => setStatus(e.target.value as 'approved' | 'declined')}
            disabled={isSubmitting}
          >
            <option value="approved">{COST_CHANGE_STATUS.approved.label}</option>
            <option value="declined">{COST_CHANGE_STATUS.declined.label}</option>
          </select>
        </Field>

        <Field label="Art der Rückmeldung" name="response_method">
          <select
            id="cost-change-response-method"
            value={responseMethod}
            onChange={(e) => setResponseMethod(e.target.value as CostChangeResponseMethod)}
            disabled={isSubmitting}
          >
            {(Object.keys(RESPONSE_METHOD_LABELS) as CostChangeResponseMethod[]).map((method) => (
              <option key={method} value={method}>
                {RESPONSE_METHOD_LABELS[method]}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Nachweis / Notiz" name="response_evidence" error={error}>
          <textarea
            id="cost-change-response-evidence"
            rows={4}
            maxLength={RESPONSE_EVIDENCE_MAX}
            value={evidence}
            onChange={(e) => setEvidence(e.target.value)}
            disabled={isSubmitting}
          />
        </Field>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Data hooks
// ---------------------------------------------------------------------------

function useCostChangeHistory(orderId: number, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.orders.costChanges(orderId),
    queryFn: () => fetchHistory(orderId),
    enabled,
  });
}

function useCostChangeMutations(orderId: number, onChanged?: () => void) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const afterWrite = async () => {
    await invalidateOrder(queryClient, orderId);
    onChanged?.();
  };
  const fail = (context: string, fallback: string) => (err: unknown) => {
    logError(context, err);
    showToast(getErrorMessage(err, fallback), 'error');
  };

  const create = useMutation({
    mutationFn: (input: CostChangeCreateInput) =>
      customerUpdatesApi.createCostChange(orderId, input),
    onSuccess: async () => {
      showToast('Kostenänderung angelegt', 'success');
      await afterWrite();
    },
    onError: fail(
      'CostChangeSection.createCostChange',
      'Kostenänderung konnte nicht angelegt werden.'
    ),
  });

  const send = useMutation({
    mutationFn: (costChangeId: number) => customerUpdatesApi.sendCostChange(costChangeId),
    onSuccess: async (result) => {
      if (result.delivered) showToast('Kostenänderung per E-Mail versendet', 'success');
      else showToast('Als PDF erstellt — bitte manuell an den Kunden übergeben.', 'info');
      await afterWrite();
    },
    onError: fail('CostChangeSection.sendCostChange', 'Kostenänderung konnte nicht gesendet werden.'),
  });

  const recordResponse = useMutation({
    mutationFn: ({ id, input }: { id: number; input: CostChangeRecordResponseInput }) =>
      customerUpdatesApi.recordCostChangeResponse(id, input),
    onSuccess: async () => {
      showToast('Antwort erfasst', 'success');
      await afterWrite();
    },
    onError: fail(
      'CostChangeSection.recordCostChangeResponse',
      'Antwort konnte nicht erfasst werden.'
    ),
  });

  return { create, send, recordResponse };
}

function historyState(query: ReturnType<typeof useCostChangeHistory>): PageStateValue {
  if (query.isPending) return { status: 'loading' };
  if (query.isError) {
    return {
      status: 'error',
      error: getErrorMessage(
        query.error,
        'Verlauf der Kostenänderungen konnte nicht geladen werden.'
      ),
      retry: () => void query.refetch(),
    };
  }
  return { status: query.data.length === 0 ? 'empty' : 'ready' };
}

// ---------------------------------------------------------------------------
// History row
// ---------------------------------------------------------------------------

interface CostChangeItemProps {
  costChange: CostChange;
  isBusy: boolean;
  onSend: (costChange: CostChange) => void;
  onRecordResponse: (costChange: CostChange) => void;
}

function CostChangeItem({ costChange, isBusy, onSend, onRecordResponse }: CostChangeItemProps) {
  return (
    <li className="cost-change-item">
      <div className="cost-change-item-header">
        <span className={`cost-change-amounts ${MONEY_CLASS}`}>
          {formatEur(costChange.original_amount)} → {formatEur(costChange.new_amount)} (netto)
        </span>
        <StatusBadge kind="costChange" status={costChange.status} />
      </div>
      <p className="cost-change-delta">{formatPercentage(costChange.delta_percent)}</p>
      <p className="cost-change-reason">{costChange.reason}</p>
      <div className="cost-change-item-actions">
        {costChange.status === 'draft' && (
          <Button variant="primary" icon="send" onClick={() => onSend(costChange)} disabled={isBusy}>
            Senden
          </Button>
        )}
        {costChange.status === 'sent' && (
          <Button
            variant="secondary"
            onClick={() => onRecordResponse(costChange)}
            disabled={isBusy}
          >
            Antwort erfassen
          </Button>
        )}
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// CostChangeSection
// ---------------------------------------------------------------------------

export function CostChangeSection({ orderId, onChanged }: CostChangeSectionProps) {
  const { hasRole } = useAuth();
  const { showConfirm } = useConfirm();
  const canManage = hasRole(['ADMIN', 'GOLDSMITH']);

  const history = useCostChangeHistory(orderId, canManage);
  const { create, send, recordResponse } = useCostChangeMutations(orderId, onChanged);
  const [responseTarget, setResponseTarget] = useState<CostChange | null>(null);
  const isBusy = create.isPending || send.isPending || recordResponse.isPending;

  const handleCreate = async (input: CostChangeCreateInput): Promise<void> => {
    if (isBusy) return;
    // Rejects on failure (onError already toasted), so the form keeps the draft.
    await create.mutateAsync(input);
  };

  const handleSend = async (costChange: CostChange) => {
    if (isBusy) return;
    const ok = await showConfirm({
      title: '§649 Kostenänderung senden',
      message: `Kostenänderung über ${formatEur(costChange.new_amount)} (netto) an den Kunden senden?`,
      confirmLabel: 'Senden',
    });
    if (ok) send.mutate(costChange.id);
  };

  const handleRecordResponse = (input: CostChangeRecordResponseInput) => {
    if (!responseTarget || isBusy) return;
    recordResponse.mutate(
      { id: responseTarget.id, input },
      { onSuccess: () => setResponseTarget(null) }
    );
  };

  if (!canManage) {
    return (
      <div className="cost-change-section cost-change-section-forbidden">
        <p>
          Keine Berechtigung. Dieser Bereich ist nur für Goldschmiede und Administratoren
          zugänglich.
        </p>
      </div>
    );
  }

  return (
    <div className="cost-change-section">
      <section className="cost-change-history" aria-labelledby="cost-change-history-title">
        <h3 id="cost-change-history-title">§649 Kostenänderungen</h3>
        <PageState
          state={historyState(history)}
          skeletonCount={2}
          empty={{
            icon: 'receipt',
            title: 'Noch keine Kostenänderungen',
            body: 'Eine neue Kostenänderung legst du unten im Formular an.',
            headingLevel: 3,
          }}
        >
          <ul className="cost-change-list">
            {(history.data ?? []).map((costChange) => (
              <CostChangeItem
                key={costChange.id}
                costChange={costChange}
                isBusy={isBusy}
                onSend={(target) => void handleSend(target)}
                onRecordResponse={setResponseTarget}
              />
            ))}
          </ul>
        </PageState>
      </section>

      <section className="cost-change-compose" aria-labelledby="cost-change-compose-title">
        <h3 id="cost-change-compose-title">Neue Kostenänderung</h3>
        <CostChangeForm onSubmit={handleCreate} disabled={isBusy} />
      </section>

      {responseTarget && (
        <RecordResponseModal
          key={responseTarget.id}
          costChange={responseTarget}
          isSubmitting={recordResponse.isPending}
          onClose={() => setResponseTarget(null)}
          onSubmit={handleRecordResponse}
        />
      )}
    </div>
  );
}

export default CostChangeSection;
