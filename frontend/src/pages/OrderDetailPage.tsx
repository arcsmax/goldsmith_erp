// Order Detail Page with Tabs
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ordersApi, materialsApi } from '../api';
import { OrderType, MaterialType, OrderStatus, OrderPhoto } from '../types';
import { useOrders, OrderTab, useToast } from '../contexts';
import TimeTrackingTab from '../components/TimeTrackingTab';
import { CommentsTab } from '../components/CommentsTab';
import { ScrapGoldTab } from '../components/scrap-gold';
import { CostBreakdownCard } from '../components/orders/CostBreakdownCard';
import { MetalInventoryCard } from '../components/orders/MetalInventoryCard';
import { CustomerInfoCard } from '../components/orders/CustomerInfoCard';
import { SollIstTab } from '../components/orders/SollIstTab';
import HandoffTab from '../components/orders/HandoffTab';
import ArbeitszettelTab from '../components/orders/ArbeitszettelTab';
import { PhotoCompare } from '../components/PhotoCompare';
import { photosApi } from '../api/photos';
import '../styles/order-detail.css';

export const OrderDetailPage: React.FC = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const { setActiveOrder, setOrderTab, getOrderTab } = useOrders();
  const { showToast } = useToast();

  const [order, setOrder] = useState<OrderType | null>(null);
  const [materials, setMaterials] = useState<MaterialType[]>([]);
  const [orderPhotos, setOrderPhotos] = useState<OrderPhoto[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Get active tab from context (remembers last tab)
  const activeTab = orderId ? getOrderTab(parseInt(orderId)) : 'details';

  useEffect(() => {
    if (!orderId) {
      navigate('/orders');
      return;
    }

    fetchOrder(parseInt(orderId));
  }, [orderId]);

  const fetchOrder = async (id: number) => {
    try {
      setIsLoading(true);
      setError(null);
      const orderData = await ordersApi.getById(id);
      setOrder(orderData);
      setActiveOrder(orderData); // Register in context

      // Load materials if available
      if (orderData.materials && orderData.materials.length > 0) {
        setMaterials(orderData.materials);
      }

      // Load order photos (best-effort — don't block page render on failure)
      try {
        const photosResponse = await photosApi.getForOrder(id);
        setOrderPhotos(photosResponse.data ?? []);
      } catch {
        // Photo loading failure is non-critical; silently ignore
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden des Auftrags');
    } finally {
      setIsLoading(false);
    }
  };

  const handleTabChange = (tab: OrderTab) => {
    if (orderId) {
      setOrderTab(parseInt(orderId), tab);
    }
  };

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
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/v1/orders/${order.id}/label`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        showToast('Etikett konnte nicht geladen werden', 'error');
        return;
      }
      const html = await response.text();
      // Use a Blob URL so the label HTML loads into a new tab cleanly —
      // the content comes exclusively from our authenticated API endpoint.
      const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
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

      {/* Tabs */}
      <div className="order-tabs">
        <button
          className={`tab ${activeTab === 'details' ? 'active' : ''}`}
          onClick={() => handleTabChange('details')}
        >
          📋 Details
        </button>
        <button
          className={`tab ${activeTab === 'kosten' ? 'active' : ''}`}
          onClick={() => handleTabChange('kosten')}
        >
          💰 Kosten
        </button>
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
        <button
          className={`tab ${activeTab === 'fotos' ? 'active' : ''}`}
          onClick={() => handleTabChange('fotos')}
        >
          Fotos ({orderPhotos.length})
        </button>
        <button
          className={`tab ${activeTab === 'handoff' ? 'active' : ''}`}
          onClick={() => handleTabChange('handoff')}
        >
          🤝 Übergabe
        </button>
        {order.status !== 'draft' && (
          <button
            className={`tab ${activeTab === 'arbeitszettel' ? 'active' : ''}`}
            onClick={() => handleTabChange('arbeitszettel')}
          >
            🔧 Arbeitszettel
          </button>
        )}
        {(order.status === 'completed' || order.status === 'delivered') && (
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

        {activeTab === 'kosten' && (
          <CostsTab order={order} />
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

        {activeTab === 'fotos' && (
          <OrderPhotosTab photos={orderPhotos} />
        )}

        {activeTab === 'handoff' && (
          <HandoffTab orderId={order.id} />
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

        {activeTab === 'soll-ist' && (
          <SollIstTab orderId={order.id} orderStatus={order.status} />
        )}
      </div>
    </div>
  );
};

// Tab Components

const DetailsTab: React.FC<{ order: OrderType }> = ({ order }) => (
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
        <div className="detail-item">
          <label>Beschreibung:</label>
          <span>{order.description}</span>
        </div>
        <div className="detail-item">
          <label>Preis:</label>
          <span>{order.price ? `${order.price.toFixed(2)} €` : 'Nicht festgelegt'}</span>
        </div>
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

const CostsTab: React.FC<{ order: OrderType }> = ({ order }) => (
  <div className="tab-panel">
    <h2>Kostenaufstellung</h2>
    <CostBreakdownCard order={order} />
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
  orderId,
}) => (
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
            <th>Preis/Einheit</th>
            <th>Einheit</th>
          </tr>
        </thead>
        <tbody>
          {materials.map((material) => (
            <tr key={material.id}>
              <td>{material.name}</td>
              <td>{material.description || '-'}</td>
              <td>{material.unit_price.toFixed(2)} €</td>
              <td>{material.unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </div>
);

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

const OrderPhotosTab: React.FC<{ photos: OrderPhoto[] }> = ({ photos }) => {
  const photoItems = photos.map(p => ({
    id: Number(p.id.replace(/-/g, '').slice(0, 8)) || Math.random(),
    file_path: p.file_path,
    notes: p.notes,
    timestamp: p.timestamp,
  }));

  return (
    <div className="tab-panel">
      <h2>Auftragsdokumentationen</h2>
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
