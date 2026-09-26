// Materials Page — server-paged list on TanStack Query (W4-03).
//
// GET /materials/?offset=… returns a Page envelope; `q` searches name and
// supplier on the server. Sorting and the "Nur niedriger Bestand" filter
// apply to the rows of the current page (the endpoint has no sort or
// low-stock parameter). No realtime channel carries material changes, so
// the list refreshes via mutation invalidation and window focus.
import React, { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { materialsApi } from '../api/materials';
import {
  compactParams,
  DEFAULT_PAGE_SIZE,
  pageInfo,
  pagedApi,
  type MaterialPageItem,
  type MaterialPageParams,
} from '../api/paged';
import { queryKeys } from '../api/queryKeys';
import type { MaterialType, MaterialCreateInput, MaterialUpdateInput } from '../types';
import { MaterialFormModal, type MaterialFormSubmit } from '../components/materials/MaterialFormModal';
import { PurchaseListModal } from '../components/materials/PurchaseListModal';
import { Pager } from '../components/Pager';
import { useToast, useConfirm, useAuth } from '../contexts';
import { getErrorMessage } from '../lib/errors';
import { formatEur, MISSING_VALUE, MONEY_CLASS } from '../lib/format';
import { canManageMaterials, canViewFinancials } from '../lib/roles';
import { useDebouncedValue } from '../lib/useDebouncedValue';
import {
  Button,
  DataTable,
  Field,
  IconButton,
  PageHeader,
  type Column,
  type PageStateValue,
} from '../ui';
import '../styles/materials.css';

type SortKey = 'name' | 'price' | 'stock';
/** Backend `q` accepts 1-100 characters. */
const MAX_SEARCH_LENGTH = 100;
/** Fallback when a material has no own minimum stock. */
const DEFAULT_MIN_STOCK = 10;

function isLowStock(material: MaterialPageItem): boolean {
  return material.stock < (material.min_stock ?? DEFAULT_MIN_STOCK);
}

/**
 * The form dialog still takes the hand-written MaterialType (types.ts); the
 * row is the generated MaterialRead, which differs only in nullability.
 * Cast at this one seam.
 */
function toMaterialType(row: MaterialPageItem): MaterialType {
  return row as unknown as MaterialType;
}

function sortRows(rows: MaterialPageItem[], sortBy: SortKey, canFinance: boolean): MaterialPageItem[] {
  return [...rows].sort((a, b) => {
    if (sortBy === 'price' && canFinance) return (b.unit_price ?? 0) - (a.unit_price ?? 0);
    if (sortBy === 'stock') return a.stock - b.stock;
    return a.name.localeCompare(b.name, 'de');
  });
}

function useMaterialsPage(q: string, pageIndex: number) {
  const params = compactParams({
    limit: DEFAULT_PAGE_SIZE,
    offset: pageIndex * DEFAULT_PAGE_SIZE,
    q: q || undefined,
  }) as MaterialPageParams;
  return useQuery({
    queryKey: queryKeys.materials.page(params),
    queryFn: ({ signal }) => pagedApi.materials(params, signal),
    placeholderData: keepPreviousData,
  });
}

function useMaterialMutations(onSaved: () => void) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.materials.all });

  const uploadImage = async (id: number, file: File | undefined, failMessage: string) => {
    if (!file) return;
    try {
      await materialsApi.uploadImage(id, file);
    } catch (err) {
      console.error('Material image upload failed', { materialId: id, err });
      showToast(failMessage, 'error');
    }
  };

  const save = useMutation({
    mutationFn: async ({ id, data }: { id: number | null; data: MaterialFormSubmit }) => {
      const { _imageFile, ...payload } = data;
      if (id === null) {
        const created = await materialsApi.create(payload as MaterialCreateInput);
        await uploadImage(created.id, _imageFile, 'Material angelegt, aber das Bild wurde nicht hochgeladen.');
        return 'Material angelegt';
      }
      await materialsApi.update(id, payload as MaterialUpdateInput);
      await uploadImage(id, _imageFile, 'Material gespeichert, aber das Bild wurde nicht hochgeladen.');
      return 'Material gespeichert';
    },
    onSuccess: async (message) => {
      await invalidate();
      onSaved();
      showToast(message, 'success');
    },
    onError: (err) => showToast(getErrorMessage(err, 'Material konnte nicht gespeichert werden.'), 'error'),
  });

  const remove = useMutation({
    mutationFn: (id: number) => materialsApi.delete(id),
    onSuccess: async () => {
      await invalidate();
      showToast('Material gelöscht', 'success');
    },
    onError: (err) =>
      showToast(
        getErrorMessage(
          err,
          'Material konnte nicht gelöscht werden. Es wird möglicherweise noch in Aufträgen verwendet.',
        ),
        'error',
      ),
  });

  return { save, remove };
}

