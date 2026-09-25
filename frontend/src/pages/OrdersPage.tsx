// Orders Page — server-paged list on TanStack Query (W3-03).
//
// GET /orders/?offset=… returns a Page envelope; status filter and `q`
// search run on the server (backend sorts newest first). The status filter
// lives in the URL (?status=…) so dashboard KPI links land pre-filtered.
// Realtime order hints invalidate ['orders'] in lib/realtimeInvalidation.ts,
// so this page registers no refetch of its own.
import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ordersApi } from '../api/orders';
import { compactParams, DEFAULT_PAGE_SIZE, pageInfo, pagedApi, type OrderPageItem } from '../api/paged';
import { queryKeys } from '../api/queryKeys';
import { photoThumbnailPath } from '../api/photos';
import AuthenticatedImage from '../components/AuthenticatedImage';
import { Pager } from '../components/Pager';
import { OrderFormModal } from '../components/orders/OrderFormModal';
import { useAuth, useToast, useConfirm } from '../contexts';
import { ORDER_STATUS } from '../design/status';
import { getErrorMessage } from '../lib/errors';
import { formatEur, MONEY_CLASS } from '../lib/format';
import { canCreateOrders, canDeleteOrders, canEditOrders, canViewFinancials } from '../lib/roles';
import { useDebouncedValue } from '../lib/useDebouncedValue';
import type { OrderType, OrderCreateInput, OrderUpdateInput, OrderStatus } from '../types';
import { Button, PageState, type PageStateValue } from '../ui';
import { StatusBadge } from '../ui/StatusBadge';
import '../styles/pages.css';
import '../styles/orders.css';
// .order-list-thumb (W2-01 thumbnail column) lives with the order styles.
import '../styles/order-detail.css';

/** Statuses accepted via ?status=…; anything else is ignored (no stuck empty filter). */
const VALID_ORDER_STATUS: ReadonlySet<OrderStatus> = new Set<OrderStatus>(
  Object.keys(ORDER_STATUS) as OrderStatus[],
);

/** Filter options: every status the backend knows, labels from status.ts. */
const STATUS_FILTER_OPTIONS = (Object.keys(ORDER_STATUS) as OrderStatus[]).map((value) => ({
  value,
  label: ORDER_STATUS[value].label,
}));

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
/** Backend `q` accepts 1-100 characters. */
const MAX_SEARCH_LENGTH = 100;

/**
 * Sort options, restoring the control removed in W3-03 now that the backend
 * has a `sort` parameter (whitelist: created_at, deadline, status, title —
 * see ORDER_SORT_FIELDS in services/list_queries.py). Empty value = the
 * backend default (newest first), so "Standard" never sends `sort` at all.
 */
const SORT_OPTIONS = [
  { value: '', label: 'Neueste zuerst (Standard)' },
  { value: 'deadline', label: 'Frist: nächste zuerst' },
  { value: '-deadline', label: 'Frist: späteste zuerst' },
  { value: 'title', label: 'Titel: A–Z' },
  { value: '-title', label: 'Titel: Z–A' },
] as const;

function parseStatus(value: string | null): OrderStatus | '' {
  return value && VALID_ORDER_STATUS.has(value as OrderStatus) ? (value as OrderStatus) : '';
}

function normaliseSearch(value: string): string {
  return value.trim().slice(0, MAX_SEARCH_LENGTH);
}

/**
 * The edit dialog still takes the hand-written OrderType (types.ts); the row
 * is the generated OrderListRead, which differs only in nullability (e.g.
 * `materials: … | null`). Cast at this one seam until OrderFormModal moves to
 * the generated types (review 04 section F item 2).
 */
function toOrderType(row: OrderPageItem): OrderType {
  return row as unknown as OrderType;
}

function useOrdersPage(params: {
  status: OrderStatus | '';
  q: string;
  sort: string;
  pageIndex: number;
  pageSize: number;
}) {
  const pageParams = compactParams({
    limit: params.pageSize,
    offset: params.pageIndex * params.pageSize,
    status: params.status || undefined,
    q: params.q || undefined,
    sort: params.sort || undefined,
  }) as Parameters<typeof pagedApi.orders>[0];
  return useQuery({
    queryKey: queryKeys.orders.page(pageParams),
    queryFn: ({ signal }) => pagedApi.orders(pageParams, signal),
    placeholderData: keepPreviousData,
  });
}

