// Reparaturen — server-paged list on TanStack Query (W4-03, playbook 5.1).
//
// GET /repairs/?offset=… returns a Page envelope; status filter, `q` search
// and sort run on the server. The status filter lives in the URL
// (?status=…), `?neu=1` opens the counter intake and `&customer_id=`
// preselects the customer (link from the customer page's Verlauf).
import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { repairsApi, type RepairPageItem, type RepairPageParams } from '../api/repairs';
import { compactParams, DEFAULT_PAGE_SIZE, pageInfo } from '../api/paged';
import { repairKeys } from '../api/repairQueries';
import { Pager } from '../components/Pager';
import { RepairIntakeScreen } from '../components/repairs/RepairIntakeScreen';
import { customerName, formatRepairDate, itemTypeLabel } from '../components/repairs/repairFormat';
import { useAuth } from '../contexts';
import { REPAIR_STATUS } from '../design/status';
import { getErrorMessage } from '../lib/errors';
import { formatEur, MISSING_VALUE } from '../lib/format';
import { canCreateRepairs, canViewFinancials } from '../lib/roles';
import { useDebouncedValue } from '../lib/useDebouncedValue';
import type { RepairJobStatus } from '../types';
import {
  Button,
  DataTable,
  DeadlineChip,
  Field,
  PageHeader,
  type Column,
  type PageStateValue,
} from '../ui';
import { StatusBadge } from '../ui/StatusBadge';
import '../styles/repairs.css';

const INTAKE_PARAM = 'neu';
const CUSTOMER_PARAM = 'customer_id';
const STATUS_PARAM = 'status';
/** Backend `q` accepts 1-100 characters. */
const MAX_SEARCH_LENGTH = 100;

const STATUS_OPTIONS = (Object.keys(REPAIR_STATUS) as RepairJobStatus[]).map((value) => ({
  value,
  label: REPAIR_STATUS[value].label,
}));

/** Whitelist: created_at, status, estimated_completion_date, repair_number. */
const SORT_OPTIONS = [
  { value: '', label: 'Neueste zuerst (Standard)' },
  { value: 'estimated_completion_date', label: 'Zusage: nächste zuerst' },
  { value: '-estimated_completion_date', label: 'Zusage: späteste zuerst' },
  { value: 'repair_number', label: 'Nummer aufsteigend' },
] as const;

/** A closed repair has no deadline any more; show the date, not "überfällig". */
const CLOSED_STATUSES: ReadonlySet<RepairJobStatus> = new Set(['picked_up', 'cancelled']);

function parseStatus(value: string | null): RepairJobStatus | '' {
  return value && value in REPAIR_STATUS ? (value as RepairJobStatus) : '';
}

function RepairDeadline({ row }: { row: RepairPageItem }) {
  if (!row.estimated_completion_date) return <>{MISSING_VALUE}</>;
  if (CLOSED_STATUSES.has(row.status)) return <>{formatRepairDate(row.estimated_completion_date)}</>;
  return <DeadlineChip deadline={row.estimated_completion_date} />;
}

function buildColumns(showPrice: boolean): Column<RepairPageItem>[] {
  const columns: Column<RepairPageItem>[] = [
    { key: 'repair_number', header: 'Nr.', render: (r) => r.repair_number },
    { key: 'bag_number', header: 'Tüte', render: (r) => r.bag_number, hideBelow: 'desktop' },
    { key: 'customer', header: 'Kunde', render: (r) => customerName(r.customer) ?? 'Laufkunde' },
    {
      key: 'item',
      header: 'Gegenstand',
      render: (r) => (
        <span className="repair-item-cell" title={r.item_description}>
          {itemTypeLabel(r.item_type)}
          {r.metal_type && <span className="repair-item-cell__metal">{r.metal_type}</span>}
        </span>
      ),
    },
    { key: 'status', header: 'Status', render: (r) => <StatusBadge kind="repair" status={r.status} /> },
    { key: 'deadline', header: 'Zugesagt bis', render: (r) => <RepairDeadline row={r} /> },
  ];
  if (showPrice) {
    columns.push({ key: 'kva', header: 'KVA', numeric: true, render: (r) => formatEur(r.estimated_cost) });
  }
  return columns;
}

function useRepairsPage(params: RepairPageParams) {
  return useQuery({
    queryKey: repairKeys.page(params),
    queryFn: ({ signal }) => repairsApi.getPage(params, signal),
    placeholderData: keepPreviousData,
  });
}

