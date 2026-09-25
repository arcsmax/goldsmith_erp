// Order detail page (W2-08; DOM-16, DOM-17, DOM-18, DOM-30), on the
// playbook detail template (UI-UX-PLAYBOOK 5.2) since W4-03.
//
// PageHeader with the back link, identity (title, StatusBadge, DeadlineChip)
// and the next action as one large "Weiter: <Status>" button; five tabs
// (Übersicht, Arbeit, Fotos, Kunde, Verlauf) synced with `?tab=`; a prompt at
// the "Fertiggestellt" / "Ausgeliefert" milestones.
//
// Data: TanStack Query (docs/technical/FRONTEND_DATA_LAYER.md). The order,
// its photos and its Verlauf live under queryKeys.orders.detail(id), so an
// `order_updates` realtime hint (lib/realtimeInvalidation.ts) refreshes them
// in place, without a loading screen; this page registers no refetch of
// its own.
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';
import type { OrderStatus } from '../types';
import { useOrders, useToast, useAuth } from '../contexts';
import { canCreateQuotes, canViewDesign } from '../lib/roles';
import { getErrorMessage } from '../lib/errors';
import { logError } from '../lib/logError';
import { ModalStackHost } from '../lib/modal-stack';
import { Button, ButtonLink, Card, DeadlineChip, PageHeader, PageState, Tabs } from '../ui';
import { StatusBadge } from '../ui/StatusBadge';
import { CommentsTab } from '../components/CommentsTab';
import { KundeninfoTab } from '../components/orders/KundeninfoTab';
import { CostAlertBanner } from '../components/orders/CostAlertBanner';
import { StatusAdvanceButton } from '../components/orders/StatusAdvanceButton';
import { StatusChangeDialog } from '../components/orders/StatusChangeDialog';
import {
  MilestonePrompt,
  buildCompletedDraft,
  type KundeninfoDraft,
  type Milestone,
} from '../components/orders/MilestonePrompt';
import { OrderTimeline } from '../components/orders/OrderTimeline';
import { PieceScanHistory } from '../components/scanner/PieceScanHistory';
import { DeliveredActions } from '../components/orders/DeliveredActions';
import { OrderOverviewTab, type OrderWithStatusFields } from '../components/orders/OrderOverviewTab';
import { OrderWorkTab } from '../components/orders/OrderWorkTab';
import { OrderPhotosTab } from '../components/orders/OrderPhotosTab';
import { PAGE_TAB_LABELS, type OrderPageTab } from '../components/orders/orderPageTabs';
import { orderPhotosQuery, orderQuery } from '../components/orders/orderQueries';
import { canChangeOrderStatus } from '../components/orders/orderStatus';
import { useOrderPageTab } from '../components/orders/useOrderPageTab';
import { useOrderStatusChange } from '../components/orders/useOrderStatusChange';
import '../styles/order-detail.css';

const MILESTONES: readonly OrderStatus[] = ['completed', 'delivered'];

/** A move into a milestone status (not the first load) raises the prompt. */
function useMilestone(status: OrderStatus | undefined, isEnabled: boolean) {
  const [milestone, setMilestone] = useState<Milestone | null>(null);
  const lastStatusRef = useRef<OrderStatus | null>(null);
  useEffect(() => {
    if (status === undefined) return;
    const previous = lastStatusRef.current;
    lastStatusRef.current = status;
    const isNewMilestone = previous !== null && previous !== status && MILESTONES.includes(status);
    if (isNewMilestone && isEnabled) setMilestone(status as Milestone);
  }, [status, isEnabled]);
  return [milestone, setMilestone] as const;
}

/** Keep OrderContext's "active order" (TimerWidget, scanner) on the loaded order. */
function useSyncActiveOrder(order: OrderWithStatusFields | undefined) {
  const { setActiveOrder } = useOrders();
  const setActiveOrderRef = useRef(setActiveOrder);
  setActiveOrderRef.current = setActiveOrder;
  useEffect(() => {
    if (order) setActiveOrderRef.current(order);
  }, [order]);
}

