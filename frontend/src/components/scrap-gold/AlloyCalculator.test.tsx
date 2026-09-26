// AlloyCalculator form contract tests — DOM-19.
//
// The backend's ScrapGoldItemCreate.alloy is the shared AlloyType enum:
// gold codes are the bare fineness number ("585", "750", ...), but silver
// and platinum are prefixed ("ag925", "ag800", "pt950") to disambiguate
// from gold. Before this fix, AlloyCalculator sent `String(selectedAlloy)`
// for every metal — a bare permille number with no prefix — which is
// wrong for silver/platinum and (further downstream, via
// `Number(alloy)` in ScrapGoldTab) got coerced back to a JSON number that
// the backend has never accepted for ANY metal (422 on every add).
//
// These tests pin the exact string handed to `onAddItem` per metal family.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../hooks/useMetalTypes', () => ({
  useMetalTypes: () => ({
    groupedMetalTypes: {},
    metalTypes: [],
    isLoading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

import { AlloyCalculator } from './AlloyCalculator';

beforeEach(() => vi.clearAllMocks());

async function fillAndSubmit(
  user: ReturnType<typeof userEvent.setup>,
  alloyLabel: string,
  weight: string,
  description: string
) {
  await user.type(screen.getByLabelText('Beschreibung'), description);
  await user.selectOptions(screen.getByLabelText('Legierung'), alloyLabel);
  await user.type(screen.getByLabelText('Gewicht'), weight);
  await user.click(screen.getByRole('button', { name: 'Position hinzufügen' }));
}

describe('AlloyCalculator', () => {
  it('sends the bare permille code for a gold alloy (585)', async () => {
    const user = userEvent.setup();
    const onAddItem = vi.fn();
    render(<AlloyCalculator onAddItem={onAddItem} />);

    await fillAndSubmit(user, '585 / 14K', '15', 'Alter Ehering');

    expect(onAddItem).toHaveBeenCalledWith('Alter Ehering', '585', 15);
  });

  it('sends the "ag"-prefixed code for a silver alloy (925), never the bare number', async () => {
    const user = userEvent.setup();
    const onAddItem = vi.fn();
    render(<AlloyCalculator onAddItem={onAddItem} />);

    await fillAndSubmit(user, 'Silber 925', '10', 'Silberkette');

    expect(onAddItem).toHaveBeenCalledWith('Silberkette', 'ag925', 10);
    expect(onAddItem).not.toHaveBeenCalledWith('Silberkette', '925', 10);
  });

  it('sends the "pt"-prefixed code for a platinum alloy (950)', async () => {
    const user = userEvent.setup();
    const onAddItem = vi.fn();
    render(<AlloyCalculator onAddItem={onAddItem} />);

    await fillAndSubmit(user, 'Platin 950', '20', 'Platinring');

    expect(onAddItem).toHaveBeenCalledWith('Platinring', 'pt950', 20);
  });

  it('does not call onAddItem when weight is zero or missing', async () => {
    const user = userEvent.setup();
    const onAddItem = vi.fn();
    render(<AlloyCalculator onAddItem={onAddItem} />);

    await user.type(screen.getByLabelText('Beschreibung'), 'Kette ohne Gewicht');
    // canAdd stays false with no weight entered, so the button is disabled.
    expect(screen.getByRole('button', { name: 'Position hinzufügen' })).toBeDisabled();
    expect(onAddItem).not.toHaveBeenCalled();
  });
});
