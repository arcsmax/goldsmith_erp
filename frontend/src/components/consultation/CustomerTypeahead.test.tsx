// CustomerTypeahead — debounced (300ms) customer search with keyboard nav.
//
// Pins these behaviors:
//   (a) a query that reaches 2 characters fires customersApi.search after the
//       debounce window and renders the returned results;
//   (b) ArrowDown then Enter selects the second result and calls onSelect
//       with that exact customer object (not the first/highlighted-by-default
//       one) — proving keyboard nav actually moves the highlight — and
//       ArrowDown updates aria-activedescendant to the newly-highlighted
//       option's id;
//   (c) a query under 2 characters never calls search, even after the
//       debounce window elapses — avoids noisy single-char lookups;
//   (d) an earlier, slower search that resolves AFTER a newer one must not
//       clobber the newer results (stale-response guard, mirrors
//       NoGoWarning.tsx's cancelled-flag pattern).
//
// Uses fireEvent + vi.useFakeTimers() rather than userEvent for the typing/
// keyboard steps: userEvent's internal timer-driven Promise machinery hangs
// when combined with Vitest fake timers (observed timeout on all three
// tests), so interactions here are driven directly and the debounce is
// advanced deterministically with vi.advanceTimersByTimeAsync.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

// ---------------------------------------------------------------------------
// API mock — BEFORE the component import (InvoicesPage.test.tsx pattern).
// ---------------------------------------------------------------------------

const mockSearch = vi.fn();

vi.mock('../../api/customers', () => ({
  customersApi: {
    search: (...args: unknown[]) => mockSearch(...args),
  },
}));

// ---------------------------------------------------------------------------
// Component under test
// ---------------------------------------------------------------------------

import { CustomerTypeahead } from './CustomerTypeahead';
import type { CustomerListItem } from '../../types';

function makeCustomer(overrides: Partial<CustomerListItem> = {}): CustomerListItem {
  return {
    id: 1,
    first_name: 'Anna',
    last_name: 'Muster',
    email: 'anna@example.com',
    customer_type: 'private',
    tags: [],
    is_active: true,
    ...overrides,
  };
}

const getInput = () => screen.getByRole('combobox', { name: 'Kundin suchen' });

describe('CustomerTypeahead', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('fires customersApi.search after the debounce once the query reaches 2 characters', async () => {
    mockSearch.mockResolvedValue([makeCustomer()]);

    render(<CustomerTypeahead onSelect={vi.fn()} />);
    fireEvent.change(getInput(), { target: { value: 'mu' } });
    expect(mockSearch).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(mockSearch).toHaveBeenCalledWith('mu', 8);
    expect(screen.getByText(/Anna Muster/)).toBeInTheDocument();
  });

  it('never calls search while the query is under 2 characters', async () => {
    render(<CustomerTypeahead onSelect={vi.fn()} />);
    fireEvent.change(getInput(), { target: { value: 'm' } });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(mockSearch).not.toHaveBeenCalled();
  });

  it('ArrowDown then Enter selects the second result and calls onSelect with it', async () => {
    const customers = [
      makeCustomer({ id: 1, first_name: 'Anna', last_name: 'Muster' }),
      makeCustomer({ id: 2, first_name: 'Max', last_name: 'Mueller' }),
    ];
    mockSearch.mockResolvedValue(customers);
    const handleSelect = vi.fn();

    render(<CustomerTypeahead onSelect={handleSelect} />);
    const input = getInput();
    fireEvent.change(input, { target: { value: 'mu' } });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(screen.getByText(/Max Mueller/)).toBeInTheDocument();

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input).toHaveAttribute('aria-activedescendant', 'typeahead-option-2');

    fireEvent.keyDown(input, { key: 'Enter' });

    expect(handleSelect).toHaveBeenCalledWith(customers[1]);
  });

  it('ignores a stale response that resolves after a newer query already returned', async () => {
    let resolveFirst!: (value: CustomerListItem[]) => void;
    let resolveSecond!: (value: CustomerListItem[]) => void;
    const firstPromise = new Promise<CustomerListItem[]>((resolve) => {
      resolveFirst = resolve;
    });
    const secondPromise = new Promise<CustomerListItem[]>((resolve) => {
      resolveSecond = resolve;
    });
    mockSearch.mockImplementationOnce(() => firstPromise);
    mockSearch.mockImplementationOnce(() => secondPromise);

    render(<CustomerTypeahead onSelect={vi.fn()} />);
    const input = getInput();

    fireEvent.change(input, { target: { value: 'an' } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    fireEvent.change(input, { target: { value: 'ann' } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(mockSearch).toHaveBeenCalledTimes(2);

    // Resolve the NEWER ('ann') query first, then the STALE ('an') one.
    await act(async () => {
      resolveSecond([makeCustomer({ id: 2, first_name: 'Anna', last_name: 'Newer' })]);
      await secondPromise;
    });
    await act(async () => {
      resolveFirst([makeCustomer({ id: 1, first_name: 'Anna', last_name: 'Stale' })]);
      await firstPromise;
    });

    expect(screen.getByText(/Anna Newer/)).toBeInTheDocument();
    expect(screen.queryByText(/Anna Stale/)).not.toBeInTheDocument();
  });
});
