// Order Detail Page with Tabs
import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ordersApi, materialsApi } from '../api';
import apiClient from '../api/client';
import { OrderType, MaterialType, OrderStatus, OrderPhoto } from '../types';
import { useOrders, OrderTab, useToast, useAuth } from '../contexts';
import { canViewDesign, canViewFinancials } from '../lib/roles';
import TimeTrackingTab from '../components/TimeTrackingTab';
import { CommentsTab } from '../components/CommentsTab';
import { ScrapGoldTab } from '../components/scrap-gold';
import { CostBreakdownCard } from '../components/orders/CostBreakdownCard';
import { MetalInventoryCard } from '../components/orders/MetalInventoryCard';
import { CustomerInfoCard } from '../components/orders/CustomerInfoCard';
import { SollIstTab } from '../components/orders/SollIstTab';
import HandoffTab from '../components/orders/HandoffTab';
import ArbeitszettelTab from '../components/orders/ArbeitszettelTab';
import { KundeninfoTab } from '../components/orders/KundeninfoTab';
import { CostAlertBanner } from '../components/orders/CostAlertBanner';
import { CostChangeSection } from '../components/orders/CostChangeSection';
import { PhotoCompare, type PhotoItem } from '../components/PhotoCompare';
import { PhotoUpload } from '../components/orders/PhotoUpload';
import { parseOrderDeepLink, stripOrderDeepLink } from '../components/orders/orderDeepLink';
import { photoFilePath, photoThumbnailPath, photosApi } from '../api/photos';
import { useRefetchOn } from '../lib/refetchBus';
import { logError } from '../lib/logError';
import '../styles/order-detail.css';

