// CustomersPage - Customer Management
import React, { useEffect, useState, useCallback } from 'react';
import { customersApi } from '../api';
import { Customer, CustomerListItem, CustomerCategory } from '../types';
import { CustomerFormModal } from '../components/CustomerFormModal';
import '../styles/pages.css';
import '../styles/customers.css';

export const CustomersPage: React.FC = () => {
  const [customers, setCustomers] = useState<CustomerListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter states
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<CustomerCategory | ''>('');
  const [filterActive, setFilterActive] = useState<boolean | ''>('');

  // Pagination states
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [totalCount, setTotalCount] = useState(0);

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Fetch customers with filters
  const fetchCustomers = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const params: any = {
        skip: page * pageSize,
        limit: pageSize,
      };

      if (searchQuery) params.search = searchQuery;
      if (filterType) params.customer_type = filterType;
      if (filterActive !== '') params.is_active = filterActive;

      const data = await customersApi.getAll(params);
      setCustomers(data);
      setTotalCount(data.length); // Backend should return total, but for now we use length
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Kunden');
    } finally {
      setIsLoading(false);
    }
  }, [page, pageSize, searchQuery, filterType, filterActive]);

  useEffect(() => {
    // Debounce search
    const timer = setTimeout(() => {
      fetchCustomers();
    }, 300);

    return () => clearTimeout(timer);
  }, [fetchCustomers]);

  // Clear all filters
  const handleClearFilters = () => {
    setSearchQuery('');
    setFilterType('');
    setFilterActive('');
    setPage(0);
  };

  // Handle create customer
  const handleCreateCustomer = async (data: any) => {
    try {
      setIsSubmitting(true);
      await customersApi.create(data);
      setShowCreateModal(false);
      setPage(0); // Reset to first page
      await fetchCustomers();
    } catch (err: any) {
      throw new Error(err.response?.data?.detail || 'Fehler beim Erstellen des Kunden');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle edit customer
  const handleEditCustomer = async (data: any) => {
    if (!editingCustomer) return;

    try {
      setIsSubmitting(true);
      await customersApi.update(editingCustomer.id, data);
      setEditingCustomer(null);
      await fetchCustomers();
    } catch (err: any) {
      throw new Error(err.response?.data?.detail || 'Fehler beim Aktualisieren des Kunden');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle delete customer
  const handleDeleteCustomer = async (customerId: number, customerName: string) => {
    const confirmed = window.confirm(
      `Möchten Sie den Kunden "${customerName}" wirklich löschen?\n\n` +
      `Hinweis: Kunden mit aktiven Aufträgen können nicht gelöscht werden.`
    );

    if (!confirmed) return;

    try {
      await customersApi.delete(customerId);
      await fetchCustomers();
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || 'Fehler beim Löschen des Kunden';
      alert(`Fehler: ${errorMsg}\n\nTipp: Kunden mit Aufträgen können nicht gelöscht werden. Deaktivieren Sie den Kunden stattdessen.`);
    }
  };

  // Open edit modal
  const handleOpenEdit = async (customerId: number) => {
    try {
      const customer = await customersApi.getById(customerId);
      setEditingCustomer(customer);
    } catch (err: any) {
      alert('Fehler beim Laden der Kundendaten');
    }
  };

  // Pagination
  const totalPages = Math.ceil(totalCount / pageSize);
  const canGoPrevious = page > 0;
  const canGoNext = page < totalPages - 1;

  if (isLoading && customers.length === 0) {
    return <div className="page-loading">Lade Kunden...</div>;
  }

  return (
    <div className="page-container">
      <header className="page-header">
        <h1>Kunden</h1>
        <button
          className="btn-primary"
          onClick={() => setShowCreateModal(true)}
        >
          + Neuer Kunde
        </button>
      </header>

      {/* Search and Filters */}
      <div className="filter-bar">
        <input
          type="text"
          className="search-input"
          placeholder="Suchen nach Name, E-Mail oder Firma..."
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setPage(0); // Reset to first page on search
          }}
        />

        <select
          className="filter-select"
          value={filterType}
          onChange={(e) => {
            setFilterType(e.target.value as CustomerCategory | '');
            setPage(0);
          }}
        >
          <option value="">Alle Typen</option>
          <option value="private">Privat</option>
          <option value="business">Geschäftskunde</option>
        </select>

        <select
          className="filter-select"
          value={filterActive === '' ? '' : filterActive ? 'true' : 'false'}
          onChange={(e) => {
            const val = e.target.value;
            setFilterActive(val === '' ? '' : val === 'true');
            setPage(0);
          }}
        >
          <option value="">Alle Status</option>
          <option value="true">Aktiv</option>
          <option value="false">Inaktiv</option>
        </select>

        {(searchQuery || filterType || filterActive !== '') && (
          <button
            className="btn-clear-filters"
            onClick={handleClearFilters}
          >
            Filter zurücksetzen
          </button>
        )}
      </div>

      {error && (
        <div className="page-error">
          {error}
          <button onClick={fetchCustomers} className="btn-primary">
            Erneut versuchen
          </button>
        </div>
      )}

      {!error && customers.length === 0 ? (
        <div className="empty-state">
          <p>Keine Kunden gefunden.</p>
          {(searchQuery || filterType || filterActive !== '') ? (
            <p className="error-hint">Versuchen Sie, die Filter zu ändern oder zurückzusetzen.</p>
          ) : (
            <p className="error-hint">Erstellen Sie Ihren ersten Kunden, um loszulegen.</p>
          )}
        </div>
      ) : (
        <>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Firma</th>
                  <th>E-Mail</th>
                  <th>Telefon</th>
                  <th>Typ</th>
                  <th>Tags</th>
                  <th>Status</th>
                  <th>Aktionen</th>
                </tr>
              </thead>
              <tbody>
                {customers.map((customer) => (
                  <tr key={customer.id}>
                    <td>#{customer.id}</td>
                    <td>
                      <strong>{customer.first_name} {customer.last_name}</strong>
                    </td>
                    <td>{customer.company_name || '-'}</td>
                    <td>{customer.email}</td>
                    <td>{customer.phone || '-'}</td>
                    <td>
                      <span className="customer-type-badge">
                        {customer.customer_type === 'private' ? '👤 Privat' : '🏢 Geschäftskunde'}
                      </span>
                    </td>
                    <td>
                      {customer.tags && customer.tags.length > 0 ? (
                        <div>
                          {customer.tags.map((tag, idx) => (
                            <span key={idx} className="customer-tag">{tag}</span>
                          ))}
                        </div>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td>
                      <span className={`customer-status ${customer.is_active ? 'active' : 'inactive'}`}>
                        {customer.is_active ? '✅ Aktiv' : '⛔ Inaktiv'}
                      </span>
                    </td>
                    <td className="customer-actions">
                      <button
                        className="btn-action"
                        title="Bearbeiten"
                        onClick={() => handleOpenEdit(customer.id)}
                      >
                        ✏️
                      </button>
                      <button
                        className="btn-action btn-danger"
                        title="Löschen"
                        onClick={() => handleDeleteCustomer(
                          customer.id,
                          `${customer.first_name} ${customer.last_name}`
                        )}
                      >
                        🗑️
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {customers.length > 0 && (
            <div className="pagination-controls">
              <div className="pagination-info">
                Zeige {page * pageSize + 1}-{Math.min((page + 1) * pageSize, totalCount)} von {totalCount}
              </div>

              <div className="pagination-buttons">
                <button
                  onClick={() => setPage(p => p - 1)}
                  disabled={!canGoPrevious}
                >
                  ◀ Zurück
                </button>
                <span>Seite {page + 1} von {Math.max(totalPages, 1)}</span>
                <button
                  onClick={() => setPage(p => p + 1)}
                  disabled={!canGoNext}
                >
                  Weiter ▶
                </button>
              </div>

              <div className="page-size-selector">
                <label>Pro Seite:</label>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setPage(0);
                  }}
                >
                  <option value="10">10</option>
                  <option value="25">25</option>
                  <option value="50">50</option>
                  <option value="100">100</option>
                </select>
              </div>
            </div>
          )}
        </>
      )}

      {/* Create Customer Modal */}
      {showCreateModal && (
        <CustomerFormModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreateCustomer}
          isLoading={isSubmitting}
        />
      )}

      {/* Edit Customer Modal */}
      {editingCustomer && (
        <CustomerFormModal
          isOpen={!!editingCustomer}
          onClose={() => setEditingCustomer(null)}
          onSubmit={handleEditCustomer}
          customer={editingCustomer}
          isLoading={isSubmitting}
        />
      )}
    </div>
  );
};
