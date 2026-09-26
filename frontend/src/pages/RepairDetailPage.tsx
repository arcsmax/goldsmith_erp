// Reparatur — detail page on TanStack Query and src/ui (W4-03, playbook 5.2).
//
// PageHeader with the back link, identity (number, StatusBadge, deadline),
// the next status step as the one primary action and the print / invoice
// actions beside it. The intake checklist stays above the tabs (dispute
// protection, visible on every tab); the five tabs mirror the order page:
// Übersicht, Arbeit, Fotos, Kunde, Verlauf, with the selection in `?tab=`.
//
// Role gates in code: status steps and cancel need REPAIR_EDIT (ADMIN +
// GOLDSMITH, the same roles as REPAIR_CREATE), Fotos and the Annahmeschein
// DESIGN_VIEW, prices and "Rechnung erstellen" FINANCIAL_VIEW. A VIEWER sees
// the repair read-only.
import React, { useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { jobsApi } from '../api/jobs';
import { repairDetailQuery } from '../api/repairQueries';
import { DEFAULT_PAYMENT_TERM_DAYS, inDaysIso } from '../components/invoices/invoiceFormat';
import { IntakeChecklist } from '../components/repairs/IntakeChecklist';
import { openAnnahmeschein } from '../components/repairs/annahmeschein';
import {
  REPAIR_TAB_LABELS,
  RepairCustomerTab,
  RepairHistoryTab,
  RepairOverviewTab,
  RepairWorkTab,
  repairTabs,
  type RepairPageTab,
} from '../components/repairs/RepairDetailTabs';
import { RepairPhotosTab } from '../components/repairs/RepairPhotosTab';
import { CompleteDialog, DiagnoseDialog } from '../components/repairs/RepairStatusDialogs';
import {
  isCancellable,
  NEXT_ACTION,
  transitionError,
  useRepairCache,
  useRepairTransition,
  type RepairTransition,
} from '../components/repairs/useRepairActions';
import { useAuth, useConfirm, useToast } from '../contexts';
import { getErrorMessage } from '../lib/errors';
import { logError } from '../lib/logError';
import { canCreateRepairs, canViewDesign, canViewFinancials } from '../lib/roles';
import type { RepairJob } from '../types';
import { Button, DeadlineChip, PageHeader, PageState, Tabs, useTabParam } from '../ui';
import { StatusBadge } from '../ui/StatusBadge';
import '../styles/repairs.css';

/** Statuses the backend bills (POST /repairs/{id}/invoice, ARCH-02). */
const INVOICEABLE_STATUSES: readonly string[] = ['ready', 'picked_up'];
const BACK = { to: '/repairs', label: 'Reparaturen' };

type OpenDialog = 'diagnose' | 'complete' | null;

function usePrintAnnahmeschein(repairId: number) {
  const { showToast } = useToast();
  return useMutation({
    mutationFn: () => openAnnahmeschein(repairId),
    onError: (err) => {
      logError('RepairDetailPage.annahmeschein', err);
      showToast('Annahmeschein konnte nicht geladen werden. Bitte erneut versuchen.', 'error');
    },
  });
}

// ARCH-02: bill a finished repair; 409 (already invoiced) and 422 (not
// billable) come back as German backend messages.
function useCreateInvoice(repairId: number) {
  const navigate = useNavigate();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: () =>
      jobsApi.invoiceRepair(repairId, {
        due_date: new Date(inDaysIso(DEFAULT_PAYMENT_TERM_DAYS)).toISOString(),
      }),
    onSuccess: (invoice) => {
      showToast('Rechnung erstellt', 'success');
      navigate(`/invoices?invoice_id=${invoice.id}`);
    },
    onError: (err) => {
      logError('RepairDetailPage.createInvoice', err);
      showToast(getErrorMessage(err, 'Rechnung konnte nicht erstellt werden.'), 'error');
    },
  });
}