function useOrderMutations(onDone: () => void) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const navigate = useNavigate();
  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.orders.all }),
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all }),
    ]);

  const create = useMutation({
    mutationFn: (data: OrderCreateInput) => ordersApi.create(data),
    onSuccess: async (newOrder) => {
      await invalidate();
      onDone();
      if (newOrder.has_scrap_gold) {
        showToast(
          'Altgold-Erfassung ausstehend — bitte im Auftrag die Altgold-Daten eingeben',
          'warning',
        );
        navigate(`/orders/${newOrder.id}`);
      } else {
        showToast('Auftrag erstellt', 'success');
      }
    },
    onError: (err) => showToast(getErrorMessage(err, 'Auftrag konnte nicht erstellt werden'), 'error'),
  });

  const update = useMutation({
    mutationFn: ({ id, data }: { id: number; data: OrderUpdateInput }) => ordersApi.update(id, data),
    onSuccess: async () => {
      await invalidate();
      onDone();
      showToast('Auftrag gespeichert', 'success');
    },
    onError: (err) =>
      showToast(getErrorMessage(err, 'Auftrag konnte nicht gespeichert werden'), 'error'),
  });

  const remove = useMutation({
    mutationFn: (id: number) => ordersApi.delete(id),
    onSuccess: async () => {
      await invalidate();
      showToast('Auftrag gelöscht', 'success');
    },
    onError: (err) => showToast(getErrorMessage(err, 'Auftrag konnte nicht gelöscht werden'), 'error'),
  });

  return { create, update, remove };
}

