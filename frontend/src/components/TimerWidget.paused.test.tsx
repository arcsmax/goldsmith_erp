// W4-03: the paused state (D-15, server-side pause) on the bench timer.
// "Pausiert" is always icon + text (StatusBadge), never colour alone, and
// is announced on the collapsed FAB too.
import { describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, render, screen } from '@testing-library/react';

import TimerWidget from './TimerWidget';
import type { TimeEntry } from '../types';

const entry = (overrides: Partial<TimeEntry> = {}): TimeEntry => ({
  id: 'paused-entry',
  order_id: 77,
  user_id: 1,
  activity_id: 2,
  start_time: new Date(Date.now() - 600_000).toISOString(),
  end_time: null,
  duration_minutes: null,
  location: null,
  complexity_rating: null,
  quality_rating: null,
  rework_required: false,
  notes: null,
  extra_metadata: null,
  is_paused: true,
  created_at: new Date(Date.now() - 600_000).toISOString(),
  ...overrides,
});

const expand = () => act(() => void window.dispatchEvent(new Event('timer:expand')));

describe('TimerWidget paused state (W4-03)', () => {
  it('announces "Pausiert" on the collapsed FAB', () => {
    render(<TimerWidget runningEntry={entry()} onStop={vi.fn()} />);
    expect(screen.getByRole('button')).toHaveTextContent('Pausiert');
  });

  it('shows the Pausiert badge with its icon and marks the panel as paused', () => {
    render(<TimerWidget runningEntry={entry()} onStop={vi.fn()} onResume={vi.fn()} />);
    expand();

    const badge = screen.getByText('Pausiert').closest('.ui-status-badge');
    expect(badge).not.toBeNull();
    expect(badge?.querySelector('svg')).not.toBeNull();
    expect(screen.getByRole('region', { name: 'Laufende Zeiterfassung' })).toHaveClass(
      'timer-widget--paused',
    );
    expect(screen.getByRole('button', { name: 'Weiter' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument();
  });

  it('uses 56px bench buttons for the timer controls', () => {
    render(<TimerWidget runningEntry={entry({ is_paused: false })} onStop={vi.fn()} onPause={vi.fn()} />);
    expand();
    for (const name of ['Pause', 'Stopp']) {
      expect(screen.getByRole('button', { name })).toHaveClass('ui-button--lg');
    }
    expect(screen.queryByText('Pausiert')).not.toBeInTheDocument();
  });
});
