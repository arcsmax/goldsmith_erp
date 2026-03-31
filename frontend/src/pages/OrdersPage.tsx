// Orders Page Component
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ordersApi } from '../api';
import { OrderType, OrderCreateInput, OrderUpdateInput, OrderStatus } from '../types';
import { OrderFormModal } from '../components/orders/OrderFormModal';
import '../styles/pages.css';
import '../styles/orders.css';

export const OrdersPage: React.FC = () => {
  const navigate = useNavigate();
  const [orders, setOrders] = useState<OrderType[]>([]);
  const [filteredOrders, setFilteredOrders] = useState<OrderType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isFormLoading, setIsFormLoading] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<OrderType | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<OrderStatus | ''>('');
  const [sortBy, setSortBy] = useState<'created' | 'deadline' | 'price'>('created');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  useEffect(() => {
    fetchOrders();
  }, []);

  useEffect(() => {
    filterAndSortOrders();
  }, [orders, searchQuery, filterStatus, sortBy]);

  const fetchOrders = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await ordersApi.getAll();
      setOrders(data);
    } catch (err: any) {
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
      await ordersApi.create(data);
      await fetchOrders();
      setIsModalOpen(false);
      alert('Auftrag erfolgreich erstellt!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Erstellen des Auftrags');
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
      alert('Auftrag erfolgreich aktualisiert!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Aktualisieren des Auftrags');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleDeleteOrder = async (orderId: number, orderTitle: string) => {
    const confirmed = window.confirm(
      `Möchten Sie den Auftrag "${orderTitle}" wirklich löschen?`
    );

    if (!confirmed) return;

    try {
      await ordersApi.delete(orderId);
      await fetchOrders();
      alert('Auftrag erfolgreich gelöscht!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Löschen des Auftrags');
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

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      new: 'Neu',
      in_progress: 'In Bearbeitung',
      completed: 'Fertiggestellt',
      delivered: 'Ausgeliefert',
    };
    return labels[status] || status;
  };

  if (isLoading) {
    return <div className="page-loading">Lade Aufträge...</div>;
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
          <p style={{ color: '#666', margin: '0.5rem 0 0 0' }}>
            {filteredOrders.length} Aufträge • Gesamtwert: {totalRevenue.toFixed(2)} €
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
            type="text"
            placeholder="Suche nach Titel, Beschreibung oder ID..."
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
            <option value="new">Neu</option>
            <option value="in_progress">In Bearbeitung</option>
            <option value="completed">Fertiggestellt</option>
            <option value="delivered">Ausgeliefert</option>
          </select>
        </div>

        <div className="filter-group">
          <label>Sortieren:</label>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value as any)}>
            <option value="created">Erstelldatum</option>
            <option value="deadline">Deadline</option>
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
          <div className="table-container">
            <table className="orders-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Titel</th>
                  <th>Beschreibung</th>
                  <th>Status</th>
                  <th>Preis</th>
                  <th>Deadline</th>
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
                    <td>#{order.id}</td>
                    <td>{order.title}</td>
                    <td>{order.description.substring(0, 50)}...</td>
                    <td>
                      <span className={`status-badge status-${order.status}`}>
                        {getStatusLabel(order.status)}
                      </span>
                    </td>
                    <td>
                      {order.price ? (
                        <span className="price-display">{order.price.toFixed(2)} €</span>
                      ) : (
                        <span className="price-calculated">Wird berechnet</span>
                      )}
                    </td>
                    <td>
                      {order.deadline
                        ? new Date(order.deadline).toLocaleDateString('de-DE')
                        : '-'}
                    </td>
                    <td>{new Date(order.created_at).toLocaleDateString('de-DE')}</td>
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
