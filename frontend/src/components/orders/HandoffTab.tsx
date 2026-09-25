// HandoffTab: Übergaben zwischen Goldschmieden, in the Arbeit tab.
//
// W4-03: the order's handoffs (queryKeys.handoffs.forOrder, refreshed by
// the order_updates / notifications hints) and the recipient list
// (queryKeys.users.list) are queries; create, accept and decline are
// mutations that invalidate the handoffs root (also the dashboard lane).
// Types follow the generated HandoffRead schema: lowercase wire values
// (`pass_to_next`, `pending`), names from first_name/last_name.
import React, { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { handoffsApi, type HandoffCreateInput } from '../../api/handoffs';
import { usersApi } from '../../api';
import type { Schema } from '../../api/generated';
import { queryKeys } from '../../api/queryKeys';
import { useAuth, useToast } from '../../contexts';
import { HANDOFF_TYPE_LABELS, getHandoffTypeLabel } from '../../design/status';
import { getErrorMessage } from '../../lib/errors';
import { Button, Card, Field, PageState, type PageStateValue } from '../../ui';
import { StatusBadge } from '../../ui/StatusBadge';

export type Handoff = Schema<'HandoffRead'>;
type HandoffType = Schema<'HandoffTypeEnum'>;
type HandoffUser = Schema<'HandoffUserSummary'>;

const DEFAULT_TYPE: HandoffType = 'pass_to_next';
const USER_PAGE_LIMIT = 100;
const HANDOFF_TYPES = Object.entries(HANDOFF_TYPE_LABELS) as Array<[HandoffType, string]>;

const DATE_TIME = new Intl.DateTimeFormat('de-DE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

const formatDateTime = (value?: string | null): string =>
  value ? DATE_TIME.format(new Date(value)) : '—';

function userName(user: HandoffUser | null | undefined, fallbackId: number | null): string {
  if (user) return `${user.first_name} ${user.last_name}`.trim();
  return fallbackId !== null ? `#${fallbackId}` : 'Unbekannt';
}

async function fetchHandoffs(orderId: number): Promise<Handoff[]> {
  const response = await handoffsApi.getForOrder(orderId);
  return Array.isArray(response.data) ? (response.data as Handoff[]) : [];
}

function useHandoffMutations(orderId: number) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.handoffs.all });
  const onError = (fallback: string) => (err: unknown) =>
    showToast(getErrorMessage(err, fallback), 'error');

  const create = useMutation({
    mutationFn: (payload: HandoffCreateInput) => handoffsApi.create(orderId, payload),
    onSuccess: async () => {
      await refresh();
      showToast('Übergabe erstellt', 'success');
    },
    onError: onError('Übergabe konnte nicht erstellt werden.'),
  });
  const accept = useMutation({
    mutationFn: (id: number) => handoffsApi.accept(id),
    onSuccess: async () => {
      await refresh();
      showToast('Übergabe angenommen', 'success');
    },
    onError: onError('Übergabe konnte nicht angenommen werden.'),
  });
  const decline = useMutation({
    mutationFn: ({ id, notes }: { id: number; notes: string }) =>
      handoffsApi.decline(id, { response_notes: notes }),
    onSuccess: async () => {
      await refresh();
      showToast('Übergabe abgelehnt', 'success');
    },
    onError: onError('Übergabe konnte nicht abgelehnt werden.'),
  });
  return { create, accept, decline };
}

// ---- One handoff ------------------------------------------------------------

interface HandoffCardProps {
  handoff: Handoff;
  currentUserId: number;
  isActing: boolean;
  onAccept: (id: number) => void;
  onDecline: (id: number, notes: string) => Promise<unknown>;
}

