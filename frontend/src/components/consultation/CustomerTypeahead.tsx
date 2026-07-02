// CustomerTypeahead — debounced customer search with keyboard navigation.
// Used by CustomerStep (Beratungs-Wizard, step 1) to find an existing
// customer before starting a consultation draft.
import React, { useEffect, useRef, useState } from 'react';
import { customersApi } from '../../api/customers';
import { CustomerListItem } from '../../types';

const SEARCH_DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 2;
const SEARCH_RESULT_LIMIT = 8;

interface CustomerTypeaheadProps {
  onSelect: (customer: CustomerListItem) => void;
  autoFocus?: boolean;
}

export const CustomerTypeahead: React.FC<CustomerTypeaheadProps> = ({ onSelect, autoFocus }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<CustomerListItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const [isSearching, setIsSearching] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (query.trim().length < MIN_QUERY_LENGTH) {
      setResults([]);
      setIsOpen(false);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        setIsSearching(true);
        const data = await customersApi.search(query.trim(), SEARCH_RESULT_LIMIT);
        setResults(data);
        setHighlighted(0);
        setIsOpen(true);
      } catch {
        setResults([]);
      } finally {
        setIsSearching(false);
      }
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const select = (customer: CustomerListItem) => {
    setIsOpen(false);
    setQuery('');
    onSelect(customer);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || results.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlighted((h) => Math.min(h + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlighted((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      select(results[highlighted]);
    } else if (e.key === 'Escape') {
      setIsOpen(false);
    }
  };

  return (
    <div className="typeahead">
      <input
        ref={inputRef}
        type="search"
        role="combobox"
        aria-expanded={isOpen}
        aria-label="Kundin suchen"
        placeholder="Name oder E-Mail suchen..."
        value={query}
        autoFocus={autoFocus}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      {isSearching && <span className="typeahead-hint">Suche...</span>}
      {isOpen && (
        <ul className="typeahead-results" role="listbox">
          {results.length === 0 && (
            <li>
              <span className="typeahead-empty">Keine Treffer</span>
            </li>
          )}
          {results.map((c, i) => (
            <li
              key={c.id}
              className={i === highlighted ? 'highlighted' : ''}
              role="option"
              aria-selected={i === highlighted}
            >
              <button type="button" onClick={() => select(c)}>
                {c.first_name} {c.last_name}
                {c.company_name ? ` (${c.company_name})` : ''}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