function listState(query: ReturnType<typeof useOrdersPage>): PageStateValue {
  if (query.isPending) return { status: 'loading' };
  if (query.isError && !query.data) {
    return {
      status: 'error',
      error: getErrorMessage(query.error, 'Aufträge konnten nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }
  return { status: query.data?.items.length ? 'ready' : 'empty' };
}

export const OrdersPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { showConfirm } = useConfirm();
  // LV-07: role gates mirror ORDER_CREATE / ORDER_EDIT / ORDER_DELETE and
  // FINANCIAL_VIEW; hidden in code, never by CSS.
  const { user } = useAuth();
  const canFinance = canViewFinancials(user?.role);
  const canCreate = canCreateOrders(user?.role);
  const canEdit = canEditOrders(user?.role);
  const canDelete = canDeleteOrders(user?.role);
  const hasRowActions = canEdit || canDelete;

  const filterStatus = parseStatus(searchParams.get('status'));
  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = normaliseSearch(useDebouncedValue(searchInput));
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  const [sort, setSort] = useState<string>('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<OrderType | null>(null);

  // A new filter, search or sort starts on the first page.
  const [lastFilterKey, setLastFilterKey] = useState(`${filterStatus}|${debouncedSearch}|${sort}`);
  const filterKey = `${filterStatus}|${debouncedSearch}|${sort}`;
  if (filterKey !== lastFilterKey) {
    setLastFilterKey(filterKey);
    setPageIndex(0);
  }

  const query = useOrdersPage({
    status: filterStatus,
    q: debouncedSearch,
    sort,
    pageIndex,
    pageSize,
  });

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedOrder(null);
  };
  const { create, update, remove } = useOrderMutations(closeModal);

  const setFilterStatus = (status: OrderStatus | '') => {
    const next = new URLSearchParams(searchParams);
    if (status) next.set('status', status);
    else next.delete('status');
    setSearchParams(next, { replace: true });
  };

  const handleDeleteOrder = async (orderId: number, orderTitle: string) => {
    const confirmed = await showConfirm({
      title: 'Auftrag löschen',
      message: `Möchten Sie den Auftrag „${orderTitle}“ wirklich löschen?`,
      confirmLabel: 'Löschen',
      variant: 'danger',
    });
    if (confirmed) remove.mutate(orderId);
  };

  const openCreateModal = () => {
    setSelectedOrder(null);
    setIsModalOpen(true);
  };

  const openEditModal = (order: OrderPageItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedOrder(toOrderType(order));
    setIsModalOpen(true);
  };

  // Failures are shown by the mutations' onError toast; the dialog stays open.
  const handleFormSubmit = async (data: OrderCreateInput | OrderUpdateInput) => {
    if (selectedOrder) {
      await update.mutateAsync({ id: selectedOrder.id, data }).catch(() => undefined);
    } else {
      await create.mutateAsync(data as OrderCreateInput).catch(() => undefined);
    }
  };

  const orders = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const { pageNumber, pageCount } = query.data
    ? pageInfo(query.data)
    : { pageNumber: 1, pageCount: 1 };
  const pageValue = orders.reduce((sum, o) => sum + (o.price || 0), 0);
  const hasFilter = Boolean(filterStatus || debouncedSearch);

  const emptyAction = hasFilter ? (
    <Button
      variant="secondary"
      onClick={() => {
        setSearchInput('');
        setFilterStatus('');
      }}
    >
      Filter zurücksetzen
    </Button>
  ) : canCreate ? (
    <Button onClick={openCreateModal}>Auftrag anlegen</Button>
  ) : undefined;

  return (
    <div className="page-container orders-page">
      <header className="page-header">
        <div>
          <h1>Aufträge</h1>
          {query.data && (
            <p className="orders-page-summary">
              {total} Aufträge
              {canFinance && (
                <>
                  {' '}• Gesamtwert dieser Seite:{' '}
                  <span className={MONEY_CLASS}>{formatEur(pageValue)}</span>
                </>
              )}
            </p>
          )}
        </div>
        {canCreate && (
          <button className="btn-primary" onClick={openCreateModal}>
            + Neuer Auftrag
          </button>
        )}
      </header>

      {/* Search and Filters */}
      <div className="orders-controls">
        <div className="search-box">
          <input
            type="search"
            className="orders-search-input"
            aria-label="Aufträge durchsuchen"
            placeholder="Titel, Kunde oder Nr. …"
            maxLength={MAX_SEARCH_LENGTH}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <label htmlFor="orders-filter-status">Status:</label>
          <select
            id="orders-filter-status"
            value={filterStatus}
            onChange={(e) => setFilterStatus(parseStatus(e.target.value))}
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
          <label htmlFor="orders-sort">Sortieren:</label>
          <select
            id="orders-sort"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="orders-page-size">Pro Seite:</label>
          <select
            id="orders-page-size"
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
      </div>

      <PageState
        state={listState(query)}
        skeleton="list"
        empty={{
          icon: 'inbox',
          title: hasFilter ? 'Keine Aufträge gefunden' : 'Noch keine Aufträge',
          body: hasFilter ? 'Suche oder Filter ändern.' : undefined,
          action: emptyAction,
        }}
      >
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
                    {canFinance && <th>Preis</th>}
                    <th>Frist</th>
                    <th>Erstellt</th>
                    {hasRowActions && <th>Aktionen</th>}
                  </tr>
                </thead>
                <tbody>
                  {orders.map((order) => (
                    <tr key={order.id} onClick={() => navigate(`/orders/${order.id}`)}>
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
                      {canFinance && (
                        <td className={MONEY_CLASS}>
                          {order.price ? (
                            <span className="price-display">{formatEur(order.price)}</span>
                          ) : (
                            <span className="price-calculated">Wird berechnet</span>
                          )}
                        </td>
                      )}
                      <td className="orders-col-date">
                        {order.deadline ? new Date(order.deadline).toLocaleDateString('de-DE') : '—'}
                      </td>
                      <td className="orders-col-date">
                        {new Date(order.created_at).toLocaleDateString('de-DE')}
                      </td>
                      {hasRowActions && (
                        <td>
                          <div className="orders-page-actions">
                            {canEdit && (
                              <button
                                className="btn-icon btn-edit"
                                onClick={(e) => openEditModal(order, e)}
                                title="Bearbeiten"
                                aria-label="Auftrag bearbeiten"
                              >
                                <span aria-hidden="true">✏️</span>
                              </button>
                            )}
                            {canDelete && (
                              <button
                                className="btn-icon btn-delete"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void handleDeleteOrder(order.id, order.title);
                                }}
                                title="Löschen"
                                aria-label="Auftrag löschen"
                                disabled={remove.isPending}
                              >
                                <span aria-hidden="true">🗑️</span>
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Pager
              label="Seiten der Auftragsliste"
              pageNumber={pageNumber}
              pageCount={pageCount}
              hasNext={query.data?.next_offset != null}
              isFetching={query.isFetching}
              onPrevious={() => setPageIndex((index) => Math.max(index - 1, 0))}
              onNext={() => setPageIndex((index) => index + 1)}
            />
          </>
      </PageState>

      {/* Order Form Modal */}
      <OrderFormModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onSubmit={handleFormSubmit}
        order={selectedOrder}
        isLoading={create.isPending || update.isPending}
      />
    </div>
  );
};