function HandoffCard({ handoff, currentUserId, isActing, onAccept, onDecline }: HandoffCardProps) {
  const [declineNotes, setDeclineNotes] = useState('');
  const [isDeclining, setIsDeclining] = useState(false);
  const canAct = handoff.to_user_id === currentUserId && handoff.status === 'pending';

  const handleDecline = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!declineNotes.trim()) return;
    try {
      await onDecline(handoff.id, declineNotes.trim());
      setIsDeclining(false);
    } catch {
      // The mutation's onError already showed the toast; keep the form open.
    }
  };

  return (
    <Card className="handoff-card">
      <p className="handoff-card__route">
        {userName(handoff.from_user, handoff.from_user_id)} → {userName(handoff.to_user, handoff.to_user_id)}
      </p>
      <p className="handoff-card__meta">
        <span>{getHandoffTypeLabel(handoff.handoff_type)}</span>{' '}
        <StatusBadge kind="handoff" status={handoff.status} />
      </p>
      {handoff.notes && <p className="handoff-card__notes">{handoff.notes}</p>}
      <p className="handoff-card__date tabular-nums">
        Erstellt: {formatDateTime(handoff.created_at)}
        {handoff.responded_at && <> · Beantwortet: {formatDateTime(handoff.responded_at)}</>}
      </p>
      {handoff.response_notes && (
        <p className="handoff-card__response-notes">Antwort: {handoff.response_notes}</p>
      )}

      {canAct && !isDeclining && (
        <div className="handoff-card__actions">
          <Button variant="primary" loading={isActing} onClick={() => onAccept(handoff.id)}>
            Übergabe annehmen
          </Button>
          <Button variant="secondary" disabled={isActing} onClick={() => setIsDeclining(true)}>
            Übergabe ablehnen
          </Button>
        </div>
      )}
      {canAct && isDeclining && (
        <form className="handoff-decline-form" onSubmit={handleDecline}>
          <Field label="Begründung" name={`decline-${handoff.id}`} required>
            <textarea
              value={declineNotes}
              onChange={(e) => setDeclineNotes(e.target.value)}
              rows={3}
            />
          </Field>
          <div className="handoff-card__actions">
            <Button
              type="submit"
              variant="danger"
              loading={isActing}
              disabled={!declineNotes.trim()}
            >
              Ablehnung senden
            </Button>
            <Button variant="ghost" disabled={isActing} onClick={() => setIsDeclining(false)}>
              Abbrechen
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}

// ---- New handoff form -------------------------------------------------------

interface HandoffFormProps {
  recipients: ReadonlyArray<{ id: number; label: string }>;
  isSubmitting: boolean;
  recipientRef: React.RefObject<HTMLSelectElement>;
  onSubmit: (payload: HandoffCreateInput) => Promise<unknown>;
}

function HandoffForm({ recipients, isSubmitting, recipientRef, onSubmit }: HandoffFormProps) {
  const [toUserId, setToUserId] = useState('');
  const [handoffType, setHandoffType] = useState<HandoffType>(DEFAULT_TYPE);
  const [notes, setNotes] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!toUserId) return;
    try {
      await onSubmit({
        to_user_id: Number(toUserId),
        handoff_type: handoffType,
        notes: notes.trim() || undefined,
      });
      setToUserId('');
      setHandoffType(DEFAULT_TYPE);
      setNotes('');
    } catch {
      // The mutation's onError already showed the toast; keep the input.
    }
  };

  return (
    <form className="handoff-form" onSubmit={handleSubmit}>
      <div className="handoff-form__fields">
        <Field label="Empfänger" name="handoff-to-user" required>
          <select
            id="handoff-to-user"
            ref={recipientRef}
            value={toUserId}
            onChange={(e) => setToUserId(e.target.value)}
          >
            <option value="">— Bitte wählen —</option>
            {recipients.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Übergabetyp" name="handoff-type">
          <select
            id="handoff-type"
            value={handoffType}
            onChange={(e) => setHandoffType(e.target.value as HandoffType)}
          >
            {HANDOFF_TYPES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Notizen" name="handoff-notes" help="Optional: besondere Hinweise für den Empfänger.">
          <textarea id="handoff-notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
        </Field>
      </div>
      <Button type="submit" variant="primary" icon="send" loading={isSubmitting} disabled={!toUserId}>
        Übergabe erstellen
      </Button>
    </form>
  );
}

// ---- Tab --------------------------------------------------------------------

interface HandoffTabProps {
  orderId: number;
}

const HandoffTab: React.FC<HandoffTabProps> = ({ orderId }) => {
  const { user: currentUser } = useAuth();
  const recipientRef = useRef<HTMLSelectElement>(null);
  const handoffs = useQuery({
    queryKey: queryKeys.handoffs.forOrder(orderId),
    queryFn: () => fetchHandoffs(orderId),
  });
  const users = useQuery({
    queryKey: queryKeys.users.list(0, USER_PAGE_LIMIT),
    queryFn: () => usersApi.getAll(0, USER_PAGE_LIMIT),
  });
  const { create, accept, decline } = useHandoffMutations(orderId);

  // Everyone except me; a failed user list leaves the dropdown empty.
  const recipients = (users.data ?? [])
    .filter((u) => u.id !== currentUser?.id)
    .map((u) => ({
      id: u.id,
      label: `${u.first_name && u.last_name ? `${u.first_name} ${u.last_name}` : u.email} (${u.role})`,
    }));

  const rows = handoffs.data ?? [];
  const state: PageStateValue = handoffs.isPending
    ? { status: 'loading' }
    : handoffs.isError
      ? {
          status: 'error',
          error: getErrorMessage(handoffs.error, 'Übergaben konnten nicht geladen werden.'),
          retry: () => void handoffs.refetch(),
        }
      : rows.length === 0
        ? { status: 'empty' }
        : { status: 'ready' };
  const actingId = accept.isPending
    ? accept.variables
    : decline.isPending
      ? decline.variables?.id
      : undefined;

  return (
    <div className="handoff-tab">
      <Card title="Neue Übergabe" headingLevel={3}>
        <HandoffForm
          recipients={recipients}
          isSubmitting={create.isPending}
          recipientRef={recipientRef}
          onSubmit={(payload) => create.mutateAsync(payload)}
        />
      </Card>

      <section className="handoff-history-section" aria-labelledby={`handoff-history-${orderId}`}>
        <h3 id={`handoff-history-${orderId}`}>Übergabehistorie ({rows.length})</h3>
        <PageState
          state={state}
          skeleton="cards"
          skeletonCount={2}
          empty={{
            icon: 'send',
            headingLevel: 3,
            title: 'Noch keine Übergaben für diesen Auftrag.',
            action: (
              <Button variant="secondary" onClick={() => recipientRef.current?.focus()}>
                Empfänger wählen
              </Button>
            ),
          }}
        >
          <ul className="handoff-list">
            {rows.map((h) => (
              <li key={h.id}>
                <HandoffCard
                  handoff={h}
                  currentUserId={currentUser?.id ?? -1}
                  isActing={actingId === h.id}
                  onAccept={(id) => accept.mutate(id)}
                  onDecline={(id, notes) => decline.mutateAsync({ id, notes })}
                />
              </li>
            ))}
          </ul>
        </PageState>
      </section>
    </div>
  );
};

export default HandoffTab;
