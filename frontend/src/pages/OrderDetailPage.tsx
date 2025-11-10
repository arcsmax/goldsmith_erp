// Order Detail Page with Tabs
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ordersApi, materialsApi } from '../api';
import { OrderType, MaterialType, OrderStatus } from '../types';
import { useOrders, OrderTab } from '../contexts';
import { CostBreakdownCard } from '../components/orders/CostBreakdownCard';
import { MetalInventoryCard } from '../components/orders/MetalInventoryCard';
import { CustomerInfoCard } from '../components/orders/CustomerInfoCard';
import '../styles/order-detail.css';

export const OrderDetailPage: React.FC = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const { setActiveOrder, setOrderTab, getOrderTab } = useOrders();

  const [order, setOrder] = useState<OrderType | null>(null);
  const [materials, setMaterials] = useState<MaterialType[]>([]);
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
      alert('Fehler beim Aktualisieren des Status: ' + err.message);
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
          className={`tab ${activeTab === 'notes' ? 'active' : ''}`}
          onClick={() => handleTabChange('notes')}
        >
          📝 Notizen
        </button>
        <button
          className={`tab ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => handleTabChange('history')}
        >
          📜 Historie
        </button>
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

        {activeTab === 'notes' && (
          <NotesTab orderId={order.id} />
        )}

        {activeTab === 'history' && (
          <HistoryTab order={order} />
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
    { value: 'new', label: 'Neu', color: '#3b82f6' },
    { value: 'in_progress', label: 'In Bearbeitung', color: '#f59e0b' },
    { value: 'completed', label: 'Fertiggestellt', color: '#10b981' },
    { value: 'delivered', label: 'Ausgeliefert', color: '#8b5cf6' },
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

const NotesTab: React.FC<{ orderId: number }> = ({ orderId }) => {
  const [notes, setNotes] = useState('');

  useEffect(() => {
    // Load notes from localStorage
    const saved = localStorage.getItem(`order_notes_${orderId}`);
    if (saved) setNotes(saved);
  }, [orderId]);

  const handleSave = () => {
    localStorage.setItem(`order_notes_${orderId}`, notes);
    alert('Notizen gespeichert!');
  };

  return (
    <div className="tab-panel">
      <h2>Notizen</h2>
      <textarea
        className="notes-textarea"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Notizen zu diesem Auftrag..."
        rows={15}
      />
      <button onClick={handleSave} className="btn-primary">
        Speichern
      </button>
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

// Helper function
const getStatusLabel = (status: string): string => {
  const labels: Record<string, string> = {
    new: 'Neu',
    in_progress: 'In Bearbeitung',
    completed: 'Fertiggestellt',
    delivered: 'Ausgeliefert',
  };
  return labels[status] || status;
};
