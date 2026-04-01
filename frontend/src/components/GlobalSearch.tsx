// Global Search Component
// Searches orders, customers, and materials client-side / via API.
// Designed for workshop use: large touch targets (min 44px), high contrast.
import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  KeyboardEvent,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { ordersApi } from '../api/orders';
import { customersApi } from '../api/customers';
import { materialsApi } from '../api/materials';
import { OrderType, CustomerListItem, MaterialType } from '../types';

interface SearchResult {
  type: 'order' | 'customer' | 'material';
  id: number;
  label: string;
  sublabel?: string;
  href: string;
}

const DEBOUNCE_MS = 300;
const MAX_RESULTS_PER_GROUP = 4;
const MIN_QUERY_LENGTH = 2;

/** Simple substring match — case-insensitive, handles undefined gracefully */
function matches(value: string | null | undefined, query: string): boolean {
  if (!value) return false;
  return value.toLowerCase().includes(query.toLowerCase());
}

function filterOrders(orders: OrderType[], query: string): SearchResult[] {
  return orders
    .filter(
      (o) =>
        matches(String(o.id), query) ||
        matches(o.title, query) ||
        matches(o.description, query)
    )
    .slice(0, MAX_RESULTS_PER_GROUP)
    .map((o) => ({
      type: 'order' as const,
      id: o.id,
      label: `#${o.id} — ${o.title}`,
      sublabel: o.status,
      href: `/orders/${o.id}`,
    }));
}

function filterMaterials(materials: MaterialType[], query: string): SearchResult[] {
  return materials
    .filter((m) => matches(m.name, query) || matches(m.description, query))
    .slice(0, MAX_RESULTS_PER_GROUP)
    .map((m) => ({
      type: 'material' as const,
      id: m.id,
      label: m.name,
      sublabel: m.description ?? undefined,
      href: `/materials`,
    }));
}

function mapCustomers(customers: CustomerListItem[]): SearchResult[] {
  return customers.slice(0, MAX_RESULTS_PER_GROUP).map((c) => ({
    type: 'customer' as const,
    id: c.id,
    label: `${c.first_name} ${c.last_name}`,
    sublabel: c.company_name ?? c.email,
    href: `/customers/${c.id}`,
  }));
}

const GROUP_LABELS: Record<string, string> = {
  order: 'Aufträge',
  customer: 'Kunden',
  material: 'Materialien',
};

