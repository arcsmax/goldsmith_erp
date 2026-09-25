// "Übergaben an mich" lane of the Heute view. Each row opens the order's
// Übergabe tab, where the handoff is accepted or declined (HandoffTab).
import React, { useCallback, useEffect, useState } from 'react';
import { handoffsApi } from '../../api/handoffs';
import { getHandoffTypeLabel } from '../../design/status';
import { logError } from '../../lib/logError';
import { useRefetchOn } from '../../lib/refetchBus';
import { TodayLane, TodayRow } from './TodayLane';

interface PendingHandoff {
  id: number;
  order_id: number;
  handoff_type: string;
  notes?: string | null;
  from_user?: { full_name?: string | null } | null;
}

function isPendingHandoff(value: unknown): value is PendingHandoff {
  if (value === null || typeof value !== 'object') return false;
  const row = value as Record<string, unknown>;
  return typeof row.id === 'number' && typeof row.order_id === 'number';
}

export const HandoffLane: React.FC = () => {
  const [handoffs, setHandoffs] = useState<PendingHandoff[]>([]);
  const [hasError, setHasError] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await handoffsApi.getPending();
      const rows: unknown[] = Array.isArray(response.data) ? response.data : [];
      setHandoffs(rows.filter(isPendingHandoff));
      setHasError(false);
    } catch (err) {
      logError('Offene Übergaben konnten nicht geladen werden', err);
      setHasError(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);
  useRefetchOn('orders', () => void load());
  useRefetchOn('notifications', () => void load());

  if (hasError) {
    return (
      <p className="deadlines-error" role="alert">
        Offene Übergaben konnten nicht geladen werden.
      </p>
    );
  }
  if (handoffs.length === 0) return null;

  return (
    <TodayLane
      id="heute-uebergaben"
      title="Übergaben an mich"
      count={handoffs.length}
      emptyText=""
    >
      {handoffs.map((handoff) => (
        <TodayRow
          key={handoff.id}
          tone="urgent"
          badge={`#${handoff.order_id}`}
          badgeLabel="Auftrag"
          title={`Übergabe: ${getHandoffTypeLabel(handoff.handoff_type)}`}
          meta={[
            handoff.from_user?.full_name ? `Von ${handoff.from_user.full_name}` : null,
            handoff.notes,
          ]}
          action={{
            to: `/orders/${handoff.order_id}`,
            label: 'Übergabe annehmen',
            orderTab: { orderId: handoff.order_id, tab: 'handoff' },
          }}
        />
      ))}
    </TodayLane>
  );
};