function listState(query: ReturnType<typeof useMaterialsPage>, rowCount: number): PageStateValue {
  if (query.isPending) return { status: 'loading' };
  if (query.isError && !query.data) {
    return {
      status: 'error',
      error: getErrorMessage(query.error, 'Materialien konnten nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }
  return { status: rowCount > 0 ? 'ready' : 'empty' };
}

function SupplierCell({ material }: { material: MaterialPageItem }) {
  if (!material.webshop_url) return <>{material.supplier || MISSING_VALUE}</>;
  return (
    <a href={material.webshop_url} target="_blank" rel="noopener noreferrer" title="Im Webshop bestellen">
      {material.supplier || 'Webshop'}
      <span className="ui-visually-hidden"> (Webshop, neues Fenster)</span>
    </a>
  );
}

function StockCell({ material }: { material: MaterialPageItem }) {
  const lowStock = isLowStock(material);
  return (
    <span className="materials-stock">
      <span className="ui-num">{material.stock}</span>
      {lowStock && <span className="materials-stock__low">Niedrig</span>}
    </span>
  );
}

function buildColumns(options: {
  canFinance: boolean;
  canManage: boolean;
  onEdit: (m: MaterialPageItem) => void;
  onDelete: (m: MaterialPageItem) => void;
  isDeleting: boolean;
}): Column<MaterialPageItem>[] {
  const { canFinance, canManage, onEdit, onDelete, isDeleting } = options;
  const columns: Column<MaterialPageItem>[] = [
    { key: 'name', header: 'Name', render: (m) => m.name },
    {
      key: 'image',
      header: 'Bild',
      hideBelow: 'tablet',
      render: (m) =>
        m.image_url ? (
          <img src={m.image_url} alt={m.name} className="materials-thumb" />
        ) : (
          <span className="materials-thumb materials-thumb--empty">Kein Bild</span>
        ),
    },
    // LV3-06: id and description are the lowest-value columns at
    // tablet-and-up widths (internal id; a two-line clamp with no data a
    // sighted desktop user can't already see elsewhere) — the same
    // reasoning LV-19 applied to the orders table's own "Beschreibung"
    // column. hideBelow alone only reaches 1024px (the playbook's widest
    // breakpoint), so at 1280px both columns were still rendered and
    // pushed the table wider than its card. materials-col-hide-tablet-up
    // (materials.css) hides them from 600px up instead, same as
    // .orders-col-description; they still surface in the phone card
    // (no hideBelow here, so they stay in DataTable's cardColumns).
    { key: 'id', header: 'ID', className: 'materials-col-hide-tablet-up', render: (m) => `#${m.id}` },
    { key: 'supplier', header: 'Lieferant', render: (m) => <SupplierCell material={m} /> },
    {
      key: 'description',
      header: 'Beschreibung',
      className: 'materials-col-hide-tablet-up',
      render: (m) => <span className="materials-clamp">{m.description || MISSING_VALUE}</span>,
    },
  ];
  if (canFinance) {
    columns.push({
      key: 'unit_price',
      header: 'Preis/Einheit',
      numeric: true,
      align: 'end',
      render: (m) => <span className={MONEY_CLASS}>{formatEur(m.unit_price)}</span>,
    });
  }
  columns.push(
    { key: 'stock', header: 'Bestand', numeric: true, align: 'end', render: (m) => <StockCell material={m} /> },
    { key: 'unit', header: 'Einheit', render: (m) => m.unit },
  );
  if (canFinance) {
    columns.push({
      key: 'value',
      header: 'Wert',
      numeric: true,
      align: 'end',
      render: (m) => (
        <span className={MONEY_CLASS}>
          {m.unit_price != null ? formatEur(m.unit_price * m.stock) : MISSING_VALUE}
        </span>
      ),
    });
  }
  if (canManage) {
    columns.push({
      key: 'actions',
      header: 'Aktionen',
      render: (m) => (
        <span className="materials-actions">
          <IconButton icon="pencil" label={`${m.name} bearbeiten`} onClick={() => onEdit(m)} />
          <IconButton
            icon="trash"
            variant="danger"
            label={`${m.name} löschen`}
            disabled={isDeleting}
            onClick={() => onDelete(m)}
          />
        </span>
      ),
    });
  }
  return columns;
}

export const MaterialsPage: React.FC = () => {
  const { showConfirm } = useConfirm();
  const { user } = useAuth();
  // FINANCIAL_VIEW (SEC-01): the backend strips `unit_price`/`stock_value`
  // from every materials response for a caller without it (GDPR-03) — the
  // list itself still loads (materials_list is "projected", not gated), so
  // only the price-bearing columns and totals are hidden here.
  const canFinance = canViewFinancials(user?.role);
  // MATERIAL_CREATE/EDIT/DELETE are ADMIN-only on the backend.
  const canManage = canManageMaterials(user?.role);

  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = useDebouncedValue(searchInput).trim().slice(0, MAX_SEARCH_LENGTH);
  const [pageIndex, setPageIndex] = useState(0);
  const [filterLowStock, setFilterLowStock] = useState(false);
  const [sortBy, setSortBy] = useState<SortKey>('name');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedMaterial, setSelectedMaterial] = useState<MaterialType | null>(null);
  const [isPurchaseListOpen, setIsPurchaseListOpen] = useState(false);

  // A new search starts on the first page.
  const [lastSearch, setLastSearch] = useState(debouncedSearch);
  if (debouncedSearch !== lastSearch) {
    setLastSearch(debouncedSearch);
    setPageIndex(0);
  }

  const query = useMaterialsPage(debouncedSearch, pageIndex);

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedMaterial(null);
  };
  const { save, remove } = useMaterialMutations(closeModal);

  const pageRows = query.data?.items ?? [];
  const visibleRows = sortRows(filterLowStock ? pageRows.filter(isLowStock) : pageRows, sortBy, canFinance);
  const { pageNumber, pageCount } = query.data ? pageInfo(query.data) : { pageNumber: 1, pageCount: 1 };
  const totalValue = canFinance
    ? visibleRows.reduce((sum, m) => sum + (m.unit_price ?? 0) * m.stock, 0)
    : null;
  const hasFilter = Boolean(debouncedSearch || filterLowStock);

  const openCreateModal = () => {
    setSelectedMaterial(null);
    setIsModalOpen(true);
  };

  const handleDelete = async (material: MaterialPageItem) => {
    const confirmed = await showConfirm({
      title: 'Material löschen',
      message: `Möchten Sie das Material „${material.name}“ wirklich löschen?`,
      confirmLabel: 'Löschen',
      variant: 'danger',
    });
    if (confirmed) remove.mutate(material.id);
  };

  // Failures are shown by the mutation's onError toast; the dialog stays open.
  const handleFormSubmit = async (data: MaterialFormSubmit) => {
    await save.mutateAsync({ id: selectedMaterial?.id ?? null, data }).catch(() => undefined);
  };

  const columns = buildColumns({
    canFinance,
    canManage,
    onEdit: (m) => {
      setSelectedMaterial(toMaterialType(m));
      setIsModalOpen(true);
    },
    onDelete: (m) => void handleDelete(m),
    isDeleting: remove.isPending,
  });

  const emptyAction = hasFilter ? (
    <Button
      variant="secondary"
      onClick={() => {
        setSearchInput('');
        setFilterLowStock(false);
      }}
    >
      Filter zurücksetzen
    </Button>
  ) : canManage ? (
    <Button icon="plus" onClick={openCreateModal}>
      Material anlegen
    </Button>
  ) : undefined;

  return (
    <div className="page-container materials-page">
      <PageHeader
        title="Materialien"
        meta={
          query.data && (
            <>
              {query.data.total} Materialien
              {totalValue !== null && (
                <>
                  {' '}• Gesamtwert: <span className={MONEY_CLASS}>{formatEur(totalValue)}</span>
                </>
              )}
            </>
          )
        }
        primaryAction={
          canManage ? (
            <Button icon="plus" onClick={openCreateModal}>
              Material anlegen
            </Button>
          ) : undefined
        }
        secondaryActions={
          <Button variant="secondary" icon="clipboard" onClick={() => setIsPurchaseListOpen(true)}>
            Bestellliste
          </Button>
        }
      />

      <div className="materials-controls">
        <Field label="Suche" name="materials-search" inputMode="search" className="materials-controls__search">
          <input
            type="search"
            placeholder="Name oder Lieferant …"
            maxLength={MAX_SEARCH_LENGTH}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </Field>
        <Field label="Sortieren" name="materials-sort-by">
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortKey)}>
            <option value="name">Name</option>
            {canFinance && <option value="price">Preis</option>}
            <option value="stock">Bestand</option>
          </select>
        </Field>
        <label className="materials-controls__check">
          <input
            type="checkbox"
            checked={filterLowStock}
            onChange={(e) => setFilterLowStock(e.target.checked)}
          />
          Nur niedriger Bestand
        </label>
      </div>

      <DataTable
        rows={visibleRows}
        columns={columns}
        getRowKey={(m) => m.id}
        caption="Materialien"
        state={listState(query, visibleRows.length)}
        empty={{
          icon: 'inbox',
          title: hasFilter ? 'Keine Materialien gefunden' : 'Noch keine Materialien',
          body: hasFilter ? 'Suche oder Filter ändern.' : undefined,
          action: emptyAction,
        }}
      />

      {query.data && (
        <Pager
          label="Seiten der Materialliste"
          pageNumber={pageNumber}
          pageCount={pageCount}
          hasNext={query.data.next_offset != null}
          isFetching={query.isFetching}
          onPrevious={() => setPageIndex((index) => Math.max(index - 1, 0))}
          onNext={() => setPageIndex((index) => index + 1)}
        />
      )}

      {canManage && (
        <MaterialFormModal
          isOpen={isModalOpen}
          onClose={closeModal}
          onSubmit={handleFormSubmit}
          material={selectedMaterial}
          isLoading={save.isPending}
        />
      )}

      <PurchaseListModal isOpen={isPurchaseListOpen} onClose={() => setIsPurchaseListOpen(false)} />
    </div>
  );
};