export const OrderDetailPage: React.FC = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const { setActiveOrder, setOrderTab, getOrderTab } = useOrders();
  const { showToast } = useToast();
  const { user } = useAuth();
  // DESIGN_VIEW / FINANCIAL_VIEW (SEC-09/GDPR-04, SEC-01): a VIEWER 403s on
  // order photos and on the Soll/Ist comparison, and the order object
  // itself arrives with description/special_instructions/price/nested
  // materials[].unit_price stripped (GDPR-03) — gate the fetch, the tabs,
  // and the affected fields on the same two checks the backend uses.
  const canDesign = canViewDesign(user?.role);
  const canFinance = canViewFinancials(user?.role);

  const [order, setOrder] = useState<OrderType | null>(null);
  const [materials, setMaterials] = useState<MaterialType[]>([]);
  const [orderPhotos, setOrderPhotos] = useState<OrderPhoto[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Bumped whenever a §649 cost-change action (create/send/record-response)
  // may have changed the projected cost, so CostAlertBanner re-fetches
  // without needing orderId to change.
  const [costDataVersion, setCostDataVersion] = useState(0);
  // Scanner deep link (?tab=fotos&capture=1): open the camera once.
  const [searchParams, setSearchParams] = useSearchParams();
  const [autoCapture, setAutoCapture] = useState(false);

  // Get active tab from context (remembers last tab)
  const activeTab = orderId ? getOrderTab(parseInt(orderId)) : 'details';

  useEffect(() => {
    if (!orderId) {
      navigate('/orders');
      return;
    }

    fetchOrder(parseInt(orderId));
  }, [orderId]);

  // `isSilent` refreshes in place (realtime hint): no loading screen, so
  // the open tab and a running photo upload stay mounted.
  const fetchOrder = async (id: number, { isSilent = false }: { isSilent?: boolean } = {}) => {
    try {
      if (!isSilent) setIsLoading(true);
      setError(null);
      const orderData = await ordersApi.getById(id);
      setOrder(orderData);
      setActiveOrder(orderData); // Register in context

      // Load materials if available
      if (orderData.materials && orderData.materials.length > 0) {
        setMaterials(orderData.materials);
      }

      // Load order photos (best-effort — don't block page render on
      // failure). DESIGN_VIEW: /orders/{id}/photos 403s for a caller
      // without it, so skip the call entirely rather than triggering it.
      if (canDesign) {
        try {
          const photosResponse = await photosApi.getForOrder(id);
          setOrderPhotos(photosResponse.data ?? []);
        } catch (photoErr: unknown) {
          // Non-critical for the page, but never silent.
          logError('OrderDetailPage.loadPhotos', photoErr);
        }
      }
    } catch (err: any) {
      // A failed background refresh keeps the order that is on screen.
      if (isSilent) {
        logError('OrderDetailPage.refetch', err);
        return;
      }
      setError(err.response?.data?.detail || 'Fehler beim Laden des Auftrags');
    } finally {
      setIsLoading(false);
    }
  };

  // W2-13: status changes and new photos from another device refresh the
  // open order without a manual reload.
  useRefetchOn('orders', () => {
    if (orderId) fetchOrder(parseInt(orderId), { isSilent: true });
  });

  const handleTabChange = (tab: OrderTab) => {
    if (orderId) {
      setOrderTab(parseInt(orderId), tab);
    }
  };

  // W2-01 / FE-04: honour scanner deep links once the order is loaded
  // (after fetchOrder's setActiveOrder has set its default tab), then drop
  // the params so a reload does not reopen the camera. Photos are
  // DESIGN_VIEW: a caller without it never gets the Fotos tab or camera.
  const loadedOrderId = order?.id ?? null;
  useEffect(() => {
    if (loadedOrderId === null) return;
    const link = parseOrderDeepLink(searchParams);
    if (link === null) return;
    const isPhotoTab = link.tab === 'fotos';
    if (link.tab && (!isPhotoTab || canDesign)) {
      setOrderTab(loadedOrderId, link.tab);
    }
    if (link.capture && canDesign) {
      setAutoCapture(true);
    }
    setSearchParams(stripOrderDeepLink(searchParams), { replace: true });
    // setOrderTab is recreated by the context on every render; the effect
    // must only react to a new order or new params.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadedOrderId, searchParams, canDesign]);

  const handlePhotoUploaded = useCallback((photo: OrderPhoto) => {
    setOrderPhotos((prev) => [...prev, photo]);
  }, []);

  const handleAutoCaptureDone = useCallback(() => setAutoCapture(false), []);

  const handleStatusChange = async (newStatus: OrderStatus) => {
    if (!order) return;

    try {
      const updated = await ordersApi.update(order.id, { status: newStatus });
      setOrder(updated);
      setActiveOrder(updated);
    } catch (err: any) {
      showToast('Fehler beim Aktualisieren des Status: ' + err.message, 'error');
    }
  };

  const handlePrintLabel = async () => {
    if (!order) return;
    try {
      const response = await apiClient.get(`/orders/${order.id}/label`, {
        responseType: 'blob',
      });
      const blob = new Blob([response.data], { type: 'text/html;charset=utf-8' });
      const blobUrl = URL.createObjectURL(blob);
      const printWindow = window.open(blobUrl, '_blank');
      if (printWindow) {
        printWindow.focus();
        // Free memory once the tab has loaded the blob
        printWindow.addEventListener('load', () => URL.revokeObjectURL(blobUrl));
      }
    } catch {
      showToast('Druckfehler – bitte erneut versuchen', 'error');
    }
  };

  if (isLoading) {
    return <div className="page-loading">Lade Auftrag...</div>;
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

  return (
    <div className="order-detail-container">
      {/* Header */}
      <header className="order-detail-header">
        <div className="header-left">
          <button onClick={() => navigate('/orders')} className="btn-back">
            ← Zurück
          </button>
          <div className="order-title">
            <h1>Auftrag #{order.id}</h1>
            <p className="order-subtitle">{order.title}</p>
          </div>
        </div>
        <div className="header-right">
          <button
            className="btn-print-label"
            onClick={handlePrintLabel}
            title="Etikett mit QR-Code drucken"
          >
            Etikett drucken
          </button>
          {order.customer_id && (
            <button
              className="btn-create-quote"
              onClick={() => navigate(`/quotes?order_id=${order.id}&customer_id=${order.customer_id}`)}
              title="Kostenvoranschlag fuer diesen Auftrag erstellen"
            >
              Angebot erstellen
            </button>
          )}
          <span className={`status-badge status-${order.status}`}>
            {getStatusLabel(order.status)}
          </span>
        </div>
      </header>

      <CostAlertBanner
        orderId={order.id}
        onCreateCostChange={() => handleTabChange('kosten')}
        refreshKey={costDataVersion}
      />

      {/* Tabs */}
      <div className="order-tabs">
        <button
          className={`tab ${activeTab === 'details' ? 'active' : ''}`}
          onClick={() => handleTabChange('details')}
        >
          📋 Details
        </button>
        {canFinance && (
          <button
            className={`tab ${activeTab === 'kosten' ? 'active' : ''}`}
            onClick={() => handleTabChange('kosten')}
          >
            💰 Kosten
          </button>
        )}
        {order.metal_type && (
          <button
            className={`tab ${activeTab === 'metall' ? 'active' : ''}`}
            onClick={() => handleTabChange('metall')}
          >
            🥇 Metall
          </button>
        )}
        <button
          className={`tab ${activeTab === 'materials' ? 'active' : ''}`}
          onClick={() => handleTabChange('materials')}
        >
          💎 Materialien
        </button>
        <button
          className={`tab ${activeTab === 'status' ? 'active' : ''}`}
          onClick={() => handleTabChange('status')}
        >
          🔄 Status
        </button>
        <button
          className={`tab ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => handleTabChange('history')}
        >
          📜 Historie
        </button>
        <button
          className={`tab ${activeTab === 'time-tracking' ? 'active' : ''}`}
          onClick={() => handleTabChange('time-tracking')}
        >
          ⏱️ Zeiterfassung
        </button>
        <button
          className={`tab ${activeTab === 'comments' ? 'active' : ''}`}
          onClick={() => handleTabChange('comments')}
        >
          📝 Notizen & Kommentare
        </button>
        <button
          className={`tab ${activeTab === 'scrap-gold' ? 'active' : ''}`}
          onClick={() => handleTabChange('scrap-gold')}
        >
          🥇 Altgold
        </button>
        {canDesign && (
          <button
            className={`tab ${activeTab === 'fotos' ? 'active' : ''}`}
            onClick={() => handleTabChange('fotos')}
          >
            Fotos ({orderPhotos.length})
          </button>
        )}
        <button
          className={`tab ${activeTab === 'handoff' ? 'active' : ''}`}
          onClick={() => handleTabChange('handoff')}
        >
          🤝 Übergabe
        </button>
        <button
          className={`tab ${activeTab === 'kundeninfo' ? 'active' : ''}`}
          onClick={() => handleTabChange('kundeninfo')}
        >
          👤 Kundeninfo
        </button>
        {order.status !== 'draft' && (
          <button
            className={`tab ${activeTab === 'arbeitszettel' ? 'active' : ''}`}
            onClick={() => handleTabChange('arbeitszettel')}
          >
            🔧 Arbeitszettel
          </button>
        )}
        {canFinance && (order.status === 'completed' || order.status === 'delivered') && (
          <button
            className={`tab ${activeTab === 'soll-ist' ? 'active' : ''}`}
            onClick={() => handleTabChange('soll-ist')}
          >
            📊 Soll/Ist
          </button>
        )}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'details' && (
          <DetailsTab order={order} />
        )}

        {activeTab === 'kosten' && canFinance && (
          <CostsTab
            order={order}
            onCostChangeUpdated={() => setCostDataVersion((v) => v + 1)}
          />
        )}

        {activeTab === 'metall' && order.metal_type && (
          <MetalTab order={order} />
        )}

        {activeTab === 'materials' && (
          <MaterialsTab materials={materials} orderId={order.id} />
        )}

        {activeTab === 'status' && (
          <StatusTab order={order} onStatusChange={handleStatusChange} />
        )}

        {activeTab === 'history' && (
          <HistoryTab order={order} />
        )}

        {activeTab === 'time-tracking' && (
          <TimeTrackingTab orderId={order.id} />
        )}

        {activeTab === 'comments' && (
          <CommentsTab orderId={order.id} />
        )}

        {activeTab === 'scrap-gold' && (
          <ScrapGoldTab orderId={order.id} customerId={order.customer_id} />
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

        {activeTab === 'handoff' && (
          <HandoffTab orderId={order.id} />
        )}

        {activeTab === 'kundeninfo' && (
          <KundeninfoTab
            orderId={order.id}
            customerName={
              order.customer
                ? `${order.customer.first_name} ${order.customer.last_name}`
                : undefined
            }
          />
        )}

        {activeTab === 'arbeitszettel' && (
          <ArbeitszettelTab
            order={order}
            onOrderUpdated={(updated) => {
              setOrder(updated);
              setActiveOrder(updated);
            }}
          />
        )}

        {activeTab === 'soll-ist' && canFinance && (
          <SollIstTab orderId={order.id} orderStatus={order.status} />
        )}
      </div>
    </div>
  );
};

// Tab Components

const DetailsTab: React.FC<{ order: OrderType }> = ({ order }) => {
  const { user } = useAuth();
  const canDesign = canViewDesign(user?.role);
  const canFinance = canViewFinancials(user?.role);

  return (
  <div className="tab-panel">
    <h2>Auftragsdetails</h2>

    {/* Customer Info Section */}
    <div className="details-section">
      <h3>Kunde</h3>
      <CustomerInfoCard customerId={order.customer_id} />
    </div>

    {/* Order Details Section */}
    <div className="details-section">
      <h3>Auftragsinformationen</h3>
      <div className="detail-grid">
        <div className="detail-item">
          <label>Auftragsnummer:</label>
          <span>#{order.id}</span>
        </div>
        <div className="detail-item">
          <label>Titel:</label>
          <span>{order.title}</span>
        </div>
        {/* DESIGN_VIEW (GDPR-04): `description` is stripped from the
            response for a caller without it — omit the row rather than
            show an empty value next to the label. */}
        {canDesign && (
          <div className="detail-item">
            <label>Beschreibung:</label>
            <span>{order.description || '—'}</span>
          </div>
        )}
        {/* FINANCIAL_VIEW (SEC-01): `price` is stripped for a caller
            without it — omit the row rather than misreport it as
            "Nicht festgelegt" (not set). */}
        {canFinance && (
          <div className="detail-item">
            <label>Preis:</label>
            <span>{order.price ? `${order.price.toFixed(2)} €` : 'Nicht festgelegt'}</span>
          </div>
        )}
        {order.deadline && (
          <div className="detail-item">
            <label>Deadline:</label>
            <span>{new Date(order.deadline).toLocaleString('de-DE')}</span>
          </div>
        )}
        {order.current_location && (
          <div className="detail-item">
            <label>Standort:</label>
            <span>{order.current_location}</span>
          </div>
        )}
        <div className="detail-item">
          <label>Erstellt:</label>
          <span>{new Date(order.created_at).toLocaleString('de-DE')}</span>
        </div>
        <div className="detail-item">
          <label>Aktualisiert:</label>
          <span>{new Date(order.updated_at).toLocaleString('de-DE')}</span>
        </div>
      </div>
    </div>
  </div>
  );
};

const CostsTab: React.FC<{ order: OrderType; onCostChangeUpdated: () => void }> = ({
  order,
  onCostChangeUpdated,
}) => (
  <div className="tab-panel">
    <h2>Kostenaufstellung</h2>
    <CostBreakdownCard order={order} />
    <CostChangeSection orderId={order.id} onChanged={onCostChangeUpdated} />
  </div>
);

const MetalTab: React.FC<{ order: OrderType }> = ({ order }) => (
  <div className="tab-panel">
    <h2>Metallinformationen</h2>
    <MetalInventoryCard order={order} />
  </div>
);

const MaterialsTab: React.FC<{ materials: MaterialType[]; orderId: number }> = ({
  materials,
}) => {
  const { user } = useAuth();
  // FINANCIAL_VIEW (GDPR-03): the backend strips `unit_price` from every
  // item in `order.materials[]` for a caller without it — the column is
  // omitted rather than crashing on `undefined.toFixed(...)`.
  const canFinance = canViewFinancials(user?.role);

  return (
    <div className="tab-panel">
      <h2>Verwendete Materialien</h2>
      {materials.length === 0 ? (
        <p className="empty-message">Keine Materialien zugeordnet.</p>
      ) : (
        <table className="materials-table">
          <thead>
            <tr>
              <th>Material</th>
              <th>Beschreibung</th>
              {canFinance && <th>Preis/Einheit</th>}
              <th>Einheit</th>
            </tr>
          </thead>
          <tbody>
            {materials.map((material) => (
              <tr key={material.id}>
                <td>{material.name}</td>
                <td>{material.description || '-'}</td>
                {canFinance && (
                  <td>{material.unit_price != null ? `${material.unit_price.toFixed(2)} €` : '—'}</td>
                )}
                <td>{material.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

const StatusTab: React.FC<{
  order: OrderType;
  onStatusChange: (status: OrderStatus) => void;
}> = ({ order, onStatusChange }) => {
  const statuses: { value: OrderStatus; label: string; color: string }[] = [
    { value: 'draft', label: 'Entwurf', color: '#9ca3af' },
    { value: 'confirmed', label: 'Bestätigt', color: '#3b82f6' },
    { value: 'in_progress', label: 'In Bearbeitung', color: '#f59e0b' },
    { value: 'waiting_for_fitting', label: 'Wartet auf Anprobe', color: '#f97316' },
    { value: 'fitting_done', label: 'Anprobe abgeschlossen', color: '#eab308' },
    { value: 'ready_for_setting', label: 'Bereit für Steinbesatz', color: '#06b6d4' },
    { value: 'quality_check', label: 'Endkontrolle', color: '#8b5cf6' },
    { value: 'completed', label: 'Fertiggestellt', color: '#10b981' },
    { value: 'delivered', label: 'Ausgeliefert', color: '#6366f1' },
  ];

  return (
    <div className="tab-panel">
      <h2>Status ändern</h2>
      <p className="status-info">
        Aktueller Status:{' '}
        <span className={`status-badge status-${order.status}`}>
          {getStatusLabel(order.status)}
        </span>
      </p>
      <div className="status-buttons">
        {statuses.map((status) => (
          <button
            key={status.value}
            className={`status-btn ${order.status === status.value ? 'active' : ''}`}
            style={{ borderColor: status.color }}
            onClick={() => onStatusChange(status.value)}
            disabled={order.status === status.value}
          >
            {status.label}
          </button>
        ))}
      </div>
    </div>
  );
};

const HistoryTab: React.FC<{ order: OrderType }> = ({ order }) => (
  <div className="tab-panel">
    <h2>Auftragsverlauf</h2>
    <div className="timeline">
      <div className="timeline-item">
        <div className="timeline-marker"></div>
        <div className="timeline-content">
          <p className="timeline-date">
            {new Date(order.created_at).toLocaleString('de-DE')}
          </p>
          <p>Auftrag erstellt</p>
        </div>
      </div>
      <div className="timeline-item">
        <div className="timeline-marker"></div>
        <div className="timeline-content">
          <p className="timeline-date">
            {new Date(order.updated_at).toLocaleString('de-DE')}
          </p>
          <p>Zuletzt aktualisiert</p>
        </div>
      </div>
    </div>
  </div>
);

// ─── Fotos tab ────────────────────────────────────────────────────────────────

/** Order photos → PhotoCompare items: stable keys, authenticated URLs. */
function toOrderPhotoItem(photo: OrderPhoto, index: number): PhotoItem {
  return {
    id: index + 1,
    renderKey: photo.id,
    file_path: photo.file_path,
    notes: photo.notes,
    timestamp: photo.timestamp,
    thumbSrc: photoThumbnailPath(photo.id),
    fullSrc: photoFilePath(photo.id),
  };
}

interface OrderPhotosTabProps {
  orderId: number;
  photos: OrderPhoto[];
  autoCapture: boolean;
  onAutoCaptureDone: () => void;
  onPhotoUploaded: (photo: OrderPhoto) => void;
}

const OrderPhotosTab: React.FC<OrderPhotosTabProps> = ({
  orderId,
  photos,
  autoCapture,
  onAutoCaptureDone,
  onPhotoUploaded,
}) => {
  const photoItems = photos.map(toOrderPhotoItem);

  return (
    <div className="tab-panel order-photos-panel">
      <h2>Auftragsdokumentationen</h2>
      <PhotoUpload
        orderId={orderId}
        onUploaded={onPhotoUploaded}
        autoOpen={autoCapture}
        onAutoOpened={onAutoCaptureDone}
      />
      <PhotoCompare
        beforePhotos={[]}
        afterPhotos={[]}
        gridMode
        allPhotos={photoItems}
      />
    </div>
  );
};

// Helper function
const getStatusLabel = (status: string): string => {
  const labels: Record<string, string> = {
    new: 'Neu',
    draft: 'Entwurf',
    confirmed: 'Bestätigt',
    in_progress: 'In Bearbeitung',
    waiting_for_fitting: 'Wartet auf Anprobe',
    fitting_done: 'Anprobe abgeschlossen',
    ready_for_setting: 'Bereit für Steinbesatz',
    quality_check: 'Endkontrolle',
    completed: 'Fertiggestellt',
    delivered: 'Ausgeliefert',
  };
  return labels[status] || status;
};