function listState(query: ReturnType<typeof useRepairsPage>): PageStateValue {
  if (query.isPending) return { status: 'loading' };
  if (query.isError && !query.data) {
    return {
      status: 'error',
      error: getErrorMessage(query.error, 'Reparaturen konnten nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }
  return { status: query.data?.items.length ? 'ready' : 'empty' };
}

export function RepairsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const showPrice = canViewFinancials(user?.role);
  const canCreate = canCreateRepairs(user?.role);
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchInput, setSearchInput] = useState('');
  const search = useDebouncedValue(searchInput).trim().slice(0, MAX_SEARCH_LENGTH);
  const [sort, setSort] = useState('');
  const [pageIndex, setPageIndex] = useState(0);

  const status = parseStatus(searchParams.get(STATUS_PARAM));
  const isIntakeOpen = searchParams.get(INTAKE_PARAM) === '1';
  const intakeCustomerId = Number(searchParams.get(CUSTOMER_PARAM)) || undefined;

  // A new filter, search or sort starts on the first page.
  const filterKey = `${status}|${search}|${sort}`;
  const [lastFilterKey, setLastFilterKey] = useState(filterKey);
  if (filterKey !== lastFilterKey) {
    setLastFilterKey(filterKey);
    setPageIndex(0);
  }

  const params = compactParams({
    limit: DEFAULT_PAGE_SIZE,
    offset: pageIndex * DEFAULT_PAGE_SIZE,
    status: status || undefined,
    q: search || undefined,
    sort: sort || undefined,
  }) as RepairPageParams;
  const query = useRepairsPage(params);

  const updateParams = (change: (next: URLSearchParams) => void, replace = false) => {
    const next = new URLSearchParams(searchParams);
    change(next);
    setSearchParams(next, { replace });
  };
  const openIntake = () => updateParams((next) => next.set(INTAKE_PARAM, '1'));
  const closeIntake = () =>
    updateParams((next) => {
      next.delete(INTAKE_PARAM);
      next.delete(CUSTOMER_PARAM);
    }, true);
  const setStatus = (value: RepairJobStatus | '') =>
    updateParams((next) => (value ? next.set(STATUS_PARAM, value) : next.delete(STATUS_PARAM)), true);
  const resetFilters = () => {
    setSearchInput('');
    setStatus('');
  };

  const hasFilter = Boolean(status || search);
  const rows = query.data?.items ?? [];
  const { pageNumber, pageCount } = query.data ? pageInfo(query.data) : { pageNumber: 1, pageCount: 1 };
  const total = query.data?.total ?? 0;

  const emptyAction = hasFilter ? (
    <Button variant="secondary" onClick={resetFilters}>
      Filter zurücksetzen
    </Button>
  ) : canCreate ? (
    <Button icon="plus" onClick={openIntake}>
      Neue Reparatur annehmen
    </Button>
  ) : undefined;

  return (
    <div className="repairs-page">
      <PageHeader
        title="Reparaturen"
        meta={query.data ? <span>{total} Reparaturen</span> : undefined}
        primaryAction={
          canCreate ? (
            <Button icon="plus" onClick={openIntake}>
              Neue Reparatur
            </Button>
          ) : undefined
        }
      />

      <div className="repairs-filters">
        <Field label="Suche" name="repairs-search" inputMode="search" className="repairs-filters__search">
          <input
            type="search"
            placeholder="Nr., Tüte, Beschreibung oder Kunde …"
            maxLength={MAX_SEARCH_LENGTH}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </Field>
        <Field label="Status" name="repairs-status">
          <select value={status} onChange={(e) => setStatus(parseStatus(e.target.value))}>
            <option value="">Alle Status</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Sortieren" name="repairs-sort">
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <DataTable
        rows={rows}
        columns={buildColumns(showPrice)}
        getRowKey={(r) => r.id}
        rowHref={(r) => `/repairs/${r.id}`}
        caption="Reparaturen"
        state={listState(query)}
        empty={{
          icon: 'wrench',
          title: 'Keine Reparaturen gefunden',
          body: hasFilter
            ? 'Suche oder Filter ändern.'
            : 'Nehmen Sie die erste Reparatur an der Theke an.',
          action: emptyAction,
        }}
        cardTitle={(r) => `${r.repair_number} · ${itemTypeLabel(r.item_type)}`}
        cardMeta={(r) => customerName(r.customer) ?? 'Laufkunde'}
        cardBadges={(r) => (
          <>
            <StatusBadge kind="repair" status={r.status} />
            <RepairDeadline row={r} />
          </>
        )}
      />

      {rows.length > 0 && (
        <Pager
          label="Seiten der Reparaturliste"
          pageNumber={pageNumber}
          pageCount={pageCount}
          summary={`${total} Reparaturen`}
          onPrevious={() => setPageIndex((i) => Math.max(0, i - 1))}
          onNext={() => setPageIndex((i) => i + 1)}
          hasNext={query.data?.next_offset != null}
          isFetching={query.isFetching}
        />
      )}

      {isIntakeOpen && (
        <RepairIntakeScreen
          onClose={closeIntake}
          // FE-17: after the intake, go straight to the new repair.
          onDone={(repairId) => navigate(`/repairs/${repairId}`)}
          initialCustomerId={intakeCustomerId}
        />
      )}
    </div>
  );
}
