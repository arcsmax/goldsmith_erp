// Global search (W4-03): header trigger opens a src/ui Modal (focus trap,
// Escape, focus return, full screen below 600px) instead of a hand-rolled
// dropdown overlay.
//
// Data: TanStack Query. Orders and materials load once per session when the
// search first opens and are filtered client-side; customers use the backend
// search endpoint with the debounced query. Failures show a message instead
// of an empty result list.
import React, { useId, useRef, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ordersApi, type OrderListItem } from '../api/orders';
import { customersApi } from '../api/customers';
import { materialsApi } from '../api/materials';
import { queryKeys } from '../api/queryKeys';
import { getStatusLabel } from '../design/status';
import { useDebouncedValue } from '../lib/useDebouncedValue';
import type { CustomerListItem, MaterialType } from '../types';
import { Field, Icon, Modal, type IconName } from '../ui';
import '../styles/components/GlobalSearch.css';

type ResultType = 'order' | 'customer' | 'material';

interface SearchResult {
  type: ResultType;
  id: number;
  label: string;
  sublabel?: string;
  href: string;
}

const MAX_RESULTS_PER_GROUP = 4;
const MIN_QUERY_LENGTH = 2;
/** Client-side index size for orders and materials. */
const INDEX_LIMIT = 200;

const GROUPS: ReadonlyArray<{ type: ResultType; label: string; icon: IconName }> = [
  { type: 'order', label: 'Aufträge', icon: 'clipboard' },
  { type: 'customer', label: 'Kunden', icon: 'user-check' },
  { type: 'material', label: 'Material', icon: 'gem' },
];

function matches(value: string | null | undefined, query: string): boolean {
  return Boolean(value) && String(value).toLowerCase().includes(query.toLowerCase());
}

function filterOrders(orders: readonly OrderListItem[], query: string): SearchResult[] {
  return orders
    .filter((o) => matches(String(o.id), query) || matches(o.title, query) || matches(o.description, query))
    .slice(0, MAX_RESULTS_PER_GROUP)
    .map((o) => ({
      type: 'order',
      id: o.id,
      label: `#${o.id} — ${o.title}`,
      sublabel: o.status ? getStatusLabel('order', o.status) : undefined,
      href: `/orders/${o.id}`,
    }));
}

function filterMaterials(materials: readonly MaterialType[], query: string): SearchResult[] {
  return materials
    .filter((m) => matches(m.name, query) || matches(m.description, query))
    .slice(0, MAX_RESULTS_PER_GROUP)
    .map((m) => ({
      type: 'material',
      id: m.id,
      label: m.name,
      sublabel: m.description ?? undefined,
      href: '/materials',
    }));
}

function mapCustomers(customers: readonly CustomerListItem[]): SearchResult[] {
  return customers.slice(0, MAX_RESULTS_PER_GROUP).map((c) => ({
    type: 'customer',
    id: c.id,
    label: `${c.first_name} ${c.last_name}`,
    sublabel: c.company_name ?? c.email ?? c.phone ?? undefined,
    href: `/customers/${c.id}`,
  }));
}

function useSearchResults(isOpen: boolean, rawQuery: string) {
  const query = useDebouncedValue(rawQuery.trim());
  const isActive = isOpen && query.length >= MIN_QUERY_LENGTH;

  const orders = useQuery({
    queryKey: queryKeys.orders.legacyList(INDEX_LIMIT),
    queryFn: () => ordersApi.getAll({ limit: INDEX_LIMIT }),
    enabled: isOpen,
  });
  const materials = useQuery({
    queryKey: queryKeys.materials.list(INDEX_LIMIT),
    queryFn: () => materialsApi.getAll({ limit: INDEX_LIMIT }),
    enabled: isOpen,
  });
  const customers = useQuery({
    queryKey: queryKeys.customers.search(query, MAX_RESULTS_PER_GROUP),
    queryFn: () => customersApi.search(query, MAX_RESULTS_PER_GROUP),
    enabled: isActive,
  });

  const results: SearchResult[] = isActive
    ? [
        ...filterOrders(orders.data ?? [], query),
        ...mapCustomers(customers.data ?? []),
        ...filterMaterials(materials.data ?? [], query),
      ]
    : [];
  const isLoading = isActive && (orders.isPending || materials.isPending || customers.isPending);
  const hasError = isActive && (orders.isError || materials.isError || customers.isError);
  return { query, isActive, results, isLoading, hasError };
}

