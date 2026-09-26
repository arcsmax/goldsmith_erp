// Werkstatt: kanban board over the jobs spine (W6, ARCH-02). Orders and
// repairs side by side, one column per unified job status. No drag and drop
// yet; "Weiter" on a card advances it by its obvious next step.
import React, { useId, useRef, useState } from 'react';

import type { JobListItem } from '../api/jobs';
import { BoardColumn } from '../components/workshop/BoardColumn';
import {
  advanceStep,
  BOARD_COLUMNS,
  COLUMN_NAV_KEYS,
  nextColumnIndex,
  type JobKindFilter,
} from '../components/workshop/boardModel';
import { CustomerFilter, type PickedCustomer } from '../components/workshop/CustomerFilter';
import { useAdvanceJob, useBoardColumns } from '../components/workshop/useWorkshopBoard';
import { useAuth, useToast } from '../contexts';
import { getStatusLabel } from '../design/status';
import { getErrorCode, getErrorExtra, getErrorMessage } from '../lib/errors';
import { logError } from '../lib/logError';
import { canEditOrders } from '../lib/roles';
import { Field } from '../ui/Field';
import { PageHeader } from '../ui/PageHeader';
import '../styles/workshop.css';

const KIND_OPTIONS: ReadonlyArray<{ value: JobKindFilter; label: string }> = [
  { value: 'all', label: 'Aufträge und Reparaturen' },
  { value: 'order', label: 'Nur Aufträge' },
  { value: 'repair', label: 'Nur Reparaturen' },
];

export function WorkshopBoardPage() {
  const { user } = useAuth();
  const { showToast } = useToast();
  const canAdvance = canEditOrders(user?.role);
  const hintId = useId();
  const [kind, setKind] = useState<JobKindFilter>('all');
  const [customer, setCustomer] = useState<PickedCustomer | null>(null);
  const columnRefs = useRef<Array<HTMLElement | null>>([]);

  const columns = useBoardColumns({ kind, customerId: customer?.id ?? null });
  const advance = useAdvanceJob({
    onSuccess: (job) => {
      const step = advanceStep(job);
      const label = step ? getStatusLabel(step.statusKind, step.target) : '';
      showToast(`Status geändert: ${job.number} ist jetzt „${label}“`, 'success');
    },
    onError: (job, err) => {
      logError('WorkshopBoardPage.advance', err);
      const message = getErrorMessage(err, `Status von ${job.number} konnte nicht geändert werden.`);
      // LV3-02: a DRAFT missing its Pflichtfelder is a dead end without a
      // way to fix it from the board — link straight to the order so the
      // user can complete it, instead of leaving a bare toast.
      const orderId = getErrorExtra(err)?.order_id;
      if (
        getErrorCode(err) === 'order.confirmation_fields_missing' &&
        typeof orderId === 'number'
      ) {
        showToast(message, 'error', 6000, {
          label: 'Auftrag vervollständigen',
          to: `/orders/${orderId}`,
        });
        return;
      }
      showToast(message, 'error');
    },
  });
  const advancingJobId = advance.isPending ? (advance.variables?.id ?? null) : null;

  const handleColumnKey = (index: number) => (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.target !== event.currentTarget || !COLUMN_NAV_KEYS.has(event.key)) return;
    event.preventDefault();
    columnRefs.current[nextColumnIndex(event.key, index, BOARD_COLUMNS.length)]?.focus();
  };

  return (
    <div className="page-container workshop-page">
      <PageHeader title="Werkstatt" meta="Aufträge und Reparaturen nach Status" />

      <div className="workshop-filters">
        <Field label="Art" name="workshop-kind">
          <select value={kind} onChange={(e) => setKind(e.target.value as JobKindFilter)}>
            {KIND_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
        <CustomerFilter value={customer} onChange={setCustomer} />
      </div>

      <p id={hintId} className="ui-visually-hidden">
        Mit den Pfeiltasten links und rechts zwischen den Spalten wechseln, mit Tab in die Karten.
      </p>
      <div className="workshop-board" role="group" aria-label="Werkstatt-Board">
        {columns.map((column, index) => (
          <BoardColumn
            key={column.status}
            ref={(el) => {
              columnRefs.current[index] = el;
            }}
            status={column.status}
            jobs={column.jobs}
            total={column.total}
            isLoading={column.isLoading}
            error={column.error}
            onRetry={column.refetch}
            canAdvance={canAdvance}
            advancingJobId={advancingJobId}
            onAdvance={(job: JobListItem) => advance.mutate(job)}
            onKeyDown={handleColumnKey(index)}
            hintId={hintId}
          />
        ))}
      </div>
    </div>
  );
}
