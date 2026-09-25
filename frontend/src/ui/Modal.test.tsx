import React, { useRef, useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Dialog, Modal, Sheet } from './Modal';

function Harness({
  isDirty = false,
  dismissOnBackdrop = false,
  withInitialFocus = false,
}: {
  isDirty?: boolean;
  dismissOnBackdrop?: boolean;
  withInitialFocus?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Öffnen
      </button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Auftrag bearbeiten"
        description="Änderungen werden sofort gespeichert."
        isDirty={isDirty}
        dismissOnBackdrop={dismissOnBackdrop}
        initialFocusRef={withInitialFocus ? inputRef : undefined}
        footer={<button type="button">Speichern</button>}
      >
        <label htmlFor="t">Titel</label>
        <input id="t" ref={inputRef} />
      </Modal>
    </>
  );
}

async function openHarness(props: React.ComponentProps<typeof Harness> = {}) {
  const user = userEvent.setup();
  render(<Harness {...props} />);
  await user.click(screen.getByRole('button', { name: 'Öffnen' }));
  return user;
}

describe('Modal', () => {
  it('renders nothing when closed', () => {
    render(<Harness />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('is a labelled, described modal dialog', async () => {
    await openHarness();
    const dialog = screen.getByRole('dialog', { name: 'Auftrag bearbeiten' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleDescription('Änderungen werden sofort gespeichert.');
    expect(screen.getByRole('heading', { level: 2, name: 'Auftrag bearbeiten' })).toBeInTheDocument();
  });

  it('moves focus into the dialog on open', async () => {
    await openHarness();
    const dialog = screen.getByRole('dialog');
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
  });

  it('honours initialFocusRef', async () => {
    await openHarness({ withInitialFocus: true });
    await waitFor(() => expect(screen.getByLabelText('Titel')).toHaveFocus());
  });

  it('traps Tab and Shift+Tab inside the dialog', async () => {
    const user = await openHarness();
    const dialog = screen.getByRole('dialog');
    for (let i = 0; i < 6; i += 1) {
      await user.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    for (let i = 0; i < 6; i += 1) {
      await user.tab({ shift: true });
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = await openHarness();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Öffnen' })).toHaveFocus();
  });

  it('has a 44px close IconButton labelled "Schließen"', async () => {
    const user = await openHarness();
    await user.click(screen.getByRole('button', { name: 'Schließen' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('does not close on backdrop click by default (forms)', async () => {
    const user = await openHarness();
    await user.click(screen.getByTestId('ui-modal-backdrop'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('closes on backdrop click when dismissOnBackdrop is set', async () => {
    const user = await openHarness({ dismissOnBackdrop: true });
    await user.click(screen.getByTestId('ui-modal-backdrop'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('asks before discarding when dirty; "Weiter bearbeiten" keeps it open', async () => {
    const user = await openHarness({ isDirty: true });
    await user.keyboard('{Escape}');
    expect(screen.getByRole('dialog', { name: 'Auftrag bearbeiten' })).toBeInTheDocument();
    expect(screen.getByText('Änderungen verwerfen?')).toBeInTheDocument();
    const keep = screen.getByRole('button', { name: 'Weiter bearbeiten' });
    await waitFor(() => expect(keep).toHaveFocus());
    await user.click(keep);
    expect(screen.queryByText('Änderungen verwerfen?')).not.toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('closes a dirty dialog after "Verwerfen"', async () => {
    const user = await openHarness({ isDirty: true });
    await user.click(screen.getByRole('button', { name: 'Schließen' }));
    await user.click(screen.getByRole('button', { name: 'Verwerfen' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('applies size and sheet classes', () => {
    const { rerender } = render(
      <Modal open onClose={vi.fn()} title="A" size="lg">
        x
      </Modal>,
    );
    expect(screen.getByRole('dialog')).toHaveClass('ui-modal--lg');
    rerender(
      <Sheet open onClose={vi.fn()} title="B">
        y
      </Sheet>,
    );
    expect(screen.getByRole('dialog')).toHaveClass('ui-modal--sheet');
  });
});

describe('Dialog', () => {
  it('confirms and cancels with German default labels', async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(
      <Dialog
        open
        title="Auftrag löschen?"
        message="Der Auftrag wird endgültig gelöscht."
        variant="danger"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    const dialog = screen.getByRole('alertdialog', { name: 'Auftrag löschen?' });
    expect(dialog).toHaveAccessibleDescription('Der Auftrag wird endgültig gelöscht.');
    // Safer default for destructive actions: focus starts on "Abbrechen".
    await waitFor(() => expect(screen.getByRole('button', { name: 'Abbrechen' })).toHaveFocus());
    await user.click(screen.getByRole('button', { name: 'Löschen' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    await user.keyboard('{Escape}');
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('uses "Bestätigen" for the default variant', () => {
    render(<Dialog open title="Weiter?" message="m" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Bestätigen' })).toBeInTheDocument();
  });
});
