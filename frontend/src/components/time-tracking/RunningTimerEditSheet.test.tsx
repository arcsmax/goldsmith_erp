// RunningTimerEditSheet: opens from the TimerWidget, sends only the changed
// fields to PATCH /time-tracking/{id}, validates the start time in German,
// writes the saved entry into the running-timer cache.
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import type { RunningTimeEntry } from '../../api/time-tracking';
import { queryKeys } from '../../api/queryKeys';
import { renderWithQuery } from '../../test/queryWrapper';
import TimerWidget from '../TimerWidget';
import { RunningTimerEditSheet } from './RunningTimerEditSheet';
import { START_TIME_MESSAGES, buildEditPayload, draftFromEntry, splitNotes } from './runningTimerEdit';

const editRunning = vi.fn();
const jobsPage = vi.fn();
const getActiveLocations = vi.fn();

vi.mock('../../api/time-tracking', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/time-tracking')>();
  return {
    ...actual,
    timeTrackingApi: {
      ...actual.timeTrackingApi,
      editRunning: (...args: unknown[]) => editRunning(...args),
    },
  };
});

vi.mock('../../api/jobs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/jobs')>();
  return {
    ...actual,
    jobsApi: { ...actual.jobsApi, page: (...args: unknown[]) => jobsPage(...args) },
  };
});

vi.mock('../../api/locations', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/locations')>();
  return {
    ...actual,
    getActiveLocations: (...args: unknown[]) => getActiveLocations(...args),
  };
});

const THIRTY_MIN_MS = 30 * 60 * 1000;

function makeEntry(overrides: Partial<RunningTimeEntry> = {}): RunningTimeEntry {
  const start = new Date(Date.now() - THIRTY_MIN_MS).toISOString();
  return {
    id: 'entry-1',
    order_id: 12,
    user_id: 7,
    activity_id: 1,
    activity_name: 'Polieren',
    order_title: 'Ring weiten',
    start_time: start,
    end_time: null,
    duration_minutes: null,
    location: 'Werkbank 1',
    complexity_rating: null,
    quality_rating: null,
    rework_required: false,
    notes: 'Alte Notiz\n\n--- Änderungsprotokoll ---\n[01.09.2026 08:00] Benutzer #7: Ort',
    extra_metadata: null,
    is_paused: false,
    created_at: start,
    ...overrides,
  };
}

const renderSheet = (entry = makeEntry(), onClose = vi.fn()) =>
  renderWithQuery(<RunningTimerEditSheet entry={entry} onClose={onClose} />, { route: null });

beforeEach(() => {
  editRunning.mockReset();
  jobsPage.mockReset();
  getActiveLocations.mockReset();
  getActiveLocations.mockResolvedValue([
    { id: 5, name: 'Tresor', kind: 'other', is_active: true, sort_order: 10, created_at: '2026-09-01T08:00:00Z' },
    { id: 9, name: 'Werkbank 1', kind: 'bench', is_active: true, sort_order: 20, created_at: '2026-09-01T08:00:00Z' },
  ]);
  jobsPage.mockResolvedValue({
    items: [
      {
        id: 101,
        kind: 'order',
        number: 'AU-2026-0042',
        title: 'Kette kürzen',
        status: 'in_progress',
        status_label: 'In Arbeit',
        kind_status: 'in_progress',
        order_id: 42,
        repair_id: null,
        created_at: '2026-09-01T08:00:00Z',
        updated_at: '2026-09-01T08:00:00Z',
      },
    ],
    total: 1,
    limit: 10,
    offset: 0,
    next_offset: null,
  });
});

afterEach(() => vi.useRealTimers());

describe('runningTimerEdit helpers', () => {
  it('keeps the change log out of the editable notes', () => {
    expect(splitNotes(makeEntry().notes)).toEqual([
      'Alte Notiz',
      '[01.09.2026 08:00] Benutzer #7: Ort',
    ]);
    expect(draftFromEntry(makeEntry()).notes).toBe('Alte Notiz');
  });

  it('returns no payload when nothing changed', () => {
    const entry = makeEntry();
    expect(buildEditPayload(entry, draftFromEntry(entry))).toEqual({ payload: null });
  });

  it('rejects a start time in the future and a malformed one', () => {
    const entry = makeEntry({ start_time: '2026-09-25T08:00:00Z' });
    const now = new Date('2026-09-25T09:00:00Z');
    const draft = draftFromEntry(entry);
    const later = new Date(now.getTime() + 2 * 60 * 60 * 1000);
    const future = `${String(later.getHours()).padStart(2, '0')}:${String(later.getMinutes()).padStart(2, '0')}`;
    expect(buildEditPayload(entry, { ...draft, startTime: future }, now)).toEqual({
      error: START_TIME_MESSAGES.future,
    });
    expect(buildEditPayload(entry, { ...draft, startTime: '25:99' }, now)).toEqual({
      error: START_TIME_MESSAGES.invalid,
    });
  });
});

