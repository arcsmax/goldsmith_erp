// Orders Page Component
import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ordersApi } from '../api';
import type { OrderListItem } from '../api/orders';
import { photoThumbnailPath } from '../api/photos';
import AuthenticatedImage from '../components/AuthenticatedImage';
import { useRefetchOn } from '../lib/refetchBus';
import { logError } from '../lib/logError';
import { OrderType, OrderCreateInput, OrderUpdateInput, OrderStatus } from '../types';
import { ORDER_STATUS } from '../design/status';
import { StatusBadge } from '../ui/StatusBadge';
import { formatEur, MONEY_CLASS } from '../lib/format';

// Valid order statuses accepted via the ?status=... URL parameter.
// Anything outside this set is ignored to avoid arbitrary user input
// turning into stuck "no results" filter states.
const VALID_ORDER_STATUS: ReadonlySet<OrderStatus> = new Set<OrderStatus>(
  Object.keys(ORDER_STATUS) as OrderStatus[],
);

/** Filter options: every status the backend knows, labels from status.ts. */
const STATUS_FILTER_OPTIONS = (Object.keys(ORDER_STATUS) as OrderStatus[]).map((value) => ({
  value,
  label: ORDER_STATUS[value].label,
}));
import { OrderFormModal } from '../components/orders/OrderFormModal';
import { useToast, useConfirm } from '../contexts';
import '../styles/pages.css';
import '../styles/orders.css';
// .order-list-thumb (W2-01 thumbnail column) lives with the order styles.
import '../styles/order-detail.css';

