// CustomersPage - Customer Management on TanStack Query (W3-03).
//
// GET /customers/ has no Page envelope yet (no `offset`, no total), so the
// legacy skip/limit call runs inside useQuery; search, type and status
// filter server-side. "Weiter" is offered while a page comes back full.
// TODO(W3-08 follow-up): switch to pagedApi once /customers/ returns Page[T].
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { customersApi } from '../api/customers';
import { DEFAULT_PAGE_SIZE, compactParams } from '../api/paged';
import { queryKeys, type CustomerListParams } from '../api/queryKeys';
import type {
  Customer,
  CustomerCategory,
  CustomerCreateInput,
  CustomerUpdateInput,
} from '../types';
import { CustomerFormModal } from '../components/CustomerFormModal';
import { Pager } from '../components/Pager';
import { useToast, useConfirm } from '../contexts';
import { getErrorMessage } from '../lib/errors';
import { useDebouncedValue } from '../lib/useDebouncedValue';
import { Button, PageState, type PageStateValue } from '../ui';
import '../styles/pages.css';
import '../styles/customers.css';

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;

interface CustomerFilters {
  search: string;
  customerType: CustomerCategory | '';
  isActive: boolean | '';
}

const NO_FILTERS: CustomerFilters = { search: '', customerType: '', isActive: '' };

function listParams(filters: CustomerFilters, pageIndex: number, pageSize: number): CustomerListParams {
  return compactParams({
    skip: pageIndex * pageSize,
    limit: pageSize,
    search: filters.search.trim() || undefined,
    customer_type: filters.customerType || undefined,
    is_active: filters.isActive === '' ? undefined : filters.isActive,
  }) as CustomerListParams;
}

function useCustomerMutations() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.customers.all });

  const create = useMutation({
    mutationFn: (data: CustomerCreateInput) => customersApi.create(data),
    onSuccess: invalidate,
  });
  const update = useMutation({
    mutationFn: ({ id, data }: { id: number; data: CustomerUpdateInput }) =>
      customersApi.update(id, data),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: (id: number) => customersApi.delete(id),
    onSuccess: async () => {
      await invalidate();
      showToast('Kunde gelöscht', 'success');
    },
    onError: (err) =>
      showToast(
        `${getErrorMessage(err, 'Kunde konnte nicht gelöscht werden')} – Tipp: Kunden mit Aufträgen können nicht gelöscht werden. Deaktivieren Sie den Kunden stattdessen.`,
        'error',
      ),
  });
  return { create, update, remove };
}

