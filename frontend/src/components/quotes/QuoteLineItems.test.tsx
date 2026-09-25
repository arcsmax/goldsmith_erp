// W4-03: field-array behaviour of the react-hook-form line-item editor.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EditableLineItems } from './QuoteLineItems';
import type { QuoteLineItem } from '../../types';

function makeItem(overrides: Partial<QuoteLineItem> = {}): QuoteLineItem {
  return {
    id: 1,
    quote_id: 10,
    line_type: 'labor',
    description: 'Handarbeit',
    quantity: 2,
    unit_price: 50,
    total: 100,
    ...overrides,
  };
}

describe('EditableLineItems field array (W4-03)', () => {
  const onAdd = vi.fn().mockResolvedValue(undefined);
  const onSave = vi.fn().mockResolvedValue(undefined);
  const onRemove = vi.fn().mockResolvedValue(undefined);
  const props = { disabled: false, onAdd, onSave, onRemove };

  beforeEach(() => vi.clearAllMocks());

  it('keeps each row bound to its line item when an earlier row disappears', async () => {
    const first = makeItem({ id: 1, description: 'Gravur' });
    const second = makeItem({ id: 2, description: 'Politur' });
    const user = userEvent.setup();
    const { rerender } = render(<EditableLineItems items={[first, second]} {...props} />);

    // The server removed the first position; the remaining row is "Politur" (id 2).
    rerender(<EditableLineItems items={[second]} {...props} />);
    expect(screen.queryByDisplayValue('Gravur')).not.toBeInTheDocument();

    const input = screen.getByDisplayValue('Politur');
    await user.clear(input);
    await user.type(input, 'Hochglanzpolitur');
    await user.tab();

    expect(onSave).toHaveBeenCalledWith(2, expect.objectContaining({ description: 'Hochglanzpolitur' }));
  });

  it('shows the server value after a save changed it', () => {
    const { rerender } = render(<EditableLineItems items={[makeItem({ quantity: 2 })]} {...props} />);
    rerender(<EditableLineItems items={[makeItem({ quantity: 3, total: 150 })]} {...props} />);
    expect((screen.getByLabelText('Menge') as HTMLInputElement).value).toBe('3');
  });

  it('adds a row for every new server line item', () => {
    const { rerender } = render(<EditableLineItems items={[makeItem()]} {...props} />);
    rerender(
      <EditableLineItems
        items={[makeItem(), makeItem({ id: 2, description: 'Stein fassen' })]}
        {...props}
      />,
    );
    expect(screen.getAllByLabelText('Beschreibung')).toHaveLength(2);
    expect(screen.getByDisplayValue('Stein fassen')).toBeInTheDocument();
  });

  it('explains an empty description instead of saving it', async () => {
    const user = userEvent.setup();
    render(<EditableLineItems items={[makeItem({ id: 4 })]} {...props} />);
    await user.clear(screen.getByDisplayValue('Handarbeit'));
    await user.tab();

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText('Beschreibung fehlt. Bitte die Position benennen.')).toBeInTheDocument();
    expect(screen.getByLabelText('Beschreibung')).toHaveAttribute('aria-invalid', 'true');
  });

  it('saves the type select on change with the other row values', async () => {
    const user = userEvent.setup();
    render(<EditableLineItems items={[makeItem({ id: 6 })]} {...props} />);
    await user.selectOptions(screen.getByLabelText('Art der Position'), 'material');
    expect(onSave).toHaveBeenCalledWith(6, {
      line_type: 'material',
      description: 'Handarbeit',
      quantity: 2,
      unit_price: 50,
    });
  });

  it('clears the add row after a successful add', async () => {
    const user = userEvent.setup();
    render(<EditableLineItems items={[]} {...props} />);
    const description = screen.getByPlaceholderText('Neue Position…');
    await user.type(description, 'Kette kürzen');
    await user.click(screen.getByRole('button', { name: 'Hinzufügen' }));

    expect(onAdd).toHaveBeenCalledWith({
      line_type: 'labor',
      description: 'Kette kürzen',
      quantity: 1,
      unit_price: 0,
    });
    expect(await screen.findByPlaceholderText('Neue Position…')).toHaveValue('');
  });
});
