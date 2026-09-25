// Metal Inventory Page — TanStack Query (W4-03).
//
// GET /metal-inventory/purchases is a legacy plain list (no Page envelope),
// so it runs inside useQuery once and search, filters, sort and paging apply
// on the client. All keys sit under ['metal-inventory']; purchases and
// bookings invalidate that root. No realtime channel carries metal changes.
import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import { metalInventoryApi } from '../api';
import { queryKeys } from '../api/queryKeys';
import type {
  MetalPurchaseListItem,
  MetalPurchaseCreateInput,
  MetalPurchaseUpdateInput,
  MetalType,
} from '../types';
import { MetalSummaryCards } from '../components/metal/MetalSummaryCards';
import { PriceChart } from '../components/metal/PriceChart';
import { MetalPurchaseFormModal } from '../components/metal/MetalPurchaseFormModal';
import { MetalTypeManager } from '../components/metal/MetalTypeManager';
import { ConsumeMetalModal } from '../components/metal/ConsumeMetalModal';
import { UsageHistoryPanel } from '../components/metal/UsageHistoryPanel';
import {
  DEPLETED_THRESHOLD_G,
  formatDate,
  formatWeight,
  METAL_TYPES,
  metalLabel,
  metalLabelWithPurity,
} from '../components/metal/metalLabels';
import { purchasesQuery } from '../components/metal/metalQueries';
import { Pager } from '../components/Pager';
import { useToast, useAuth } from '../contexts';
import { getErrorMessage } from '../lib/errors';
import { formatEur, MISSING_VALUE, MONEY_CLASS } from '../lib/format';
import {
  canEditOrders,
  canManageMaterials,
  canViewFinancials,
  FINANCIAL_HIDDEN_HINT,
} from '../lib/roles';
import {
  Button,
  DataTable,
  EmptyState,
  Field,
  IconButton,
  PageHeader,
  type Column,
  type PageStateValue,
} from '../ui';
import '../styles/metal-inventory.css';

type DepletedFilter = 'all' | 'active' | 'depleted';
type SortKey = 'date' | 'metal_type' | 'value' | 'remaining';

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
const PERCENT = 100;

interface ListFilters {
  search: string;
  metalType: MetalType | '';
  depleted: DepletedFilter;
  sortBy: SortKey;
}

const isDepleted = (p: MetalPurchaseListItem) => p.remaining_weight_g <= DEPLETED_THRESHOLD_G;
const remainingValue = (p: MetalPurchaseListItem) => p.remaining_weight_g * p.price_per_gram;

function usagePercent(p: MetalPurchaseListItem): number {
  return p.weight_g === 0 ? 0 : ((p.weight_g - p.remaining_weight_g) / p.weight_g) * PERCENT;
}

const SORTERS: Record<SortKey, (a: MetalPurchaseListItem, b: MetalPurchaseListItem) => number> = {
  date: (a, b) => new Date(b.date_purchased).getTime() - new Date(a.date_purchased).getTime(),
  metal_type: (a, b) => a.metal_type.localeCompare(b.metal_type),
  value: (a, b) => remainingValue(b) - remainingValue(a),
  remaining: (a, b) => b.remaining_weight_g - a.remaining_weight_g,
};

function applyFilters(rows: MetalPurchaseListItem[], f: ListFilters): MetalPurchaseListItem[] {
  const q = f.search.trim().toLowerCase();
  return rows
    .filter(
      (p) =>
        !q ||
        [p.supplier, p.invoice_number, p.lot_number, String(p.id)].some((v) => v?.toLowerCase().includes(q)),
    )
    .filter((p) => !f.metalType || p.metal_type === f.metalType)
    .filter((p) => f.depleted === 'all' || (f.depleted === 'depleted') === isDepleted(p))
    .sort(SORTERS[f.sortBy]);
}