function RepairDetailView({ repair }: { repair: RepairJob }) {
  const { user } = useAuth();
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const canEdit = canCreateRepairs(user?.role);
  const canDesign = canViewDesign(user?.role);
  const canFinance = canViewFinancials(user?.role);
  const tabIds = repairTabs(canDesign);
  const [activeTab, setTab] = useTabParam<RepairPageTab>(tabIds, 'uebersicht');
  const [dialog, setDialog] = useState<OpenDialog>(null);

  const cache = useRepairCache(repair.id);
  const transition = useRepairTransition(repair.id, () => setDialog(null));
  const print = usePrintAnnahmeschein(repair.id);
  const invoice = useCreateInvoice(repair.id);

  const next = canEdit ? NEXT_ACTION[repair.status] : undefined;
  const run = (t: RepairTransition) =>
    transition.mutate(t, {
      // Dialog steps show the error inline; one-tap steps as a toast.
      onError: (err) => {
        if (dialog === null) showToast(transitionError(err), 'error');
      },
    });
  const openDialog = (which: Exclude<OpenDialog, null>) => {
    transition.reset();
    setDialog(which);
  };
  const handleNext = () => {
    if (!next) return;
    if (next.action === 'diagnose' || next.action === 'complete') openDialog(next.action);
    else run({ action: next.action });
  };
  const handleCancel = async () => {
    const confirmed = await showConfirm({
      title: 'Reparatur stornieren',
      message: `Möchten Sie die Reparatur ${repair.repair_number} wirklich stornieren?`,
      confirmLabel: 'Stornieren',
      cancelLabel: 'Nicht stornieren',
      variant: 'danger',
    });
    if (confirmed) run({ action: 'cancel' });
  };

  const refresh = () => void cache.refresh();
  const panels: Record<RepairPageTab, () => ReactNode> = {
    uebersicht: () => (
      <RepairOverviewTab
        repair={repair}
        canFinance={canFinance}
        onCancel={canEdit && isCancellable(repair.status) ? () => void handleCancel() : undefined}
        isCancelling={transition.isPending && transition.variables?.action === 'cancel'}
      />
    ),
    arbeit: () => (
      <RepairWorkTab
        repair={repair}
        canFinance={canFinance}
        onDiagnose={next?.action === 'diagnose' ? () => openDialog('diagnose') : undefined}
      />
    ),
    fotos: () => <RepairPhotosTab repair={repair} />,
    kunde: () => <RepairCustomerTab repair={repair} onRepairRefresh={refresh} />,
    verlauf: () => <RepairHistoryTab repair={repair} />,
  };
  const tabItems = tabIds.map((id) => ({
    id,
    label: id === 'fotos' ? `Fotos (${repair.photos?.length ?? 0})` : REPAIR_TAB_LABELS[id],
    panel: id === activeTab ? panels[id]() : undefined,
  }));

  const isOpen = isCancellable(repair.status);
  const meta = (
    <>
      <StatusBadge kind="repair" status={repair.status} />
      {isOpen && repair.estimated_completion_date && (
        <DeadlineChip deadline={repair.estimated_completion_date} />
      )}
      <span className="repair-header-meta">Tüte {repair.bag_number}</span>
      <span className="repair-header-meta">{repair.item_description}</span>
    </>
  );
  const secondaryActions = (
    <>
      {canDesign && (
        <Button variant="secondary" icon="file-text" onClick={() => print.mutate()} loading={print.isPending}>
          Annahmeschein drucken
        </Button>
      )}
      {canFinance && INVOICEABLE_STATUSES.includes(repair.status) && repair.customer_id != null && (
        <Button variant="secondary" icon="receipt" onClick={() => invoice.mutate()} loading={invoice.isPending}>
          Rechnung erstellen
        </Button>
      )}
    </>
  );
  const dialogError = transition.isError ? transitionError(transition.error) : null;

  return (
    <div className="repair-detail-page">
      <PageHeader
        title={repair.repair_number}
        back={BACK}
        meta={meta}
        primaryAction={
          next ? (
            <Button icon={next.icon} onClick={handleNext} loading={transition.isPending && dialog === null}>
              {next.label}
            </Button>
          ) : undefined
        }
        secondaryActions={secondaryActions}
      />

      {/* Eingangs-Checkliste — dispute protection, kept above the tabs so it
          stays visible regardless of which tab is active. */}
      <IntakeChecklist repair={repair} onUpdated={cache.set} onRefresh={refresh} />

      <Tabs label="Reparaturbereiche" tabs={tabItems} selectedId={activeTab} onSelect={setTab} />

      {dialog === 'diagnose' && (
        <DiagnoseDialog
          open
          isSubmitting={transition.isPending}
          error={dialogError}
          onSubmit={run}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'complete' && (
        <CompleteDialog
          open
          estimatedCost={canFinance ? repair.estimated_cost : null}
          isSubmitting={transition.isPending}
          error={dialogError}
          onSubmit={run}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}

export function RepairDetailPage() {
  const { id } = useParams<{ id: string }>();
  const repairId = Number(id);
  const isValidId = Number.isInteger(repairId) && repairId > 0;
  const query = useQuery({ ...repairDetailQuery(repairId), enabled: isValidId });

  if (query.data) return <RepairDetailView repair={query.data} />;

  const state = !isValidId
    ? { status: 'error' as const, error: 'Reparatur nicht gefunden.' }
    : query.isError
      ? {
          status: 'error' as const,
          error: getErrorMessage(query.error, 'Reparatur konnte nicht geladen werden.'),
          retry: () => void query.refetch(),
        }
      : { status: 'loading' as const };
  return (
    <div className="repair-detail-page">
      <PageHeader title="Reparatur" back={BACK} />
      <PageState state={state} skeleton="detail" skeletonCount={3} />
    </div>
  );
}
