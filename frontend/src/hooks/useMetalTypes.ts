/**
 * useMetalTypes — fetch and cache the unified metal-type list.
 *
 * Returns all built-in MetalType enum values plus active custom types from
 * the database.  Results are grouped by base_metal for easy rendering in
 * <optgroup> dropdowns.
 *
 * Usage:
 *   const { metalTypes, groupedMetalTypes, isLoading, error } = useMetalTypes();
 */
import { useEffect, useState, useCallback } from 'react';
import { metalTypesApi } from '../api';
import { MetalTypeOption } from '../types';

export interface GroupedMetalTypes {
  [baseMetal: string]: MetalTypeOption[];
}

export interface UseMetalTypesResult {
  /** Flat sorted list (base_metal order, then display_name) */
  metalTypes: MetalTypeOption[];
  /** Same list grouped by base_metal key for <optgroup> rendering */
  groupedMetalTypes: GroupedMetalTypes;
  isLoading: boolean;
  error: string | null;
  /** Manually refresh the list (call after creating/updating/deleting) */
  refresh: () => void;
}

// Module-level simple cache: avoids re-fetching on every mount within a
// single browser session.  Invalidated by calling refresh().
let _cache: MetalTypeOption[] | null = null;
let _listeners: Array<() => void> = [];

function notifyListeners(): void {
  _listeners.forEach((fn) => fn());
}

export function invalidateMetalTypesCache(): void {
  _cache = null;
  notifyListeners();
}

const BASE_METAL_ORDER = ['gold', 'silver', 'platinum', 'palladium'];

function groupByBaseMetal(types: MetalTypeOption[]): GroupedMetalTypes {
  const groups: GroupedMetalTypes = {};
  for (const t of types) {
    if (!groups[t.base_metal]) {
      groups[t.base_metal] = [];
    }
    groups[t.base_metal].push(t);
  }
  // Sort groups in canonical order
  const ordered: GroupedMetalTypes = {};
  for (const base of BASE_METAL_ORDER) {
    if (groups[base]) {
      ordered[base] = groups[base];
    }
  }
  // Append any unexpected base_metal values at the end
  for (const key of Object.keys(groups)) {
    if (!ordered[key]) {
      ordered[key] = groups[key];
    }
  }
  return ordered;
}

export function useMetalTypes(): UseMetalTypesResult {
  const [metalTypes, setMetalTypes] = useState<MetalTypeOption[]>(_cache ?? []);
  const [isLoading, setIsLoading] = useState(_cache === null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  // Subscribe to external cache invalidations
  useEffect(() => {
    const listener = () => setVersion((v) => v + 1);
    _listeners.push(listener);
    return () => {
      _listeners = _listeners.filter((l) => l !== listener);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    if (_cache !== null) {
      setMetalTypes(_cache);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    metalTypesApi
      .getAll()
      .then((data) => {
        if (!cancelled) {
          _cache = data;
          setMetalTypes(data);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const msg =
            err instanceof Error ? err.message : 'Metalltypen konnten nicht geladen werden.';
          setError(msg);
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
    // version dependency forces re-fetch after invalidation
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  const refresh = useCallback(() => {
    invalidateMetalTypesCache();
  }, []);

  return {
    metalTypes,
    groupedMetalTypes: groupByBaseMetal(metalTypes),
    isLoading,
    error,
    refresh,
  };
}
