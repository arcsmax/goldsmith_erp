// Repair status workflow on TanStack Query (W4-03).
//
// NEXT_ACTION maps a status to the one primary action of the detail page
// header (playbook 5.2: the next step is derived from the status). Every
// transition answers with the fresh RepairJob: it is written into the detail
// cache, and the ['repairs'] root plus the dashboard are invalidated so the
// list and "Heute" follow.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../api/queryKeys';
import { repairKeys } from '../../api/repairQueries';
import { repairsApi } from '../../api/repairs';
import { useToast } from '../../contexts';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import type { RepairJob, RepairJobStatus } from '../../types';
import type { IconName } from '../../ui';

export type RepairTransition =
  | { action: 'diagnose'; diagnosis_notes: string; estimated_cost: number; estimated_completion_date?: string }
  | { action: 'approve' }
  | { action: 'start' }
  | { action: 'quality_check' }
  | { action: 'complete'; actual_cost: number }
  | { action: 'pickup' }
  | { action: 'cancel' };

export type RepairActionName = RepairTransition['action'];

export interface NextAction {
  action: Exclude<RepairActionName, 'cancel'>;
  label: string;
  icon: IconName;
  /** Needs a form first (diagnosis, final cost). */
  hasDialog: boolean;
}

export const NEXT_ACTION: Partial<Record<RepairJobStatus, NextAction>> = {
  received: { action: 'diagnose', label: 'Diagnose stellen', icon: 'search', hasDialog: true },
  quoted: { action: 'approve', label: 'Angebot bestätigen', icon: 'thumbs-up', hasDialog: false },
  approved: { action: 'start', label: 'Reparatur starten', icon: 'wrench', hasDialog: false },
  in_repair: { action: 'quality_check', label: 'Zur QK einreichen', icon: 'scan-search', hasDialog: false },
  quality_check: { action: 'complete', label: 'Fertigmelden', icon: 'circle-check', hasDialog: true },
  ready: { action: 'pickup', label: 'Abholung bestätigen', icon: 'package-check', hasDialog: false },
};

const CLOSED: ReadonlySet<RepairJobStatus> = new Set(['picked_up', 'cancelled']);

export function isCancellable(status: RepairJobStatus): boolean {
  return !CLOSED.has(status);
}

const SUCCESS: Record<RepairActionName, string> = {
  diagnose: 'Diagnose gespeichert',
  approve: 'Angebot bestätigt',
  start: 'Reparatur gestartet',
  quality_check: 'Zur Qualitätskontrolle eingereicht',
  complete: 'Reparatur fertiggemeldet',
  pickup: 'Abholung bestätigt',
  cancel: 'Reparatur storniert',
};

function runTransition(id: number, t: RepairTransition): Promise<RepairJob> {
  switch (t.action) {
    case 'diagnose':
      return repairsApi.diagnose(id, {
        diagnosis_notes: t.diagnosis_notes,
        estimated_cost: t.estimated_cost,
        estimated_completion_date: t.estimated_completion_date,
      });
    case 'approve':
      return repairsApi.approve(id);
    case 'start':
      return repairsApi.startRepair(id);
    case 'quality_check':
      return repairsApi.submitQualityCheck(id);
    case 'complete':
      return repairsApi.complete(id, { actual_cost: t.actual_cost });
    case 'pickup':
      return repairsApi.pickup(id);
    case 'cancel':
      return repairsApi.cancel(id);
  }
}

/** Cache helpers shared by the transitions, photos and the checklist. */
export function useRepairCache(repairId: number) {
  const queryClient = useQueryClient();
  return {
    set: (repair: RepairJob) => queryClient.setQueryData(repairKeys.detail(repairId), repair),
    refresh: () => queryClient.invalidateQueries({ queryKey: repairKeys.detail(repairId) }),
    refreshLists: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: repairKeys.lists() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all }),
      ]),
  };
}

export function useRepairTransition(repairId: number, onDone?: () => void) {
  const cache = useRepairCache(repairId);
  const { showToast } = useToast();
  return useMutation({
    mutationFn: (transition: RepairTransition) => runTransition(repairId, transition),
    onSuccess: async (updated, transition) => {
      cache.set(updated);
      onDone?.();
      showToast(SUCCESS[transition.action], 'success');
      await cache.refreshLists();
    },
    onError: (err, transition) => {
      logError(`RepairDetailPage.${transition.action}`, err);
    },
  });
}

/** German message for a failed transition (shown inline or as a toast). */
export function transitionError(err: unknown): string {
  return getErrorMessage(err, 'Aktion fehlgeschlagen. Bitte erneut versuchen.');
}
