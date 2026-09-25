import React from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EmptyState } from './EmptyState';
import { PageState, SKELETON_DELAY_MS } from './PageState';

describe('EmptyState', () => {
  it('shows a heading, body, decorative icon and the action', () => {
    const { container } = render(
      <EmptyState
        icon="inbox"
        title="Noch keine Aufträge"
        body="Lege den ersten Auftrag an oder scanne eine Auftragstüte."
        action={<button type="button">Ersten Auftrag anlegen</button>}
        secondaryAction={<button type="button">QR-Code scannen</button>}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Noch keine Aufträge' })).toBeInTheDocument();
    expect(screen.getByText(/Lege den ersten Auftrag an/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ersten Auftrag anlegen' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'QR-Code scannen' })).toBeInTheDocument();
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('PageState', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('announces loading immediately and shows the skeleton only after the delay', () => {
    const { container } = render(
      <PageState state={{ status: 'loading' }}>
        <p>Inhalt</p>
      </PageState>,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Wird geladen…');
    expect(container.querySelector('.ui-skeleton')).toBeNull();
    act(() => {
      vi.advanceTimersByTime(SKELETON_DELAY_MS);
    });
    const skeleton = container.querySelector('.ui-skeleton');
    expect(skeleton).not.toBeNull();
    expect(skeleton).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByText('Inhalt')).not.toBeInTheDocument();
  });

  it('shows the error with a retry button', () => {
    vi.useRealTimers();
    const retry = vi.fn();
    render(
      <PageState state={{ status: 'error', error: 'Kunden konnten nicht geladen werden.', retry }}>
        <p>Inhalt</p>
      </PageState>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Kunden konnten nicht geladen werden.');
    return userEvent.click(screen.getByRole('button', { name: 'Erneut versuchen' })).then(() => {
      expect(retry).toHaveBeenCalledTimes(1);
    });
  });

  it('falls back to a generic German error text', () => {
    render(<PageState state={{ status: 'error' }}>x</PageState>);
    expect(screen.getByRole('alert')).toHaveTextContent('Daten konnten nicht geladen werden.');
    expect(screen.queryByRole('button', { name: 'Erneut versuchen' })).not.toBeInTheDocument();
  });

  it('renders the EmptyState for empty', () => {
    render(
      <PageState state={{ status: 'empty' }} empty={{ title: 'Keine Treffer' }}>
        x
      </PageState>,
    );
    expect(screen.getByRole('heading', { name: 'Keine Treffer' })).toBeInTheDocument();
  });

  it('renders children when ready', () => {
    render(<PageState state={{ status: 'ready' }}>Inhalt</PageState>);
    expect(screen.getByText('Inhalt')).toBeInTheDocument();
  });
});