export const OrdersPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const [orders, setOrders] = useState<OrderListItem[]>([]);
  const [filteredOrders, setFilteredOrders] = useState<OrderListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isFormLoading, setIsFormLoading] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<OrderType | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  // Initialize status filter from URL ?status=... query param so deep-links
  // from the dashboard KPI cards land on the pre-filtered view.
  const [filterStatus, setFilterStatus] = useState<OrderStatus | ''>(() => {
    const fromUrl = searchParams.get('status');
    if (fromUrl && VALID_ORDER_STATUS.has(fromUrl as OrderStatus)) {
      return fromUrl as OrderStatus;
    }
    return '';
  });
  const [sortBy, setSortBy] = useState<'created' | 'deadline' | 'price'>('created');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  // Keep filter in sync when the URL changes while the page is mounted
  // (e.g., user clicks a different KPI card without unmount).
  useEffect(() => {
    const fromUrl = searchParams.get('status');
    if (fromUrl && VALID_ORDER_STATUS.has(fromUrl as OrderStatus)) {
      setFilterStatus(fromUrl as OrderStatus);
    } else if (!fromUrl) {
      setFilterStatus('');
    }
  }, [searchParams]);

  useEffect(() => {
    fetchOrders();
  }, []);

  // W2-13: a status change or new order on another device refreshes the
  // list in place (no spinner, filters and page kept).
  useRefetchOn('orders', () => {
    fetchOrders({ isSilent: true });
  });

  useEffect(() => {
    filterAndSortOrders();
  }, [orders, searchQuery, filterStatus, sortBy]);

  const fetchOrders = async ({ isSilent = false }: { isSilent?: boolean } = {}) => {
    try {
      if (!isSilent) setIsLoading(true);
      setError(null);
      const data = await ordersApi.getAll();
      setOrders(data);
    } catch (err: any) {
      // A failed background refresh keeps the list that is on screen.
      if (isSilent) {
        logError('OrdersPage.refetch', err);
        return;
      }
      setError(err.response?.data?.detail || 'Fehler beim Laden der Aufträge');
    } finally {
      setIsLoading(false);
    }
  };

  const filterAndSortOrders = () => {
    let filtered = [...orders];

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (o) =>
          o.title.toLowerCase().includes(query) ||
          o.description.toLowerCase().includes(query) ||
          o.id.toString().includes(query)
      );
    }

    // Status filter
    if (filterStatus) {
      filtered = filtered.filter((o) => o.status === filterStatus);
    }

    // Sort
    filtered.sort((a, b) => {
      if (sortBy === 'created') {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      } else if (sortBy === 'deadline') {
        const aDate = a.deadline ? new Date(a.deadline).getTime() : Infinity;
        const bDate = b.deadline ? new Date(b.deadline).getTime() : Infinity;
        return aDate - bDate;
      } else if (sortBy === 'price') {
        return (b.price || 0) - (a.price || 0);
      }
      return 0;
    });

    setFilteredOrders(filtered);
  };

  const handleCreateOrder = async (data: OrderCreateInput) => {
    try {
      setIsFormLoading(true);
      const newOrder = await ordersApi.create(data);
      await fetchOrders();
      setIsModalOpen(false);
      if (newOrder.has_scrap_gold) {
        showToast(
          'Altgold-Erfassung ausstehend — bitte im Auftrag die Altgold-Daten eingeben',
          'warning'
        );
        navigate(`/orders/${newOrder.id}`);
      } else {
        showToast('Auftrag erfolgreich erstellt!', 'success');
      }
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Erstellen des Auftrags', 'error');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleUpdateOrder = async (data: OrderUpdateInput) => {
    if (!selectedOrder) return;

    try {
      setIsFormLoading(true);
      await ordersApi.update(selectedOrder.id, data);
      await fetchOrders();
      setIsModalOpen(false);
      setSelectedOrder(null);
      showToast('Auftrag erfolgreich aktualisiert!', 'success');
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Aktualisieren des Auftrags', 'error');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleDeleteOrder = async (orderId: number, orderTitle: string) => {
    const confirmed = await showConfirm({
      title: 'Auftrag löschen',
      message: `Möchten Sie den Auftrag „${orderTitle}“ wirklich löschen?`,
      confirmLabel: 'Löschen',
      variant: 'danger',
    });

    if (!confirmed) return;

    try {
      await ordersApi.delete(orderId);
      await fetchOrders();
      showToast('Auftrag gelöscht', 'success');
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Löschen des Auftrags', 'error');
    }
  };

  const openCreateModal = () => {
    setSelectedOrder(null);
    setIsModalOpen(true);
  };

  const openEditModal = (order: OrderType, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedOrder(order);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedOrder(null);
  };

  const handleFormSubmit = async (data: OrderCreateInput | OrderUpdateInput) => {
    if (selectedOrder) {
      await handleUpdateOrder(data);
    } else {
      await handleCreateOrder(data as OrderCreateInput);
    }
  };

  if (isLoading) {
    return <div className="page-loading">Aufträge werden geladen…</div>;
  }

  if (error) {
    return <div className="page-error">{error}</div>;
  }

  // Pagination
  const totalPages = Math.ceil(filteredOrders.length / pageSize);
  const paginatedOrders = filteredOrders.slice(
    page * pageSize,
    (page + 1) * pageSize
  );

  const totalRevenue = filteredOrders.reduce((sum, o) => sum + (o.price || 0), 0);

  return (
    <div className="page-container">
      <header className="page-header">
        <div>
          <h1>Aufträge</h1>
          <p className="orders-page-summary">
            {filteredOrders.length} Aufträge • Gesamtwert:{' '}
            <span className={MONEY_CLASS}>{formatEur(totalRevenue)}</span>
          </p>
        </div>
        <button className="btn-primary" onClick={openCreateModal}>
          + Neuer Auftrag
        </button>
      </header>

      {/* Search and Filters */}
      <div className="orders-controls">
        <div className="search-box">
          <input
            type="search"
            className="orders-search-input"
            aria-label="Aufträge durchsuchen"
            placeholder="Titel, Beschreibung oder Nr. …"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <label>Status:</label>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as OrderStatus | '')}
          >
            <option value="">Alle</option>
            {STATUS_FILTER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>Sortieren:</label>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value as any)}>
            <option value="created">Erstelldatum</option>
            <option value="deadline">Frist</option>
            <option value="price">Preis</option>
          </select>
        </div>

        <div className="filter-group">
          <label>Pro Seite:</label>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPage(0);
            }}
          >
            <option value="25">25</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </div>
      </div>

      {filteredOrders.length === 0 ? (
        <div className="empty-state">
          <p>
            {searchQuery || filterStatus
              ? 'Keine Aufträge gefunden.'
              : 'Keine Aufträge vorhanden.'}
          </p>
        </div>
      ) : (
        <>
          <div className="table-container orders-table-container">
            <table className="orders-table">
              <thead>
                <tr>
                  <th className="order-list-thumb-cell">Foto</th>
                  <th>ID</th>
                  <th>Titel</th>
                  <th className="orders-col-description">Beschreibung</th>
                  <th>Status</th>
                  <th>Preis</th>
                  <th>Frist</th>
                  <th>Erstellt</th>
                  <th>Aktionen</th>
                </tr>
              </thead>
              <tbody>
                {paginatedOrders.map((order) => (
                  <tr
                    key={order.id}
                    onClick={() => navigate(`/orders/${order.id}`)}
                  >
                    <td className="order-list-thumb-cell">
                      {order.first_photo_id && (
                        <AuthenticatedImage
                          src={photoThumbnailPath(order.first_photo_id)}
                          alt={`Foto zu ${order.title}`}
                          className="order-list-thumb"
                        />
                      )}
                    </td>
                    <td>#{order.id}</td>
                    <td>{order.title}</td>
                    <td className="orders-col-description">
                      <span className="orders-description-clamp">{order.description ?? ''}</span>
                    </td>
                    <td>
                      <StatusBadge kind="order" status={order.status} />
                    </td>
                    <td className={MONEY_CLASS}>
                      {order.price ? (
                        <span className="price-display">{formatEur(order.price)}</span>
                      ) : (
                        <span className="price-calculated">Wird berechnet</span>
                      )}
                    </td>
                    <td className="orders-col-date">
                      {order.deadline
                        ? new Date(order.deadline).toLocaleDateString('de-DE')
                        : '—'}
                    </td>
                    <td className="orders-col-date">
                      {new Date(order.created_at).toLocaleDateString('de-DE')}
                    </td>
                    <td>
                      <div className="orders-page-actions">
                        <button
                          className="btn-icon btn-edit"
                          onClick={(e) => openEditModal(order, e)}
                          title="Bearbeiten"
                        >
                          ✏️
                        </button>
                        <button
                          className="btn-icon btn-delete"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteOrder(order.id, order.title);
                          }}
                          title="Löschen"
                        >
                          🗑️
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination-controls">
              <div className="pagination-info">
                Seite {page + 1} von {totalPages} • {filteredOrders.length} Aufträge
              </div>
              <div className="pagination-buttons">
                <button onClick={() => setPage(0)} disabled={page === 0}>
                  ‹‹ Erste
                </button>
                <button onClick={() => setPage(page - 1)} disabled={page === 0}>
                  ‹ Zurück
                </button>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={page >= totalPages - 1}
                >
                  Weiter ›
                </button>
                <button
                  onClick={() => setPage(totalPages - 1)}
                  disabled={page >= totalPages - 1}
                >
                  Letzte ››
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Order Form Modal */}
      <OrderFormModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onSubmit={handleFormSubmit}
        order={selectedOrder}
        isLoading={isFormLoading}
      />
    </div>
  );
};
