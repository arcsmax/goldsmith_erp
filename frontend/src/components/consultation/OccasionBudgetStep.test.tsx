// OccasionBudgetStep — Beratungs-Wizard step 2 tests.
//
// Pins two behaviors from the Task 4 brief:
//   (a) all 8 occasion chips render with their German label; clicking one
//       marks it selected and reports {occasion: '<key>'} via onFieldsChange.
//   (b) an invalid budget range (von > bis) shows the German error message
//       inline and reports the step as INVALID (onFieldsChange(null)) — the
//       wizard engine blocks Weiter entirely until the range is fixed.
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OccasionBudgetStep, OCCASION_LABELS } from './OccasionBudgetStep';
import type { Consultation } from '../../types';

function makeConsultation(overrides: Partial<Consultation> = {}): Consultation {
  return {
    id: 1,
    customer_id: 5,
    conducted_by: 1,
    status: 'draft',
    occasion: 'other',
    photos: [],
    created_at: '2026-07-02T10:00:00',
    updated_at: '2026-07-02T10:00:00',
    ...overrides,
  };
}

const noopPatch = vi.fn(async () => true);
const noopRefresh = vi.fn(async () => undefined);

describe('OccasionBudgetStep', () => {
  it('renders all 8 occasion chips with German labels; clicking one selects it and reports the occasion', async () => {
    const onFieldsChange = vi.fn();
    render(
      <OccasionBudgetStep
        consultation={makeConsultation()}
        onPatch={noopPatch}
        refresh={noopRefresh}
        onFieldsChange={onFieldsChange}
      />
    );

    const labels = Object.values(OCCASION_LABELS);
    expect(labels).toHaveLength(8);
    labels.forEach((label) => {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    });

    const weddingChip = screen.getByRole('button', { name: OCCASION_LABELS.wedding });
    await userEvent.click(weddingChip);

    expect(weddingChip).toHaveClass('selected');
    expect(onFieldsChange).toHaveBeenCalledWith(expect.objectContaining({ occasion: 'wedding' }));
  });

  it('shows the German range error and withholds the patch when budget_min > budget_max', () => {
    const onFieldsChange = vi.fn();
    render(
      <OccasionBudgetStep
        consultation={makeConsultation()}
        onPatch={noopPatch}
        refresh={noopRefresh}
        onFieldsChange={onFieldsChange}
      />
    );

    fireEvent.change(screen.getByLabelText('Budget von €'), { target: { value: '500' } });
    fireEvent.change(screen.getByLabelText('Budget bis €'), { target: { value: '100' } });

    expect(
      screen.getByText('Von-Budget darf nicht über dem Bis-Budget liegen')
    ).toBeInTheDocument();
    expect(onFieldsChange).toHaveBeenLastCalledWith(null);
  });

  it('shows the German negative-value error and withholds the patch when budget_min is negative', () => {
    // HTML min="0" only constrains the spinner arrows — typing '-50' still
    // lands in state, so the Zod .min(0) failure must surface inline instead
    // of silently dropping the patch via onFieldsChange({}).
    const onFieldsChange = vi.fn();
    render(
      <OccasionBudgetStep
        consultation={makeConsultation()}
        onPatch={noopPatch}
        refresh={noopRefresh}
        onFieldsChange={onFieldsChange}
      />
    );

    fireEvent.change(screen.getByLabelText('Budget von €'), { target: { value: '-50' } });

    expect(screen.getByText('Darf nicht negativ sein')).toBeInTheDocument();
    expect(onFieldsChange).toHaveBeenLastCalledWith(null);
  });
});
