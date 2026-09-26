import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Field } from './Field';

describe('Field', () => {
  it('binds a visible label to the input', () => {
    render(
      <Field label="Titel" name="title">
        <input />
      </Field>,
    );
    const input = screen.getByLabelText('Titel');
    expect(input).toHaveAttribute('name', 'title');
    expect(input).toHaveClass('ui-field__control');
  });

  it('marks required fields in text and with aria-required', () => {
    render(
      <Field label="Kunde" name="customer" required>
        <input />
      </Field>,
    );
    const input = screen.getByLabelText(/Kunde/);
    expect(input).toHaveAttribute('aria-required', 'true');
    expect(input).toBeRequired();
    expect(screen.getByText('Pflichtfeld')).toBeInTheDocument();
  });

  it('links help text via aria-describedby', () => {
    render(
      <Field label="Gewicht" name="weight" help="In Gramm, Komma erlaubt.">
        <input />
      </Field>,
    );
    expect(screen.getByLabelText('Gewicht')).toHaveAccessibleDescription('In Gramm, Komma erlaubt.');
  });

  it('marks errors with aria-invalid and describes them', () => {
    render(
      <Field
        label="Gewicht"
        name="weight"
        help="In Gramm."
        error="Gewicht fehlt. Bitte in Gramm eingeben."
      >
        <input />
      </Field>,
    );
    const input = screen.getByLabelText('Gewicht');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription(/Gewicht fehlt\. Bitte in Gramm eingeben\./);
    expect(input).toHaveAccessibleDescription(/In Gramm\./);
  });

  it('forwards inputMode and shows a unit suffix', () => {
    render(
      <Field label="Preis" name="price" inputMode="decimal" suffix="€">
        <input />
      </Field>,
    );
    expect(screen.getByLabelText('Preis')).toHaveAttribute('inputmode', 'decimal');
    expect(screen.getByText('€')).toHaveAttribute('aria-hidden', 'true');
  });

  it('wraps a select and a textarea', () => {
    render(
      <>
        <Field label="Status" name="status">
          <select>
            <option>Neu</option>
          </select>
        </Field>
        <Field label="Notiz" name="note">
          <textarea />
        </Field>
      </>,
    );
    expect(screen.getByLabelText('Status').tagName).toBe('SELECT');
    expect(screen.getByLabelText('Notiz').tagName).toBe('TEXTAREA');
  });

  it('keeps an id the child already has', () => {
    render(
      <Field label="E-Mail" name="email">
        <input id="customer-email" type="email" />
      </Field>,
    );
    expect(screen.getByLabelText('E-Mail')).toHaveAttribute('id', 'customer-email');
  });
});
