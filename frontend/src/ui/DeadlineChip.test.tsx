import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DeadlineChip, describeDeadline } from './DeadlineChip';

const NOW = new Date(2026, 8, 25, 14, 30); // Do., 25.09.2026 14:30 local

describe('describeDeadline', () => {
  it.each([
    ['2026-10-04', 'neutral', 'in 9 Tagen'],
    ['2026-09-29', 'neutral', 'in 4 Tagen'],
    ['2026-09-28', 'waiting', 'in 3 Tagen'],
    ['2026-09-27', 'waiting', 'in 2 Tagen'],
    ['2026-09-26', 'waiting', 'morgen fällig'],
    ['2026-09-25', 'waiting', 'heute fällig'],
    ['2026-09-24', 'danger', '1 Tag überfällig'],
    ['2026-09-22', 'danger', '3 Tage überfällig'],
    ['2026-09-22T08:00:00', 'danger', '3 Tage überfällig'],
  ])('%s -> %s "%s"', (deadline, tone, label) => {
    const result = describeDeadline(deadline, NOW);
    expect(result.tone).toBe(tone);
    expect(result.label).toBe(label);
  });

  it('handles a missing or invalid deadline', () => {
    expect(describeDeadline(null, NOW)).toMatchObject({ tone: 'none', label: 'Keine Frist' });
    expect(describeDeadline('kaputt', NOW)).toMatchObject({ tone: 'none', label: 'Keine Frist' });
  });
});

describe('DeadlineChip', () => {
  it('pairs a shape with text, never colour alone', () => {
    const { container } = render(<DeadlineChip deadline="2026-09-22" now={NOW} />);
    const chip = container.querySelector('.ui-deadline-chip');
    expect(chip).toHaveClass('ui-deadline-chip--danger');
    expect(chip).toHaveTextContent('3 Tage überfällig');
    const shape = container.querySelector('.ui-deadline-chip__shape');
    expect(shape).toHaveAttribute('aria-hidden', 'true');
    expect(shape).toHaveTextContent('■');
  });

  it('uses distinct shapes per urgency', () => {
    const { container, rerender } = render(<DeadlineChip deadline="2026-10-04" now={NOW} />);
    expect(container.querySelector('.ui-deadline-chip__shape')).toHaveTextContent('●');
    rerender(<DeadlineChip deadline="2026-09-27" now={NOW} />);
    expect(container.querySelector('.ui-deadline-chip__shape')).toHaveTextContent('▲');
  });

  it('exposes the exact date via a time element', () => {
    render(<DeadlineChip deadline="2026-10-04" now={NOW} />);
    const time = screen.getByText('in 9 Tagen').closest('time');
    expect(time).toHaveAttribute('dateTime', '2026-10-04');
    expect(time).toHaveAttribute('title', 'Frist: 04.10.2026');
  });

  it('renders "Keine Frist" without a shape', () => {
    const { container } = render(<DeadlineChip deadline={null} now={NOW} />);
    expect(screen.getByText('Keine Frist')).toBeInTheDocument();
    expect(container.querySelector('.ui-deadline-chip__shape')).toBeNull();
  });
});
