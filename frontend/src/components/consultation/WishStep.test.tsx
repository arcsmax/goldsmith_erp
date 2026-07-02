// WishStep — Beratungs-Wizard step 3 tests.
//
// Pins three behaviors from the Task 4 brief:
//   (a) clicking the 'Ring' piece-type chip reports {piece_type: 'ring'}.
//   (b) typing in the wishes textarea reports the text.
//   (c) adding a material chip ("Rotgold 585" + Enter) reports
//       materials_discussed: [{metal: 'Rotgold 585'}].
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WishStep, PIECE_TYPE_LABELS } from './WishStep';
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

describe('WishStep', () => {
  it('clicking the Ring chip selects it and reports piece_type', async () => {
    const onFieldsChange = vi.fn();
    render(
      <WishStep
        consultation={makeConsultation()}
        onPatch={noopPatch}
        refresh={noopRefresh}
        onFieldsChange={onFieldsChange}
      />
    );

    const ringChip = screen.getByRole('button', { name: PIECE_TYPE_LABELS.ring });
    await userEvent.click(ringChip);

    expect(ringChip).toHaveClass('selected');
    expect(onFieldsChange).toHaveBeenCalledWith(expect.objectContaining({ piece_type: 'ring' }));
  });

  it('typing in the wishes textarea reports the text', () => {
    const onFieldsChange = vi.fn();
    render(
      <WishStep
        consultation={makeConsultation()}
        onPatch={noopPatch}
        refresh={noopRefresh}
        onFieldsChange={onFieldsChange}
      />
    );

    fireEvent.change(screen.getByLabelText('Was wünscht sich die Kundin?'), {
      target: { value: 'Ein schlichter Ring mit kleinem Diamanten' },
    });

    expect(onFieldsChange).toHaveBeenCalledWith(
      expect.objectContaining({ wishes: 'Ein schlichter Ring mit kleinem Diamanten' })
    );
  });

  it('adding a material chip via Enter reports materials_discussed', async () => {
    const onFieldsChange = vi.fn();
    render(
      <WishStep
        consultation={makeConsultation()}
        onPatch={noopPatch}
        refresh={noopRefresh}
        onFieldsChange={onFieldsChange}
      />
    );

    const input = screen.getByLabelText('Besprochene Materialien');
    await userEvent.type(input, 'Rotgold 585{Enter}');

    expect(onFieldsChange).toHaveBeenCalledWith(
      expect.objectContaining({ materials_discussed: [{ metal: 'Rotgold 585' }] })
    );
    expect(screen.getByRole('button', { name: 'Rotgold 585 entfernen' })).toBeInTheDocument();
    // Input clears after adding so the same key can be typed again.
    expect(input).toHaveValue('');
  });
});
