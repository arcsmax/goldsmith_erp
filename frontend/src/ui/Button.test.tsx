import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { Button, ButtonLink, IconButton } from './Button';
import { Card } from './Card';

describe('Button', () => {
  it('renders a native button with type="button" by default', () => {
    render(<Button>Auftrag speichern</Button>);
    const button = screen.getByRole('button', { name: 'Auftrag speichern' });
    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveClass('ui-button', 'ui-button--primary', 'ui-button--md');
  });

  it('applies variant and bench size classes', () => {
    render(
      <Button variant="danger" size="lg">
        Auftrag löschen
      </Button>,
    );
    const button = screen.getByRole('button', { name: 'Auftrag löschen' });
    expect(button).toHaveClass('ui-button--danger', 'ui-button--lg');
  });

  it('allows type="submit"', () => {
    render(<Button type="submit">Speichern</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'submit');
  });

  it('loading disables the button, sets aria-busy and blocks clicks', async () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Auftrag speichern
      </Button>,
    );
    const button = screen.getByRole('button', { name: /Auftrag speichern/ });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('marks the leading icon as decorative', () => {
    const { container } = render(<Button icon="plus">Neuer Auftrag</Button>);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
  });

  it('fires onClick when enabled', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Speichern</Button>);
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe('ButtonLink', () => {
  it('renders a link styled as a button', () => {
    render(
      <MemoryRouter>
        <ButtonLink to="/orders/new" variant="secondary">
          Neuer Auftrag
        </ButtonLink>
      </MemoryRouter>,
    );
    const link = screen.getByRole('link', { name: 'Neuer Auftrag' });
    expect(link).toHaveAttribute('href', '/orders/new');
    expect(link).toHaveClass('ui-button', 'ui-button--secondary');
  });
});

describe('IconButton', () => {
  it('uses label as aria-label and title', () => {
    render(<IconButton icon="close" label="Schließen" />);
    const button = screen.getByRole('button', { name: 'Schließen' });
    expect(button).toHaveAttribute('title', 'Schließen');
    expect(button).toHaveClass('ui-icon-button', 'ui-button--ghost');
  });

  it('fails a dev assertion when the label is missing', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const props = { icon: 'close' } as unknown as React.ComponentProps<typeof IconButton>;
    expect(() => render(<IconButton {...props} />)).toThrow(/aria-label/);
    const blank = { icon: 'close', label: '  ' } as React.ComponentProps<typeof IconButton>;
    expect(() => render(<IconButton {...blank} />)).toThrow(/aria-label/);
    spy.mockRestore();
  });
});

describe('Card', () => {
  it('renders a titled section labelled by its heading', () => {
    render(
      <Card title="Kunde" action={<a href="/customers/1">Öffnen</a>}>
        Inhalt
      </Card>,
    );
    const region = screen.getByRole('region', { name: 'Kunde' });
    expect(region).toHaveClass('ui-card');
    expect(screen.getByRole('link', { name: 'Öffnen' })).toBeInTheDocument();
  });

  it('applies the alert tone class', () => {
    const { container } = render(<Card tone="danger">x</Card>);
    expect(container.firstChild).toHaveClass('ui-card--danger');
  });
});