const SearchIcon: React.FC = () => (
  <svg
    className="global-search__icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

export const GlobalSearch: React.FC = () => {
  const navigate = useNavigate();
  const listboxId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [rawQuery, setRawQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(-1);
  const { query, isActive, results, isLoading, hasError } = useSearchResults(isOpen, rawQuery);

  const handleClose = () => {
    setIsOpen(false);
    setRawQuery('');
    setActiveIndex(-1);
  };

  const openResult = (result: SearchResult) => {
    navigate(result.href);
    handleClose();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, -1));
    } else if (e.key === 'Enter' && results[activeIndex]) {
      e.preventDefault();
      openResult(results[activeIndex]);
    }
  };

  const optionId = (index: number) => `${listboxId}-option-${index}`;
  const groups = GROUPS.map((group) => ({
    ...group,
    items: results
      .map((result, index) => ({ result, index }))
      .filter(({ result }) => result.type === group.type),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="global-search">
      <button
        type="button"
        className="global-search__trigger"
        onClick={() => setIsOpen(true)}
        aria-label="Suche öffnen"
        aria-haspopup="dialog"
        title="Suchen (Aufträge, Kunden, Material)"
      >
        <SearchIcon />
      </button>

      <Modal open={isOpen} onClose={handleClose} title="Suche" initialFocusRef={inputRef} dismissOnBackdrop>
        <Field
          label="Aufträge, Kunden oder Material suchen"
          name="global-search"
          inputMode="search"
          help={`Mindestens ${MIN_QUERY_LENGTH} Zeichen.`}
        >
          <input
            ref={inputRef}
            type="search"
            value={rawQuery}
            onChange={(e) => {
              setRawQuery(e.target.value);
              setActiveIndex(-1);
            }}
            onKeyDown={handleKeyDown}
            role="combobox"
            aria-autocomplete="list"
            aria-controls={listboxId}
            aria-expanded={isActive && results.length > 0}
            aria-activedescendant={activeIndex >= 0 ? optionId(activeIndex) : undefined}
            autoComplete="off"
          />
        </Field>

        <div className="global-search__status" aria-live="polite">
          {isLoading && 'Wird gesucht…'}
          {!isLoading && hasError && (
            <span role="alert">Suche fehlgeschlagen. Bitte erneut versuchen.</span>
          )}
          {!isLoading && !hasError && isActive && results.length === 0 && `Keine Treffer für „${query}“.`}
        </div>

        <div id={listboxId} role="listbox" aria-label="Suchergebnisse" className="global-search__results">
          {groups.map((group) => (
            <div key={group.type} role="group" aria-label={group.label} className="global-search__group">
              <p className="global-search__group-label" aria-hidden="true">
                {group.label}
              </p>
              {group.items.map(({ result, index }) => (
                <button
                  type="button"
                  key={`${result.type}-${result.id}`}
                  id={optionId(index)}
                  role="option"
                  aria-selected={activeIndex === index}
                  className={`global-search__result${activeIndex === index ? ' global-search__result--active' : ''}`}
                  onClick={() => openResult(result)}
                  onMouseEnter={() => setActiveIndex(index)}
                >
                  <Icon name={group.icon} className="global-search__result-icon" />
                  <span className="global-search__result-text">
                    <span className="global-search__result-label">{result.label}</span>
                    {result.sublabel && (
                      <span className="global-search__result-sublabel">{result.sublabel}</span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
};

export default GlobalSearch;
