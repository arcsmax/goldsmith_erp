// CustomerTypeahead — debounced (300ms) customer search with keyboard nav.
//
// Pins three behaviors:
//   (a) a query that reaches 2 characters fires customersApi.search after the
//       debounce window and renders the returned results;
//   (b) ArrowDown then Enter selects the second result and calls onSelect
//       with that exact customer object (not the first/highlighted-by-default
//       one) — proving keyboard nav actually moves the highlight;
//   (c) a query under 2 characters never calls search, even after the
//       debounce window elapses — avoids noisy single-char lookups.
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
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(handleSelect).toHaveBeenCalledWith(customers[1]);
  });
});