describe('RunningTimerEditSheet', () => {
  it('opens from the TimerWidget "Bearbeiten" button', async () => {
    const user = userEvent.setup();
    renderWithQuery(<TimerWidget runningEntry={makeEntry()} onStop={vi.fn()} />, { route: null });
    window.dispatchEvent(new Event('timer:expand'));

    expect(await screen.findByText('Auftrag #12 – Ring weiten · Polieren')).toBeInTheDocument();
    expect(screen.getByText('Ort: Werkbank 1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Bearbeiten' }));

    const dialog = await screen.findByRole('dialog', { name: 'Timer bearbeiten' });
    expect(within(dialog).getByLabelText(/Startzeit/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/Notiz/)).toHaveValue('Alte Notiz');
  });

  it('submits only the changed fields and updates the running-timer cache', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const saved = makeEntry({ activity_id: 3, activity_name: 'Löten', order_id: 42, notes: 'neu' });
    editRunning.mockResolvedValue(saved);
    const { client } = renderSheet(makeEntry(), onClose);

    await user.click(screen.getByRole('button', { name: 'Aktivität ändern' }));
    const loeten = await screen.findAllByRole('button', { name: /Löten/ });
    await user.click(loeten[0]);
    expect(screen.getByText('Löten')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Auftrag ändern' }));
    await user.click(await screen.findByRole('button', { name: 'AU-2026-0042 – Kette kürzen' }));

    const notes = screen.getByLabelText(/Notiz/);
    await user.clear(notes);
    await user.type(notes, 'neu');

    await user.click(screen.getByRole('button', { name: 'Änderungen speichern' }));

    await waitFor(() => expect(editRunning).toHaveBeenCalledTimes(1));
    expect(editRunning).toHaveBeenCalledWith('entry-1', { activity_id: 3, order_id: 42, notes: 'neu' });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(client.getQueryData(queryKeys.timer.running(7))).toEqual(saved);
    expect(jobsPage).toHaveBeenCalledWith(expect.objectContaining({ kind: 'order', limit: 10, offset: 0 }), expect.anything());
  });

  it('changes the Standort through the id-based picker and sends location_id', async () => {
    const user = userEvent.setup();
    const saved = makeEntry({ location: 'Tresor', location_id: 5 });
    editRunning.mockResolvedValue(saved);
    renderSheet(makeEntry({ location: 'Werkbank 1', location_id: 9 }));

    await user.click(screen.getByRole('button', { name: 'Ort ändern' }));
    const select = await screen.findByLabelText('Standort');
    await user.selectOptions(select, '5');

    await user.click(screen.getByRole('button', { name: 'Änderungen speichern' }));

    await waitFor(() => expect(editRunning).toHaveBeenCalledTimes(1));
    expect(editRunning).toHaveBeenCalledWith('entry-1', { location_id: 5 });
  });

  it('shows the German start-time error and does not submit', async () => {
    const user = userEvent.setup();
    renderSheet();
    const start = screen.getByLabelText(/Startzeit/);
    await user.clear(start);
    await user.click(screen.getByRole('button', { name: 'Änderungen speichern' }));

    expect(await screen.findByText(START_TIME_MESSAGES.invalid)).toBeInTheDocument();
    expect(start).toHaveAttribute('aria-invalid', 'true');
    expect(editRunning).not.toHaveBeenCalled();
  });

  it('shows the server message when the save is refused', async () => {
    const user = userEvent.setup();
    editRunning.mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 422,
        data: { detail: 'Die Startzeit darf nicht vor dem Ende der vorherigen Zeiterfassung (25.09.2026 08:00 Uhr) liegen.' },
      },
    });
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderSheet();
    const notes = screen.getByLabelText(/Notiz/);
    await user.type(notes, ' ergänzt');
    await user.click(screen.getByRole('button', { name: 'Änderungen speichern' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('vor dem Ende der vorherigen Zeiterfassung');
  });
});
