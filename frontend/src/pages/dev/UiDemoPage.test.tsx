import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { UiDemoPage } from './UiDemoPage';

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <UiDemoPage />
    </MemoryRouter>,
  );
}

describe('UiDemoPage (/dev/ui)', () => {
  it('renders every primitive section', () => {
    renderAt('/dev/ui');
    expect(screen.getByRole('heading', { level: 1, name: 'UI-Bausteine' })).toBeInTheDocument();
    for (const name of [
      'Button, IconButton, ButtonLink',
      'Card',
      'Modal, Dialog, Sheet, PromptDialog',
      'Field',
      'DataTable, ListCard',
      'EmptyState, PageState',
      'PageHeader, Tabs, TabBar',
      'DeadlineChip',
    ]) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument();
    }
  });

  it.each([
    ['modal', 'dialog', 'Auftrag bearbeiten'],
    ['dialog', 'alertdialog', 'Auftrag löschen?'],
    ['sheet', 'dialog', '#1042 Trauringe Gelbgold 585'],
    ['prompt', 'dialog', 'Kostenänderung ablehnen'],
  ] as const)('opens the %s overlay from ?open=', (open, role, name) => {
    renderAt(`/dev/ui?open=${open}`);
    expect(screen.getByRole(role, { name })).toBeInTheDocument();
  });

  it('selects the tab from ?tab=', () => {
    renderAt('/dev/ui?tab=time');
    expect(screen.getByRole('tab', { name: 'Zeit' })).toHaveAttribute('aria-selected', 'true');
  });
});
