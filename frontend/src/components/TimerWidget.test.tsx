// Tests for TimerWidget Component
//
// The widget renders a collapsed floating action button (FAB) by default and
// only shows the expanded controls after it is opened. Tests expand it via the
// 'timer:expand' window event the component listens for (see TimerWidget.tsx),
// which avoids depending on FAB-click timing.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TimerWidget from './TimerWidget';
import { TimeEntry } from '../types';

describe('TimerWidget', () => {
  const mockOnStop = vi.fn();
  const mockOnRefresh = vi.fn();

  const makeEntry = (overrides: Partial<TimeEntry> = {}): TimeEntry => ({
    id: 'test-entry-id',
    order_id: 123,
    user_id: 1,
    activity_id: 1,
    start_time: new Date(Date.now() - 1800000).toISOString(), // 30 min ago
    end_time: null,
    duration_minutes: null,
    location: 'workbench_1',
    complexity_rating: null,
    quality_rating: null,
    rework_required: false,
    notes: null,
    extra_metadata: null,
    created_at: new Date(Date.now() - 1800000).toISOString(),
    ...overrides,
  });

  const renderWidget = (entry: TimeEntry | null) =>
    render(
      <TimerWidget
        runningEntry={entry}
        onStop={mockOnStop}
        onRefresh={mockOnRefresh}
      />
    );

  // Expand the collapsed FAB into the full widget.
  const expand = () =>
    act(() => {
      window.dispatchEvent(new Event('timer:expand'));
    });

  beforeEach(() => {
    mockOnStop.mockClear();
    mockOnRefresh.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Collapsed FAB', () => {
    it('renders a start FAB when no entry is running', () => {
      renderWidget(null);

      const fab = screen.getByRole('button');
      expect(fab).toHaveClass('timer-fab');
      expect(fab).toHaveAttribute('title', 'Zeiterfassung starten');
    });

    it('renders an active FAB with elapsed time when an entry is running', () => {
      renderWidget(makeEntry());

      const fab = screen.getByRole('button');
      expect(fab).toHaveClass('timer-fab--active');
      expect(fab.textContent).toMatch(/\d+:\d{2}/); // shows running time
    });
  });

  describe('Expanded view', () => {
    it('shows the running label, order number and elapsed time', () => {
      renderWidget(makeEntry());
      expand();

      expect(screen.getByText('⏱️ Läuft')).toBeInTheDocument();

      const activity = screen.getByText(
        (_, el) => el?.classList.contains('timer-activity') ?? false
      );
      expect(activity).toHaveTextContent('Auftrag #123');

      expect(document.querySelector('.timer-time')?.textContent).toMatch(
        /\d+:\d{2}/
      );
    });

    it('collapses back to the FAB via the minimize button', async () => {
      const user = userEvent.setup();
      renderWidget(makeEntry());
      expand();

      await user.click(screen.getByTitle('Minimieren'));

      expect(screen.getByRole('button')).toHaveClass('timer-fab');
    });
  });

  describe('Pause / Resume', () => {
    it('toggles between running and paused state', async () => {
      const user = userEvent.setup();
      renderWidget(makeEntry());
      expand();

      expect(screen.getByText('⏱️ Läuft')).toBeInTheDocument();

      await user.click(screen.getByText('⏸️ Pause'));

      expect(screen.getByText('⏸️ Pausiert')).toBeInTheDocument();
      expect(screen.getByText('▶️ Fortsetzen')).toBeInTheDocument();

      await user.click(screen.getByText('▶️ Fortsetzen'));

      expect(screen.getByText('⏱️ Läuft')).toBeInTheDocument();
    });
  });

  describe('Stop dialog', () => {
    const openStopDialog = async (user: ReturnType<typeof userEvent.setup>) => {
      renderWidget(makeEntry());
      expand();
      await user.click(screen.getByText('⏹️ Stopp'));
    };

    it('opens with rating, rework and notes fields', async () => {
      const user = userEvent.setup();
      await openStopDialog(user);

      expect(screen.getByText('Zeiterfassung beenden')).toBeInTheDocument();
      expect(screen.getByText('Komplexität (1-5)')).toBeInTheDocument();
      expect(screen.getByText('Qualität (1-5)')).toBeInTheDocument();
      expect(screen.getByText('Nacharbeit erforderlich')).toBeInTheDocument();
      expect(screen.getByText('Notizen (optional)')).toBeInTheDocument();
      expect(
        screen.getByPlaceholderText('Zusätzliche Notizen...')
      ).toBeInTheDocument();
    });

    it('closes without stopping when cancel is clicked', async () => {
      const user = userEvent.setup();
      await openStopDialog(user);

      await user.click(screen.getByText('Abbrechen'));

      expect(
        screen.queryByText('Zeiterfassung beenden')
      ).not.toBeInTheDocument();
      expect(mockOnStop).not.toHaveBeenCalled();
    });

    it('stops the timer and notifies parent on confirm', async () => {
      const user = userEvent.setup();
      await openStopDialog(user);

      await user.click(screen.getByText('Stoppen & Speichern'));

      await waitFor(() => {
        expect(mockOnStop).toHaveBeenCalledTimes(1);
      });
      expect(mockOnRefresh).toHaveBeenCalled();
    });

    it('lets the user pick a complexity rating', async () => {
      const user = userEvent.setup();
      await openStopDialog(user);

      const field = screen
        .getByText('Komplexität (1-5)')
        .closest('.stop-dialog-field') as HTMLElement;
      const stars = within(field).getAllByText('★');
      expect(stars).toHaveLength(5);

      // Default complexity is 3 → 3 active stars; clicking the 5th selects 5.
      await user.click(stars[4]);
      await waitFor(() => {
        const active = within(field)
          .getAllByText('★')
          .filter((s) => s.classList.contains('active'));
        expect(active).toHaveLength(5);
      });
    });

    it('lets the user pick a quality rating', async () => {
      const user = userEvent.setup();
      await openStopDialog(user);

      const field = screen
        .getByText('Qualität (1-5)')
        .closest('.stop-dialog-field') as HTMLElement;
      const stars = within(field).getAllByText('★');
      expect(stars).toHaveLength(5);

      // Default quality is 4 → clicking the 2nd selects 2.
      await user.click(stars[1]);
      await waitFor(() => {
        const active = within(field)
          .getAllByText('★')
          .filter((s) => s.classList.contains('active'));
        expect(active).toHaveLength(2);
      });
    });

    it('toggles the rework-required checkbox', async () => {
      const user = userEvent.setup();
      await openStopDialog(user);

      const checkbox = screen.getByRole('checkbox');
      expect(checkbox).not.toBeChecked();
      await user.click(checkbox);
      expect(checkbox).toBeChecked();
    });

    it('accepts notes input', async () => {
      const user = userEvent.setup();
      await openStopDialog(user);

      const notes = screen.getByPlaceholderText('Zusätzliche Notizen...');
      await user.type(notes, 'Sauber poliert');
      expect(notes).toHaveValue('Sauber poliert');
    });
  });

  describe('Elapsed time', () => {
    it('updates the displayed time every second', () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2025-01-01T12:00:00Z'));

      // start 60 seconds before "now" → 1:00 elapsed
      renderWidget(makeEntry({ start_time: '2025-01-01T11:59:00Z' }));
      expand();

      expect(document.querySelector('.timer-time')?.textContent).toBe('1:00');

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      expect(document.querySelector('.timer-time')?.textContent).toBe('1:01');
    });
  });
});
