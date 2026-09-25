// Order detail page (W2-08; DOM-16, DOM-17, DOM-18, DOM-30).
//
// Five tabs (Übersicht, Arbeit, Fotos, Kunde, Verlauf), the next action as
// one large "Weiter: <Status>" button in the header (PATCH
// /orders/{id}/status), the order history as a real timeline, and a
// prompt at the "Fertiggestellt" / "Ausgeliefert" milestones.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ordersApi } from '../api';
import apiClient from '../api/client';
import type { MaterialType, OrderPhoto, OrderStatus } from '../types';
import { useOrders, useToast, useAuth } from '../contexts';
import { canViewDesign } from '../lib/roles';
import { CommentsTab } from '../components/CommentsTab';
import { KundeninfoTab } from '../components/orders/KundeninfoTab';
import { CostAlertBanner } from '../components/orders/CostAlertBanner';
import { parseOrderDeepLink, stripOrderDeepLink } from '../components/orders/orderDeepLink';
import { photosApi } from '../api/photos';
import { useRefetchOn } from '../lib/refetchBus';
import { logError } from '../lib/logError';
import { OrderStatusBadge } from '../components/orders/OrderStatusBadge';
import { StatusAdvanceButton } from '../components/orders/StatusAdvanceButton';
import {
  StatusChangeDialog,
  type StatusChangeRequest,
} from '../components/orders/StatusChangeDialog';
import {
  MilestonePrompt,
  buildCompletedDraft,
  type KundeninfoDraft,
  type Milestone,
} from '../components/orders/MilestonePrompt';
import { OrderTimeline } from '../components/orders/OrderTimeline';
import { OrderTabs, OrderTabPanel } from '../components/orders/OrderTabs';
import { OrderOverviewTab, type OrderWithStatusFields } from '../components/orders/OrderOverviewTab';
import { OrderWorkTab } from '../components/orders/OrderWorkTab';
import { OrderPhotosTab } from '../components/orders/OrderPhotosTab';
import {
  PAGE_TAB_ORDER,
  PAGE_TAB_STORAGE,
  resolveOrderTab,
  type OrderPageTab,
  type WorkSection,
} from '../components/orders/orderPageTabs';
import {
  canChangeOrderStatus,
  needsReason,
  statusChangeErrorMessage,
  statusLabel,
} from '../components/orders/orderStatus';
import '../styles/order-detail.css';

const MILESTONES: readonly OrderStatus[] = ['completed', 'delivered'];