export const CustomersPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();

  const [filters, setFilters] = useState<CustomerFilters>(NO_FILTERS);
  const debouncedSearch = useDebouncedValue(filters.search);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);

  const params = listParams({ ...filters, search: debouncedSearch }, pageIndex, pageSize);
  const query = useQuery({
    queryKey: queryKeys.customers.list(params),
    queryFn: () => customersApi.getAll(params),
    placeholderData: keepPreviousData,
  });
  const { create, update, remove } = useCustomerMutations();

  const customers = query.data ?? [];
  const hasFilter = Boolean(filters.search || filters.customerType || filters.isActive !== '');
  const hasNext = customers.length === pageSize;

  const updateFilters = (patch: Partial<CustomerFilters>) => {
    setFilters((current) => ({ ...current, ...patch }));
    setPageIndex(0);
  };

  const handleCreateCustomer = async (data: CustomerCreateInput | CustomerUpdateInput) => {
    try {
      await create.mutateAsync(data as CustomerCreateInput);
      setShowCreateModal(false);
      setPageIndex(0);
    } catch (err) {
      // CustomerFormModal shows the message and keeps the form open.
      throw new Error(getErrorMessage(err, 'Kunde konnte nicht angelegt werden'));
    }
  };

  const handleEditCustomer = async (data: CustomerCreateInput | CustomerUpdateInput) => {
    if (!editingCustomer) return;
    try {
      await update.mutateAsync({ id: editingCustomer.id, data });
      setEditingCustomer(null);
    } catch (err) {
      throw new Error(getErrorMessage(err, 'Kunde konnte nicht gespeichert werden'));
    }
  };

  const handleDeleteCustomer = async (customerId: number, customerName: string) => {
    const confirmed = await showConfirm({
      title: 'Kunden löschen',
      message: `Möchten Sie den Kunden „${customerName}“ wirklich löschen? Kunden mit aktiven Aufträgen können nicht gelöscht werden.`,
      confirmLabel: 'Löschen',
      variant: 'danger',
    });
    if (confirmed) remove.mutate(customerId);
  };

  const handleOpenEdit = async (customerId: number) => {
    try {
      const customer = await queryClient.fetchQuery({
        queryKey: queryKeys.customers.detail(customerId),
        queryFn: () => customersApi.getById(customerId),
      });
      setEditingCustomer(customer);
    } catch (err) {
      showToast(getErrorMessage(err, 'Kundendaten konnten nicht geladen werden'), 'error');
    }
  };

  const state: PageStateValue = query.isPending
    ? { status: 'loading' }
    : query.isError && !query.data
      ? {
          status: 'error',
          error: getErrorMessage(query.error, 'Kunden konnten nicht geladen werden.'),
          retry: () => void query.refetch(),
        }
      : { status: customers.length ? 'ready' : 'empty' };

  return (
    <div className="page-container">
      <header className="page-header">
        <h1>Kunden</h1>
        <button className="btn-primary" onClick={() => setShowCreateModal(true)}>
          + Neuer Kunde
        </button>
      </header>

      {/* Search and Filters */}
      <div className="filter-bar">
        <input
          type="search"
          className="search-input"
          aria-label="Kunden durchsuchen"
          placeholder="Suchen nach Name, E-Mail oder Firma …"
          value={filters.search}
          onChange={(e) => updateFilters({ search: e.target.value })}
        />

        <select
          className="filter-select"
          aria-label="Kundentyp"
          value={filters.customerType}
          onChange={(e) => updateFilters({ customerType: e.target.value as CustomerCategory | '' })}
        >
          <option value="">Alle Typen</option>
          <option value="private">Privat</option>
          <option value="business">Geschäftskunde</option>
        </select>

        <select
          className="filter-select"
          aria-label="Kundenstatus"
          value={filters.isActive === '' ? '' : filters.isActive ? 'true' : 'false'}
          onChange={(e) => {
            const val = e.target.value;
            updateFilters({ isActive: val === '' ? '' : val === 'true' });
          }}
        >
          <option value="">Alle Status</option>
          <option value="true">Aktiv</option>
          <option value="false">Inaktiv</option>
        </select>

        {hasFilter && (
          <button className="btn-clear-filters" onClick={() => updateFilters(NO_FILTERS)}>
            Filter zurücksetzen
          </button>
        )}
      </div>

      <PageState
        state={state}
        skeleton="list"
        empty={{
          icon: 'search',
          title: hasFilter ? 'Keine Kunden gefunden' : 'Noch keine Kunden',
          body: hasFilter ? 'Suche oder Filter ändern.' : undefined,
          action: hasFilter ? (
            <Button variant="secondary" onClick={() => updateFilters(NO_FILTERS)}>
              Filter zurücksetzen
            </Button>
          ) : (
            <Button onClick={() => setShowCreateModal(true)}>Kunden anlegen</Button>
          ),
        }}
      >
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
                <tr
                  key={customer.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/customers/${customer.id}`)}
                >
                  <td>#{customer.id}</td>
                  <td>
                    <strong>
                      {customer.first_name} {customer.last_name}
                    </strong>
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
                        {customer.tags.map((tag) => (
                          <span key={tag} className="customer-tag">
                            {tag}
                          </span>
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
                      aria-label="Kunden bearbeiten"
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleOpenEdit(customer.id);
                      }}
                    >
                      <span aria-hidden="true">✏️</span>
                    </button>
                    <button
                      className="btn-action btn-danger"
                      title="Löschen"
                      aria-label="Kunden löschen"
                      disabled={remove.isPending}
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDeleteCustomer(
                          customer.id,
                          `${customer.first_name} ${customer.last_name}`,
                        );
                      }}
                    >
                      <span aria-hidden="true">🗑️</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <Pager
          label="Seiten der Kundenliste"
          pageNumber={pageIndex + 1}
          pageCount={hasNext ? undefined : pageIndex + 1}
          summary={`${pageIndex * pageSize + 1}–${pageIndex * pageSize + customers.length} angezeigt`}
          hasNext={hasNext}
          isFetching={query.isFetching}
          onPrevious={() => setPageIndex((index) => Math.max(index - 1, 0))}
          onNext={() => setPageIndex((index) => index + 1)}
        />
        <div className="page-size-selector">
          <label htmlFor="customers-page-size">Pro Seite:</label>
          <select
            id="customers-page-size"
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPageIndex(0);
            }}
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>
      </PageState>

      {/* Create Customer Modal */}
      {showCreateModal && (
        <CustomerFormModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreateCustomer}
          isLoading={create.isPending}
        />
      )}

      {/* Edit Customer Modal */}
      {editingCustomer && (
        <CustomerFormModal
          isOpen={!!editingCustomer}
          onClose={() => setEditingCustomer(null)}
          onSubmit={handleEditCustomer}
          customer={editingCustomer}
          isLoading={update.isPending}
        />
      )}
    </div>
  );
};