function buildColumns(canEdit: boolean, onEdit: (p: MetalPurchaseListItem) => void): Column<MetalPurchaseListItem>[] {
  const columns: Column<MetalPurchaseListItem>[] = [
    { key: 'metal', header: 'Metalltyp', render: (p) => metalLabel(p.metal_type) },
    // LV3-06: id and lot (batch code) are the lowest-value columns at
    // tablet-and-up widths — see the identical MaterialsPage.tsx comment
    // and .orders-col-description in orders.css for the precedent this
    // mirrors (hideBelow tops out at 1024px, so it can't hide a column
    // specifically at the 1280px width where this table overflowed).
    { key: 'id', header: 'ID', className: 'metal-col-hide-tablet-up', render: (p) => `#${p.id}` },
    { key: 'date', header: 'Datum', render: (p) => <span className="ui-num">{formatDate(p.date_purchased)}</span> },
    { key: 'weight', header: 'Gewicht', numeric: true, align: 'end', hideBelow: 'tablet', render: (p) => formatWeight(p.weight_g) },
    {
      key: 'remaining',
      header: 'Verbleibend',
      numeric: true,
      align: 'end',
      render: (p) => (
        <span className={isDepleted(p) ? 'metal-muted' : undefined}>
          {formatWeight(p.remaining_weight_g)}
          {isDepleted(p) && ' (aufgebraucht)'}
        </span>
      ),
    },
    {
      key: 'price',
      header: 'Preis/g',
      numeric: true,
      align: 'end',
      hideBelow: 'tablet',
      render: (p) => <span className={MONEY_CLASS}>{formatEur(p.price_per_gram)}</span>,
    },
    {
      key: 'value',
      header: 'Wert',
      numeric: true,
      align: 'end',
      render: (p) => <span className={MONEY_CLASS}>{formatEur(remainingValue(p))}</span>,
    },
    {
      key: 'usage',
      header: 'Verbrauch',
      hideBelow: 'tablet',
      render: (p) => (
        <span className="metal-usage">
          <span className="metal-usage__bar" aria-hidden="true">
            {/* Runtime value: share of the batch already used. */}
            <span className="metal-usage__fill" style={{ width: `${usagePercent(p)}%` }} />
          </span>
          <span className="ui-num">{usagePercent(p).toFixed(0)} %</span>
        </span>
      ),
    },
    { key: 'supplier', header: 'Lieferant', hideBelow: 'tablet', render: (p) => p.supplier || MISSING_VALUE },
    { key: 'lot', header: 'Charge', className: 'metal-col-hide-tablet-up', render: (p) => <code>{p.lot_number || MISSING_VALUE}</code> },
  ];
  if (canEdit) {
    columns.push({
      key: 'actions',
      header: 'Aktionen',
      render: (p) => (
        <IconButton icon="pencil" label={`Einkauf #${p.id} bearbeiten`} onClick={() => onEdit(p)} />
      ),
    });
  }
  return columns;
}

function usePurchaseMutation(selected: MetalPurchaseListItem | null, onSaved: () => void) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  return useMutation({
    mutationFn: (data: MetalPurchaseCreateInput | MetalPurchaseUpdateInput) =>
      selected
        ? metalInventoryApi.updatePurchase(selected.id, data as MetalPurchaseUpdateInput)
        : metalInventoryApi.createPurchase(data as MetalPurchaseCreateInput),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.metalInventory.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all }),
      ]);
      showToast(selected ? 'Einkauf gespeichert' : 'Einkauf angelegt', 'success');
      onSaved();
    },
    onError: (err) => showToast(getErrorMessage(err, 'Einkauf konnte nicht gespeichert werden.'), 'error'),
  });
}

