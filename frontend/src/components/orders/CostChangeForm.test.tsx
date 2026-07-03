// CostChangeForm tests — V1.2 Task 5.
//
// Pins:
//   (a) reason < 10 chars blocks submit with an inline message — onSubmit
//       is NOT called (mirrors the backend's CostChangeCreate constraint,
//       so we never round-trip a guaranteed-422).
//   (b) new_amount <= 0 blocks submit with an inline message.
//   (c) a valid submit calls onSubmit with parsed numbers + a line-items
//       array built from the optional add/remove rows.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CostChangeForm } from './CostChangeForm';

afterEach(() => {
  vi.clearAllMocks();
});

describe('CostChangeForm', () => {
  it('blocks submit and shows a message when reason is under 10 characters', async () => {
    const onSubmit = vi.fn();
    render(<CostChangeForm onSubmit={onSubmit} />);

    await userEvent.type(screen.getByLabelText(/Neuer Betrag/), '500');
    await userEvent.type(screen.getByLabelText(/Begründung/), 'zu kurz');
    await userEvent.click(screen.getByRole('button', { name: 'Kostenänderung anlegen' }));

    expect(await screen.findByText(/zwischen 10 und 2000 Zeichen/)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('blocks submit and shows a message when new_amount is <= 0', async () => {
    const onSubmit = vi.fn();
    render(<CostChangeForm onSubmit={onSubmit} />);

    await userEvent.type(screen.getByLabelText(/Neuer Betrag/), '0');
    await userEvent.type(
      screen.getByLabelText(/Begründung/),
      'Ausreichend lange Begründung für den Test.'
    );
    await userEvent.click(screen.getByRole('button', { name: 'Kostenänderung anlegen' }));

    expect(await screen.findByText(/größer als 0/)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('calls onSubmit with parsed numbers and a line-items array on a valid submit', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<CostChangeForm onSubmit={onSubmit} />);

    await userEvent.type(screen.getByLabelText(/Neuer Betrag/), '750.5');
    await userEvent.type(
      screen.getByLabelText(/Begründung/),
      'Zusätzlicher Steinbesatz wurde vom Kunden gewünscht.'
    );
    await userEvent.click(screen.getByRole('button', { name: '+ Position hinzufügen' }));
    await userEvent.type(screen.getByLabelText('Bezeichnung Position 1'), 'Saphir 0.5ct');
    await userEvent.type(screen.getByLabelText('Betrag Position 1'), '120');

    await userEvent.click(screen.getByRole('button', { name: 'Kostenänderung anlegen' }));

    expect(onSubmit).toHaveBeenCalledWith({
      new_amount: 750.5,
      reason: 'Zusätzlicher Steinbesatz wurde vom Kunden gewünscht.',
      line_items: [{ label: 'Saphir 0.5ct', amount: 120, kind: 'add' }],
    });
  });

  it('omits a blank optional line-item row from the submitted payload', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<CostChangeForm onSubmit={onSubmit} />);

    await userEvent.type(screen.getByLabelText(/Neuer Betrag/), '900');
    await userEvent.type(
      screen.getByLabelText(/Begründung/),
      'Kein Zusatzmaterial, nur Preisanpassung.'
    );
    // Add and then leave a row entirely blank.
    await userEvent.click(screen.getByRole('button', { name: '+ Position hinzufügen' }));

    await userEvent.click(screen.getByRole('button', { name: 'Kostenänderung anlegen' }));

    expect(onSubmit).toHaveBeenCalledWith({
      new_amount: 900,
      reason: 'Kein Zusatzmaterial, nur Preisanpassung.',
      line_items: [],
    });
  });

  it('disables all fields when disabled is true', () => {
    render(<CostChangeForm onSubmit={vi.fn()} disabled />);

    expect(screen.getByLabelText(/Neuer Betrag/)).toBeDisabled();
    expect(screen.getByLabelText(/Begründung/)).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Kostenänderung anlegen' })).toBeDisabled();
  });
});
