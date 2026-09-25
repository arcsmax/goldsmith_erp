import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { PromptDialog, usePromptDialog } from './PromptDialog';

describe('PromptDialog', () => {
  it('renders a labelled text field focused on open', async () => {
    render(
      <PromptDialog
        open
        title="Ablehnung begründen"
        label="Grund"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('dialog', { name: 'Ablehnung begründen' })).toBeInTheDocument();
    const input = screen.getByLabelText(/Grund/);
    await waitFor(() => expect(input).toHaveFocus());
  });

  it('submits the trimmed value with Enter', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <PromptDialog open title="T" label="Grund" onSubmit={onSubmit} onCancel={vi.fn()} />,
    );
    await user.type(screen.getByLabelText(/Grund/), '  Stein fehlt  {Enter}');
    expect(onSubmit).toHaveBeenCalledWith('Stein fehlt');
  });

  it('shows a German error and blocks submit when required and empty', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <PromptDialog
        open
        title="T"
        label="Grund"
        required
        confirmLabel="Ablehnung senden"
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />,
    );
    await user.click(screen.getByRole('button', { name: 'Ablehnung senden' }));
    expect(onSubmit).not.toHaveBeenCalled();
    const input = screen.getByLabelText(/Grund/);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription(/Grund fehlt/);
  });

  it('runs a custom validator', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <PromptDialog
        open
        title="T"
        label="Gewicht"
        inputMode="decimal"
        validate={(v) => (Number.isNaN(Number(v.replace(',', '.'))) ? 'Bitte eine Zahl eingeben.' : null)}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />,
    );
    const input = screen.getByLabelText(/Gewicht/);
    expect(input).toHaveAttribute('inputmode', 'decimal');
    await user.type(input, 'abc{Enter}');
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Bitte eine Zahl eingeben.')).toBeInTheDocument();
  });

  it('cancels on Escape', async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<PromptDialog open title="T" label="Grund" onSubmit={vi.fn()} onCancel={onCancel} />);
    await user.keyboard('{Escape}');
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

describe('usePromptDialog', () => {
  function Host({ onResult }: { onResult: (v: string | null) => void }) {
    const { prompt, dialog } = usePromptDialog();
    return (
      <>
        <button
          type="button"
          onClick={() => {
            void prompt({ title: 'Notiz', label: 'Text' }).then(onResult);
          }}
        >
          Fragen
        </button>
        {dialog}
      </>
    );
  }

  it('resolves with the value, or null on cancel', async () => {
    const onResult = vi.fn();
    const user = userEvent.setup();
    render(<Host onResult={onResult} />);
    await user.click(screen.getByRole('button', { name: 'Fragen' }));
    await user.type(screen.getByLabelText(/Text/), 'Hallo{Enter}');
    await waitFor(() => expect(onResult).toHaveBeenCalledWith('Hallo'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Fragen' }));
    await act(async () => {
      await user.keyboard('{Escape}');
    });
    await waitFor(() => expect(onResult).toHaveBeenLastCalledWith(null));
  });
});