export const GlobalSearch: React.FC = () => {
  const navigate = useNavigate();
  const [isExpanded, setIsExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  // Cache fetched data so we only fetch once per session
  const ordersCache = useRef<OrderType[] | null>(null);
  const materialsCache = useRef<MaterialType[] | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Open the search input
  const handleOpen = useCallback(() => {
    setIsExpanded(true);
    // Focus happens after the input is rendered
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  const handleClose = useCallback(() => {
    setIsExpanded(false);
    setQuery('');
    setResults([]);
    setActiveIndex(-1);
  }, []);

  // Close on click outside
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        handleClose();
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [handleClose]);

  // Close on Escape key (global)
  useEffect(() => {
    const handleKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [handleClose]);

  // Perform search with debounce
  const performSearch = useCallback(async (q: string) => {
    if (q.length < MIN_QUERY_LENGTH) {
      setResults([]);
      return;
    }

    setIsLoading(true);
    try {
      // Fetch orders and materials from cache or API in parallel
      const [orders, materials, customers] = await Promise.all([
        ordersCache.current !== null
          ? Promise.resolve(ordersCache.current)
          : ordersApi.getAll({ limit: 200 }).then((data) => {
              ordersCache.current = data;
              return data;
            }),
        materialsCache.current !== null
          ? Promise.resolve(materialsCache.current)
          : materialsApi.getAll({ limit: 200 }).then((data) => {
              materialsCache.current = data;
              return data;
            }),
        // Customer search uses the dedicated backend search endpoint
        customersApi.search(q, MAX_RESULTS_PER_GROUP),
      ]);

      const orderResults = filterOrders(orders, q);
      const customerResults = mapCustomers(customers);
      const materialResults = filterMaterials(materials, q);

      setResults([...orderResults, ...customerResults, ...materialResults]);
      setActiveIndex(-1);
    } catch {
      // Search errors are non-critical — silently clear results
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleQueryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const q = e.target.value;
    setQuery(q);

    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => performSearch(q), DEBOUNCE_MS);
  };

  // Keyboard navigation within the dropdown
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, -1));
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      const result = results[activeIndex];
      if (result) navigate(result.href);
      handleClose();
    }
  };

  const handleResultClick = (result: SearchResult) => {
    navigate(result.href);
    handleClose();
  };

  // Group results by type for display
  const grouped = results.reduce<Record<string, SearchResult[]>>((acc, r) => {
    if (!acc[r.type]) acc[r.type] = [];
    acc[r.type].push(r);
    return acc;
  }, {});
  const groupOrder: Array<'order' | 'customer' | 'material'> = ['order', 'customer', 'material'];

  // Flat list with position index for keyboard navigation
  let flatIndex = 0;
  const groupedWithIndex: Array<{
    groupKey: string;
    items: Array<{ result: SearchResult; index: number }>;
  }> = groupOrder
    .filter((key) => grouped[key]?.length)
    .map((key) => ({
      groupKey: key,
      items: (grouped[key] || []).map((result) => ({ result, index: flatIndex++ })),
    }));

  const hasResults = results.length > 0;
  const showDropdown = isExpanded && query.length >= MIN_QUERY_LENGTH;

  return (
    <div className="global-search" ref={containerRef}>
      {/* Collapsed state: icon button */}
      {!isExpanded && (
        <button
          className="global-search__trigger"
          onClick={handleOpen}
          aria-label="Suche öffnen"
          title="Suchen (Aufträge, Kunden, Materialien)"
        >
          <SearchIcon />
        </button>
      )}

      {/* Expanded state: input + dropdown */}
      {isExpanded && (
        <div className="global-search__input-wrapper">
          <span className="global-search__input-icon" aria-hidden="true">
            <SearchIcon />
          </span>
          <input
            ref={inputRef}
            className="global-search__input"
            type="search"
            value={query}
            onChange={handleQueryChange}
            onKeyDown={handleKeyDown}
            placeholder="Suchen... (Aufträge, Kunden, Materialien)"
            aria-label="Globale Suche"
            aria-autocomplete="list"
            aria-controls="global-search-results"
            aria-expanded={showDropdown}
            role="combobox"
            autoComplete="off"
          />
          {isLoading && (
            <span className="global-search__spinner" aria-label="Suche läuft..." />
          )}
          <button
            className="global-search__close"
            onClick={handleClose}
            aria-label="Suche schließen"
          >
            ✕
          </button>

          {/* Dropdown */}
          {showDropdown && (
            <div
              id="global-search-results"
              className="global-search__dropdown"
              role="listbox"
              aria-label="Suchergebnisse"
            >
              {!hasResults && !isLoading && (
                <p className="global-search__empty">Keine Ergebnisse für "{query}"</p>
              )}

              {groupedWithIndex.map(({ groupKey, items }) => (
                <div key={groupKey} className="global-search__group">
                  <p className="global-search__group-label">
                    {GROUP_LABELS[groupKey]}
                  </p>
                  {items.map(({ result, index }) => (
                    <button
                      key={`${result.type}-${result.id}`}
                      className={`global-search__result${activeIndex === index ? ' global-search__result--active' : ''}`}
                      onClick={() => handleResultClick(result)}
                      onMouseEnter={() => setActiveIndex(index)}
                      role="option"
                      aria-selected={activeIndex === index}
                    >
                      <span className="global-search__result-type-icon">
                        {result.type === 'order' && '📋'}
                        {result.type === 'customer' && '📇'}
                        {result.type === 'material' && '💎'}
                      </span>
                      <span className="global-search__result-text">
                        <span className="global-search__result-label">{result.label}</span>
                        {result.sublabel && (
                          <span className="global-search__result-sublabel">
                            {result.sublabel}
                          </span>
                        )}
                      </span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const SearchIcon: React.FC = () => (
  <svg
    width="20"
    height="20"
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

export default GlobalSearch;