function listState(query: UseQueryResult<MetalPurchaseListItem[]>, count: number): PageStateValue {
  if (query.isPending) return { status: 'loading' };
  if (query.isError) {
    return {
      status: 'error',
      error: getErrorMessage(query.error, 'Metalleinkäufe konnten nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }
  return { status: count ? 'ready' : 'empty' };
}

interface FilterBarProps {
  filters: ListFilters;
  onChange: (patch: Partial<ListFilters>) => void;
  pageSize: number;
  onPageSize: (size: number) => void;
}

const FilterBar: React.FC<FilterBarProps> = ({ filters, onChange, pageSize, onPageSize }) => (
  <div className="metal-controls">
    <Field label="Suche" name="metal-search" inputMode="search" className="metal-controls__search">
      <input
        type="search"
        placeholder="Lieferant, Rechnung, Charge oder ID …"
        value={filters.search}
        onChange={(e) => onChange({ search: e.target.value })}
      />
    </Field>
    <Field label="Metalltyp" name="metal-inventory-filter-type">
      <select value={filters.metalType} onChange={(e) => onChange({ metalType: e.target.value as MetalType | '' })}>
        <option value="">Alle</option>
        {METAL_TYPES.map((value) => (
          <option key={value} value={value}>
            {metalLabelWithPurity(value)}
          </option>
        ))}
      </select>
    </Field>
    <Field label="Bestand" name="metal-inventory-filter-status">
      <select value={filters.depleted} onChange={(e) => onChange({ depleted: e.target.value as DepletedFilter })}>
        <option value="all">Alle</option>
        <option value="active">Aktiv (Bestand vorhanden)</option>
        <option value="depleted">Aufgebraucht</option>
      </select>
    </Field>
    <Field label="Sortieren" name="metal-inventory-sort-by">
      <select value={filters.sortBy} onChange={(e) => onChange({ sortBy: e.target.value as SortKey })}>
        <option value="date">Kaufdatum</option>
        <option value="metal_type">Metalltyp</option>
        <option value="value">Wert</option>
        <option value="remaining">Verbleibend</option>
      </select>
    </Field>
    <Field label="Pro Seite" name="metal-inventory-page-size">
      <select value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))}>
        {PAGE_SIZE_OPTIONS.map((size) => (
          <option key={size} value={size}>
            {size}
          </option>
        ))}
      </select>
    </Field>
  </div>
);

