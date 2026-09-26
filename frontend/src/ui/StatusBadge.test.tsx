// StatusBadge accessibility contract (UI-UX-PLAYBOOK 4.2; LV-05).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('StatusBadge', () => {
  it('shows a customer-facing label when given, keeping tone and icon from the map', () => {
    const { container } = render(
      <StatusBadge kind="order" status="ready_for_setting" label="In Arbeit" />,
    );
    expect(screen.getByText('In Arbeit')).toBeInTheDocument();
    expect(screen.queryByText('Bereit zum Fassen')).not.toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass('ui-status-badge--progress');
  });

  it('shows the German label, never the raw enum value', () => {
    render(<StatusBadge kind="order" status="confirmed" />);
    expect(screen.getByText('Bestätigt')).toBeInTheDocument();
    expect(screen.queryByText('confirmed')).not.toBeInTheDocument();
    expect(screen.queryByText('CONFIRMED')).not.toBeInTheDocument();
  });

  it('renders a decorative icon next to the label', () => {
    const { container } = render(<StatusBadge kind="repair" status="in_repair" />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByText('In Arbeit')).toBeInTheDocument();
  });

  it('applies the tone and the non-colour border cue from the map', () => {
    const { container } = render(<StatusBadge kind="order" status="draft" />);
    const badge = container.firstElementChild as HTMLElement;
    expect(badge).toHaveClass('status-badge', 'ui-status-badge--neutral', 'ui-status-badge--dashed');
  });

  it('marks cancelled as struck through and delivered as double border', () => {
    const { container, rerender } = render(<StatusBadge kind="order" status="cancelled" />);
    expect(container.firstElementChild).toHaveClass('ui-status-badge--danger', 'ui-status-badge--struck');
    rerender(<StatusBadge kind="order" status="delivered" />);
    expect(container.firstElementChild).toHaveClass('ui-status-badge--handover', 'ui-status-badge--double');
  });

  it('renders an unknown value raw in the neutral tone and warns', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { container } = render(<StatusBadge kind="quote" status="teleported" />);
    expect(screen.getByText('teleported')).toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass('ui-status-badge--neutral');
    expect(warn).toHaveBeenCalledWith('StatusBadge: unknown status', {
      kind: 'quote',
      status: 'teleported',
    });
  });

  it('is plain text, not an interactive control', () => {
    render(<StatusBadge kind="invoice" status="paid" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('Bezahlt')).toBeInTheDocument();
  });
});