export function OrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const numericId = orderId ? parseInt(orderId, 10) : NaN;
  const navigate = useNavigate();
  const { setActiveOrder, setOrderTab, getOrderTab } = useOrders();
  const { showToast } = useToast();
  const { user } = useAuth();
  // DESIGN_VIEW (SEC-09/GDPR-04): a VIEWER 403s on order photos, so the
  // Fotos tab and the photo fetch are gated on the same check as the backend.
  const canDesign = canViewDesign(user?.role);
  const canChangeStatus = canChangeOrderStatus(user?.role);

  const [order, setOrder] = useState<OrderWithStatusFields | null>(null);
  const [materials, setMaterials] = useState<MaterialType[]>([]);
  const [orderPhotos, setOrderPhotos] = useState<OrderPhoto[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [costDataVersion, setCostDataVersion] = useState(0);
  const [timelineVersion, setTimelineVersion] = useState(0);
  const [searchParams, setSearchParams] = useSearchParams();
  const [autoCapture, setAutoCapture] = useState(false);
  const [focusSection, setFocusSection] = useState<WorkSection | null>(null);
  // Status change (DOM-18)
  const [isStatusBusy, setIsStatusBusy] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [dialogTarget, setDialogTarget] = useState<OrderStatus | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [isStatusMenuOpen, setIsStatusMenuOpen] = useState(false);
  // Milestone prompt (DOM-30)
  const [milestone, setMilestone] = useState<Milestone | null>(null);
  const [kundeninfoDraft, setKundeninfoDraft] = useState<KundeninfoDraft | null>(null);
  const lastStatusRef = useRef<OrderStatus | null>(null);

  const stored = Number.isNaN(numericId) ? 'details' : getOrderTab(numericId);
  const resolved = resolveOrderTab(stored);
  const activeTab: OrderPageTab = resolved.tab === 'fotos' && !canDesign ? 'uebersicht' : resolved.tab;
  const visibleTabs = PAGE_TAB_ORDER.filter((tab) => tab !== 'fotos' || canDesign);

  /** Apply a fresh order; a move into a milestone status raises the prompt. */
  const applyOrder = useCallback(
    (next: OrderWithStatusFields) => {
      const previous = lastStatusRef.current;
      lastStatusRef.current = next.status;
      setOrder(next);
      setActiveOrder(next);
      if (next.materials) setMaterials(next.materials);
      const isNewMilestone = previous !== null && previous !== next.status && MILESTONES.includes(next.status);
      if (isNewMilestone && canChangeStatus) setMilestone(next.status as Milestone);
    },
    [canChangeStatus, setActiveOrder]
  );

  // `isSilent` refreshes in place (realtime hint): no loading screen, so
  // the open tab and a running photo upload stay mounted.
  const fetchOrder = async (id: number, { isSilent = false }: { isSilent?: boolean } = {}) => {
    try {
      if (!isSilent) setIsLoading(true);
      setError(null);
      applyOrder(await ordersApi.getById(id));
      if (canDesign) {
        try {
          const photosResponse = await photosApi.getForOrder(id);
          setOrderPhotos(photosResponse.data ?? []);
        } catch (photoErr: unknown) {
          logError('OrderDetailPage.loadPhotos', photoErr);
        }
      }
    } catch (err: unknown) {
      logError(isSilent ? 'OrderDetailPage.refetch' : 'OrderDetailPage.load', err);
      if (isSilent) return; // a failed background refresh keeps what is on screen
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Fehler beim Laden des Auftrags');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (Number.isNaN(numericId)) {
      navigate('/orders');
      return;
    }
    lastStatusRef.current = null;
    fetchOrder(numericId);
    // fetchOrder is recreated every render; only a new order id reloads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numericId]);

  // W2-13: status changes, photos and Kundeninfos from another device
  // refresh the open order and its Verlauf without a manual reload.
  useRefetchOn('orders', () => {
    if (Number.isNaN(numericId)) return;
    fetchOrder(numericId, { isSilent: true });
    setTimelineVersion((v) => v + 1);
  });

  const handleTabChange = useCallback(
    (tab: OrderPageTab) => {
      if (!Number.isNaN(numericId)) setOrderTab(numericId, PAGE_TAB_STORAGE[tab]);
    },
    [numericId, setOrderTab]
  );

  // Scanner / dashboard deep links (W2-01, FE-04), honoured once the order
  // is loaded, then dropped so a reload does not reopen the camera.
  const loadedOrderId = order?.id ?? null;
  useEffect(() => {
    if (loadedOrderId === null) return;
    const link = parseOrderDeepLink(searchParams);
    if (link === null) return;
    if (link.tab && (link.tab !== 'fotos' || canDesign)) {
      setOrderTab(loadedOrderId, link.tab);
      setFocusSection(resolveOrderTab(link.tab).section);
    }
    if (link.tab === 'status' && canChangeStatus) setIsStatusMenuOpen(true);
    if (link.capture && canDesign) setAutoCapture(true);
    setSearchParams(stripOrderDeepLink(searchParams), { replace: true });
    // setOrderTab is recreated by the context on every render; the effect
    // must only react to a new order or new params.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadedOrderId, searchParams, canDesign, canChangeStatus]);

  const handlePhotoUploaded = useCallback((photo: OrderPhoto) => {
    setOrderPhotos((prev) => [...prev, photo]);
    setTimelineVersion((v) => v + 1);
  }, []);
  const handleAutoCaptureDone = useCallback(() => setAutoCapture(false), []);
  const handleFocusSectionDone = useCallback(() => setFocusSection(null), []);

  const submitStatusChange = async (request: StatusChangeRequest) => {
    if (!order) return;
    setIsStatusBusy(true);
    setStatusError(null);
    setDialogError(null);
    try {
      applyOrder(await ordersApi.changeStatus(order.id, request));
      setDialogTarget(null);
      setTimelineVersion((v) => v + 1);
      showToast(`Status geändert: ${statusLabel(request.status)}`, 'success');
    } catch (err: unknown) {
      logError('OrderDetailPage.changeStatus', err);
      const message = statusChangeErrorMessage(err);
      if (dialogTarget !== null) setDialogError(message);
      else setStatusError(message);
    } finally {
      setIsStatusBusy(false);
    }
  };

  const requestStatusChange = (target: OrderStatus) => {
    if (needsReason(target)) {
      setDialogError(null);
      setDialogTarget(target);
      return;
    }
    void submitStatusChange({ status: target });
  };

  const handleMilestoneAction = () => {
    if (!order || milestone === null) return;
    if (milestone === 'completed') setKundeninfoDraft(buildCompletedDraft(order, orderPhotos));
    setMilestone(null);
    handleTabChange('kunde');
  };

  const handlePrintLabel = async () => {
    if (!order) return;
    try {
      const response = await apiClient.get(`/orders/${order.id}/label`, { responseType: 'blob' });
      const blob = new Blob([response.data], { type: 'text/html;charset=utf-8' });
      const blobUrl = URL.createObjectURL(blob);
      const printWindow = window.open(blobUrl, '_blank');
      if (printWindow) {
        printWindow.focus();
        printWindow.addEventListener('load', () => URL.revokeObjectURL(blobUrl));
      }
    } catch (err: unknown) {
      logError('OrderDetailPage.printLabel', err);
      showToast('Druckfehler – bitte erneut versuchen', 'error');
    }
  };

  if (isLoading) {
    return (
      <div className="page-loading" role="status">
        Wird geladen…
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="page-error">
        <p>{error || 'Auftrag nicht gefunden'}</p>
        <button onClick={() => navigate('/orders')} className="btn-primary">
          Zurück zu Aufträgen
        </button>
      </div>
    );
  }

  const customerName = order.customer
    ? `${order.customer.first_name} ${order.customer.last_name}`
    : undefined;

  return (
    <div className="order-detail-container">
      <header className="order-detail-header">
        <div className="header-left">
          <button onClick={() => navigate('/orders')} className="btn-back">
            ← Zurück
          </button>
          <div className="order-title">
            <h1>Auftrag #{order.id}</h1>
            <p className="order-subtitle">{order.title}</p>
            <OrderStatusBadge status={order.status} />
          </div>
        </div>
        <div className="header-right">
          {canChangeStatus && (
            <StatusAdvanceButton
              status={order.status}
              isBusy={isStatusBusy}
              isMenuOpen={isStatusMenuOpen}
              onMenuOpenChange={setIsStatusMenuOpen}
              onSelect={requestStatusChange}
            />
          )}
          <button className="btn-print-label" onClick={handlePrintLabel} title="Etikett mit QR-Code drucken">
            Etikett drucken
          </button>
          {order.customer_id && (
            <button
              className="btn-create-quote"
              onClick={() => navigate(`/quotes?order_id=${order.id}&customer_id=${order.customer_id}`)}
              title="Kostenvoranschlag für diesen Auftrag erstellen"
            >
              Angebot erstellen
            </button>
          )}
        </div>
        {statusError && (
          <p className="order-status-error" role="alert">
            {statusError}
          </p>
        )}
      </header>

      {milestone !== null && (
        <MilestonePrompt
          milestone={milestone}
          onAction={handleMilestoneAction}
          onDismiss={() => setMilestone(null)}
        />
      )}

      <CostAlertBanner
        orderId={order.id}
        onCreateCostChange={() => {
          handleTabChange('arbeit');
          setFocusSection('kosten');
        }}
        refreshKey={costDataVersion}
      />

      <OrderTabs
        tabs={visibleTabs}
        active={activeTab}
        onChange={handleTabChange}
        labels={{ fotos: `Fotos (${orderPhotos.length})` }}
      />

      <OrderTabPanel active={activeTab}>
        {activeTab === 'uebersicht' && <OrderOverviewTab order={order} role={user?.role} />}

        {activeTab === 'arbeit' && (
          <OrderWorkTab
            order={order}
            materials={materials}
            role={user?.role}
            focusSection={focusSection}
            onFocusSectionDone={handleFocusSectionDone}
            onOrderUpdated={applyOrder}
            onCostChangeUpdated={() => setCostDataVersion((v) => v + 1)}
          />
        )}

        {activeTab === 'fotos' && canDesign && (
          <OrderPhotosTab
            orderId={order.id}
            photos={orderPhotos}
            autoCapture={autoCapture}
            onAutoCaptureDone={handleAutoCaptureDone}
            onPhotoUploaded={handlePhotoUploaded}
          />
        )}

        {activeTab === 'kunde' && (
          <div className="tab-panel">
            <h2>Kunde</h2>
            <section className="details-section" aria-labelledby="order-kunde-info">
              <h3 id="order-kunde-info">Kundeninfo</h3>
              <KundeninfoTab orderId={order.id} customerName={customerName} initialDraft={kundeninfoDraft} />
            </section>
            <section className="details-section" aria-labelledby="order-kunde-notes">
              <h3 id="order-kunde-notes">Notizen und Kommentare</h3>
              <CommentsTab orderId={order.id} />
            </section>
          </div>
        )}

        {activeTab === 'verlauf' && (
          <div className="tab-panel">
            <h2>Verlauf</h2>
            <OrderTimeline orderId={order.id} refreshKey={timelineVersion} />
          </div>
        )}
      </OrderTabPanel>

      {dialogTarget !== null && (
        <StatusChangeDialog
          target={dialogTarget}
          isSubmitting={isStatusBusy}
          errorMessage={dialogError}
          onConfirm={(request) => void submitStatusChange(request)}
          onCancel={() => setDialogTarget(null)}
        />
      )}
    </div>
  );
}

export default OrderDetailPage;