const MetalInventoryContent: React.FC<{ role: string | undefined }> = ({ role }) => {
  const { showToast } = useToast();
  // FE-12: the backend serialises roles lowercase; compare case-insensitively.
  const isAdmin = (role ?? '').toUpperCase() === 'ADMIN';
  const canManage = canManageMaterials(role); // MATERIAL_CREATE / MATERIAL_EDIT
  const canConsume = canEditOrders(role); // POST /consume needs ORDER_EDIT

  const [filters, setFilters] = useState<ListFilters>({
    search: '',
    metalType: '',
    depleted: 'active',
    sortBy: 'date',
  });
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZE_OPTIONS[0]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selected, setSelected] = useState<MetalPurchaseListItem | null>(null);
  const [isConsumeOpen, setIsConsumeOpen] = useState(false);
  const [isTypeManagerOpen, setIsTypeManagerOpen] = useState(false);

  const query = useQuery(purchasesQuery({ include_depleted: true }));
  const closeModal = () => {
    setIsModalOpen(false);
    setSelected(null);
  };
  const save = usePurchaseMutation(selected, closeModal);

  const filtered = applyFilters(query.data ?? [], filters);
  const pageCount = Math.max(Math.ceil(filtered.length / pageSize), 1);
  const safePage = Math.min(pageIndex, pageCount - 1);
  const pageRows = filtered.slice(safePage * pageSize, (safePage + 1) * pageSize);
  const totalValue = filtered.reduce((sum, p) => sum + remainingValue(p), 0);
  const hasFilter = Boolean(filters.search || filters.metalType || filters.depleted !== 'all');

  const updateFilters = (patch: Partial<ListFilters>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
    setPageIndex(0);
  };
  const openCreate = () => {
    setSelected(null);
    setIsModalOpen(true);
  };

  return (
    <div className="page-container metal-inventory-page">
      <PageHeader
        title="Metallinventar"
        meta={
          query.data && (
            <>
              {filtered.length} Einkäufe • Wert: <span className={MONEY_CLASS}>{formatEur(totalValue)}</span>
            </>
          )
        }
        primaryAction={
          canManage ? (
            <Button icon="plus" onClick={openCreate}>
              Einkauf anlegen
            </Button>
          ) : undefined
        }
        secondaryActions={
          <>
            {canConsume && (
              <Button variant="secondary" onClick={() => setIsConsumeOpen(true)}>
                Verbrauch erfassen
              </Button>
            )}
            {isAdmin && (
              <Button variant="secondary" onClick={() => setIsTypeManagerOpen(true)}>
                Metalltypen verwalten
              </Button>
            )}
          </>
        }
      />

      <MetalSummaryCards />
      <PriceChart />

      <section className="metal-purchases" aria-labelledby="metal-purchases-title">
        <h2 id="metal-purchases-title">Metalleinkäufe</h2>
        <FilterBar
          filters={filters}
          onChange={updateFilters}
          pageSize={pageSize}
          onPageSize={(size) => {
            setPageSize(size);
            setPageIndex(0);
          }}
        />
        <DataTable
          rows={pageRows}
          columns={buildColumns(canManage, (p) => {
            setSelected(p);
            setIsModalOpen(true);
          })}
          getRowKey={(p) => p.id}
          caption="Metalleinkäufe"
          state={listState(query, pageRows.length)}
          empty={{
            icon: 'inbox',
            title: hasFilter ? 'Keine Metalleinkäufe gefunden' : 'Noch keine Metalleinkäufe',
            body: hasFilter ? 'Suche oder Filter ändern.' : undefined,
            action: hasFilter ? (
              <Button
                variant="secondary"
                onClick={() => updateFilters({ search: '', metalType: '', depleted: 'all' })}
              >
                Filter zurücksetzen
              </Button>
            ) : canManage ? (
              <Button onClick={openCreate}>Einkauf anlegen</Button>
            ) : undefined,
          }}
        />
        {filtered.length > pageSize && (
          <Pager
            label="Seiten der Einkaufsliste"
            pageNumber={safePage + 1}
            pageCount={pageCount}
            hasNext={safePage < pageCount - 1}
            isFetching={query.isFetching}
            onPrevious={() => setPageIndex(Math.max(safePage - 1, 0))}
            onNext={() => setPageIndex(safePage + 1)}
          />
        )}
      </section>

      <UsageHistoryPanel onRecordUsage={canConsume ? () => setIsConsumeOpen(true) : undefined} />

      {canManage && (
        <MetalPurchaseFormModal
          isOpen={isModalOpen}
          onClose={closeModal}
          onSubmit={async (data) => {
            await save.mutateAsync(data).catch(() => undefined);
          }}
          purchase={selected}
          isLoading={save.isPending}
        />
      )}
      {canConsume && (
        <ConsumeMetalModal
          isOpen={isConsumeOpen}
          onClose={() => setIsConsumeOpen(false)}
          onSuccess={() => showToast('Verbrauch gebucht', 'success')}
        />
      )}
      {isAdmin && <MetalTypeManager isOpen={isTypeManagerOpen} onClose={() => setIsTypeManagerOpen(false)} />}
    </div>
  );
};

export const MetalInventoryPage: React.FC = () => {
  const { user } = useAuth();
  // FINANCIAL_VIEW (SEC-01): every endpoint on this page — purchases,
  // statistics, usage history, allocate-preview — is financial by nature
  // and 403s a VIEWER outright, so the queries are not even mounted for a
  // caller without the role (mirrors CostAlertBanner's canView pattern).
  if (!canViewFinancials(user?.role)) {
    return (
      <div className="page-container metal-inventory-page">
        <PageHeader title="Metallinventar" />
        <EmptyState icon="circle-help" title={FINANCIAL_HIDDEN_HINT} />
      </div>
    );
  }
  return <MetalInventoryContent role={user?.role} />;
};
