// Unit tests for the editable quote line-items table (editable-quotes feature).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { EditableLineItems } from './QuotesPage';
import type { QuoteLineItem } from '../types';

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

describe('EditableLineItems', () => {
  const onAdd = vi.fn().mockResolvedValue(undefined);
  const onSave = vi.fn().mockResolvedValue(undefined);
  const onRemove = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders each existing line item as editable inputs', () => {
    render(
      <EditableLineItems
        items={[makeItem(), makeItem({ id: 2, description: 'Material', total: 30 })]}
        disabled={false}
        onAdd={onAdd}
        onSave={onSave}
        onRemove={onRemove}
      />
    );
    expect(screen.getByDisplayValue('Handarbeit')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Material')).toBeInTheDocument();
    // Add-row present.
    expect(screen.getByPlaceholderText('Neue Position…')).toBeInTheDocument();
  });

  it('adding a new position calls onAdd with the drafted item', async () => {
    const user = userEvent.setup();
    render(
      <EditableLineItems
        items={[]}
        disabled={false}
        onAdd={onAdd}
        onSave={onSave}
        onRemove={onRemove}
      />
    );
    await user.type(screen.getByPlaceholderText('Neue Position…'), 'Gravur');
    await user.click(screen.getByRole('button', { name: 'Hinzufügen' }));
    expect(onAdd).toHaveBeenCalledTimes(1);
    expect(onAdd).toHaveBeenCalledWith(
      expect.objectContaining({ description: 'Gravur', quantity: 1 })
    );
  });

  it('does not add an empty position', async () => {
    const user = userEvent.setup();
    render(
      <EditableLineItems
        items={[]}
        disabled={false}
        onAdd={onAdd}
        onSave={onSave}
        onRemove={onRemove}
      />
    );
    // Button is disabled while description is blank.
    expect(screen.getByRole('button', { name: 'Hinzufügen' })).toBeDisabled();
    expect(onAdd).not.toHaveBeenCalled();
  });

  it('removing a row calls onRemove with the item id', async () => {
    const user = userEvent.setup();
    render(
      <EditableLineItems
        items={[makeItem({ id: 7 })]}
        disabled={false}
        onAdd={onAdd}
        onSave={onSave}
        onRemove={onRemove}
      />
    );
    await user.click(screen.getByRole('button', { name: /entfernen/ }));
    expect(onRemove).toHaveBeenCalledWith(7);
  });

  it('does not persist an invalid (cleared) quantity to the API', async () => {
    const user = userEvent.setup();
    render(
      <EditableLineItems
        items={[makeItem({ id: 5 })]}
        disabled={false}
        onAdd={onAdd}
        onSave={onSave}
        onRemove={onRemove}
      />
    );
    const qty = screen.getByLabelText('Menge');
    await user.clear(qty); // empty → NaN
    await user.tab(); // blur
    expect(onSave).not.toHaveBeenCalled();
  });

  it('editing a description and blurring calls onSave with the full item', async () => {
    const user = userEvent.setup();
    render(
      <EditableLineItems
        items={[makeItem({ id: 3, description: 'Alt' })]}
        disabled={false}
        onAdd={onAdd}
        onSave={onSave}
        onRemove={onRemove}
      />
    );
    const input = screen.getByDisplayValue('Alt');
    await user.clear(input);
    await user.type(input, 'Neu');
    await user.tab(); // blur
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith(3, expect.objectContaining({ description: 'Neu' }));
  });

  it('disables all controls when disabled', () => {
    render(
      <EditableLineItems
        items={[makeItem()]}
        disabled={true}
        onAdd={onAdd}
        onSave={onSave}
        onRemove={onRemove}
      />
    );
    expect(screen.getByDisplayValue('Handarbeit')).toBeDisabled();
    expect(screen.getByPlaceholderText('Neue Position…')).toBeDisabled();
  });
});