function usePrintLabel(orderId: number) {
  const { showToast } = useToast();
  return useMutation({
    mutationFn: () => apiClient.get(`/orders/${orderId}/label`, { responseType: 'blob' }),
    onSuccess: (response) => {
      const blob = new Blob([response.data], { type: 'text/html;charset=utf-8' });
      const blobUrl = URL.createObjectURL(blob);
      const printWindow = window.open(blobUrl, '_blank');
      if (printWindow) {
        printWindow.focus();
        printWindow.addEventListener('load', () => URL.revokeObjectURL(blobUrl));
      }
    },
    onError: (err) => {
      logError('OrderDetailPage.printLabel', err);
      showToast('Etikett konnte nicht gedruckt werden. Bitte erneut versuchen.', 'error');
    },
  });
}

export function OrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const numericId = orderId ? parseInt(orderId, 10) : NaN;
  if (Number.isNaN(numericId)) return <Navigate to="/orders" replace />;
  return <OrderDetailView key={numericId} orderId={numericId} />;
}

function OrderDetailView({ orderId }: { orderId: number }) {
  const { user } = useAuth();
  // DESIGN_VIEW (SEC-09/GDPR-04): a VIEWER 403s on order photos, so the
  // Fotos tab and the photo fetch are gated on the same check as the backend.
  const canDesign = canViewDesign(user?.role);
  const canChangeStatus = canChangeOrderStatus(user?.role);
  // LV2-04: a VIEWER could see "Angebot erstellen" and be bounced by the guard.
  const canCreateQuote = canCreateQuotes(user?.role);

  const orderQueryResult = useQuery(orderQuery(orderId));
  const order = orderQueryResult.data;
  const photos = useQuery({ ...orderPhotosQuery(orderId), enabled: canDesign }).data ?? [];
  useSyncActiveOrder(order);

  const tab = useOrderPageTab({
    orderId,
    canDesign,
    canChangeStatus,
    isOrderLoaded: order !== undefined,
  });
  const status = useOrderStatusChange(order);
  const [milestone, setMilestone] = useMilestone(order?.status, canChangeStatus);
  const [kundeninfoDraft, setKundeninfoDraft] = useState<KundeninfoDraft | null>(null);
  const printLabel = usePrintLabel(orderId);

  const title = `Auftrag #${orderId}`;
  const back = { to: '/orders', label: 'Aufträge' };

  if (!order) {
    const state = orderQueryResult.isError
      ? {
          status: 'error' as const,
          error: getErrorMessage(orderQueryResult.error, 'Auftrag konnte nicht geladen werden.'),
          retry: () => void orderQueryResult.refetch(),
        }
      : { status: 'loading' as const };
    return (
      <div className="order-detail-container">
        <PageHeader title={title} back={back} />
        <PageState state={state} skeleton="detail" skeletonCount={3} />
      </div>
    );
  }

  const handleMilestoneAction = () => {
    if (milestone === 'completed') setKundeninfoDraft(buildCompletedDraft(order, photos));
    setMilestone(null);
    tab.selectTab('kunde');
  };

  const customerName = order.customer
    ? `${order.customer.first_name} ${order.customer.last_name}`
    : undefined;

  const panels: Record<OrderPageTab, () => ReactNode> = {
    uebersicht: () => <OrderOverviewTab order={order} role={user?.role} />,
    arbeit: () => (
      <OrderWorkTab
        order={order}
        materials={order.materials ?? []}
        role={user?.role}
        focusSection={tab.focusSection}
        onFocusSectionDone={tab.clearFocusSection}
      />
    ),
    fotos: () => (
      <OrderPhotosTab
        orderId={order.id}
        photos={photos}
        autoCapture={tab.autoCapture}
        onAutoCaptureDone={tab.clearAutoCapture}
      />
    ),
    kunde: () => (
      <div className="order-tab-body">
        <h2 className="ui-visually-hidden">Kunde</h2>
        <Card title="Kundeninfo" headingLevel={3}>
          <KundeninfoTab orderId={order.id} customerName={customerName} initialDraft={kundeninfoDraft} />
        </Card>
        <Card title="Notizen und Kommentare" headingLevel={3}>
          <CommentsTab orderId={order.id} />
        </Card>
      </div>
    ),
    verlauf: () => (
      <div className="order-tab-body">
        <h2 className="ui-visually-hidden">Verlauf</h2>
        <OrderTimeline orderId={order.id} />
        {/* Scan-Verlauf: a section of Verlauf, the page keeps its five tabs. */}
        <Card title="Scan-Verlauf" headingLevel={3}>
          <PieceScanHistory entityType="order" entityId={order.id} />
        </Card>
      </div>
    ),
  };

  const tabItems = tab.tabs.map((id) => ({
    id,
    label: id === 'fotos' ? `Fotos (${photos.length})` : PAGE_TAB_LABELS[id],
    panel: id === tab.activeTab ? panels[id]() : undefined,
  }));

  const meta = (
    <>
      <span className="order-detail-subtitle">{order.title}</span>
      <StatusBadge kind="order" status={order.status} />
      {order.deadline && <DeadlineChip deadline={order.deadline} />}
    </>
  );

  const secondaryActions = (
    <>
      <Button
        variant="secondary"
        icon="file-text"
        onClick={() => printLabel.mutate()}
        loading={printLabel.isPending}
        title="Etikett mit QR-Code drucken"
      >
        Etikett drucken
      </Button>
      {order.customer_id && canCreateQuote && (
        <ButtonLink
          variant="secondary"
          icon="receipt"
          to={`/quotes?order_id=${order.id}&customer_id=${order.customer_id}`}
          title="Kostenvoranschlag für diesen Auftrag erstellen"
        >
          Angebot erstellen
        </ButtonLink>
      )}
    </>
  );

  return (
    <div className="order-detail-container">
      <PageHeader
        title={title}
        back={back}
        meta={meta}
        primaryAction={
          canChangeStatus ? (
            <StatusAdvanceButton
              status={order.status}
              isBusy={status.isBusy}
              isMenuOpen={tab.isStatusMenuOpen}
              onMenuOpenChange={tab.setStatusMenuOpen}
              onSelect={status.request}
            />
          ) : undefined
        }
        secondaryActions={secondaryActions}
      />
      {status.headerError && (
        <p className="order-status-error" role="alert">
          {status.headerError}
        </p>
      )}

      {milestone !== null && (
        <MilestonePrompt
          milestone={milestone}
          onAction={handleMilestoneAction}
          onDismiss={() => setMilestone(null)}
        >
          {milestone === 'delivered' && (
            <DeliveredActions
              orderId={order.id}
              price={order.price}
              role={user?.role}
              userName={[user?.first_name, user?.last_name].filter(Boolean).join(' ')}
            />
          )}
        </MilestonePrompt>
      )}

      <CostAlertBanner orderId={order.id} onCreateCostChange={() => tab.openWorkSection('kosten')} />

      <Tabs
        label="Auftragsbereiche"
        tabs={tabItems}
        selectedId={tab.activeTab}
        onSelect={(id) => tab.selectTab(id as OrderPageTab)}
        className="order-detail-tabs"
      />

      {status.dialogTarget !== null && (
        <StatusChangeDialog
          target={status.dialogTarget}
          isSubmitting={status.isBusy}
          errorMessage={status.dialogError}
          onConfirm={(request) => void status.submit(request)}
          onCancel={status.closeDialog}
        />
      )}

      {/* W2-09: hosts the PunzierungsCheckModal fired by the hallmark gate.
          ScanOverlay only mounts its own ModalStackHost while the scanner is
          open, so this page needs its own. */}
      <ModalStackHost />
    </div>
  );
}

export default OrderDetailPage;
