// Tests for TimerWidget Component
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TimerWidget from './TimerWidget';
import { TimeEntry } from '../types';

describe('TimerWidget', () => {
  const mockOnStop = vi.fn();
  const mockOnRefresh = vi.fn();

  const mockRunningEntry: TimeEntry = {
    id: 'test-entry-id',
    order_id: 123,
    user_id: 1,
    activity_id: 1,
    start_time: new Date(Date.now() - 1800000).toISOString(), // 30 minutes ago
    end_time: null,
    duration_minutes: null,
    location: 'workbench_1',
    complexity_rating: null,
    quality_rating: null,
    rework_required: false,
    notes: null,
    extra_metadata: null,
    created_at: new Date(Date.now() - 1800000).toISOString(),
  };

  beforeEach(() => {
    mockOnStop.mockClear();
    mockOnRefresh.mockClear();
  });

  describe('Visibility', () => {
    it('should not render when no entry is running', () => {
      const { container } = render(
        <TimerWidget
          runningEntry={null}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      expect(container.firstChild).toBeNull();
    });

    it('should render when entry is running', () => {
      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      expect(screen.getByText(/Auftrag #123/)).toBeInTheDocument();
    });
  });

  describe('Timer Display', () => {
    it('should show elapsed time', () => {
      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      // Should show time in format "00:30:XX" (30 minutes)
      expect(screen.getByText(/00:3/)).toBeInTheDocument();
    });

    it('should update elapsed time every second', async () => {
      vi.useFakeTimers();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const initialTime = screen.getByText(/00:3/).textContent;

      // Advance time by 2 seconds
      vi.advanceTimersByTime(2000);

      await waitFor(() => {
        const newTime = screen.getByText(/00:3/).textContent;
        expect(newTime).not.toBe(initialTime);
      });

      vi.useRealTimers();
    });

    it('should show order number', () => {
      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      expect(screen.getByText('Auftrag #123')).toBeInTheDocument();
    });

    it('should show location when available', () => {
      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      expect(screen.getByText('📍 workbench_1')).toBeInTheDocument();
    });

    it('should not show location when not available', () => {
      const entryWithoutLocation = { ...mockRunningEntry, location: null };

      render(
        <TimerWidget
          runningEntry={entryWithoutLocation}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      expect(screen.queryByText(/📍/)).not.toBeInTheDocument();
    });
  });

  describe('Pause/Resume Functionality', () => {
    it('should show pause button when timer is running', () => {
      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      expect(screen.getByTitle('Pausieren')).toBeInTheDocument();
    });

    it('should pause timer when pause button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const pauseButton = screen.getByTitle('Pausieren');
      await user.click(pauseButton);

      // Should show resume button after pause
      expect(screen.getByTitle('Fortsetzen')).toBeInTheDocument();
    });

    it('should show pause badge when paused', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const pauseButton = screen.getByTitle('Pausieren');
      await user.click(pauseButton);

      expect(screen.getByText('Pausiert')).toBeInTheDocument();
    });

    it('should resume timer when resume button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      // Pause first
      const pauseButton = screen.getByTitle('Pausieren');
      await user.click(pauseButton);

      // Then resume
      const resumeButton = screen.getByTitle('Fortsetzen');
      await user.click(resumeButton);

      // Should show pause button again
      expect(screen.getByTitle('Pausieren')).toBeInTheDocument();
      expect(screen.queryByText('Pausiert')).not.toBeInTheDocument();
    });
  });

  describe('Stop Dialog', () => {
    it('should open stop dialog when stop button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const stopButton = screen.getByText('Stoppen');
      await user.click(stopButton);

      expect(screen.getByText('Zeiterfassung beenden')).toBeInTheDocument();
    });

    it('should show complexity rating field in stop dialog', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const stopButton = screen.getByText('Stoppen');
      await user.click(stopButton);

      expect(screen.getByText('Komplexität:')).toBeInTheDocument();
    });

    it('should show quality rating field in stop dialog', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const stopButton = screen.getByText('Stoppen');
      await user.click(stopButton);

      expect(screen.getByText('Qualität:')).toBeInTheDocument();
    });

    it('should show rework required checkbox', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const stopButton = screen.getByText('Stoppen');
      await user.click(stopButton);

      expect(screen.getByText('Nacharbeit erforderlich')).toBeInTheDocument();
    });

    it('should show notes textarea', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const stopButton = screen.getByText('Stoppen');
      await user.click(stopButton);

      expect(screen.getByPlaceholderText('Notizen (optional)...')).toBeInTheDocument();
    });

    it('should close stop dialog when cancel is clicked', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const stopButton = screen.getByText('Stoppen');
      await user.click(stopButton);

      const cancelButton = screen.getByText('Abbrechen');
      await user.click(cancelButton);

      expect(screen.queryByText('Zeiterfassung beenden')).not.toBeInTheDocument();
    });

    it('should not call onStop when cancel is clicked', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const stopButton = screen.getByText('Stoppen');
      await user.click(stopButton);

      const cancelButton = screen.getByText('Abbrechen');
      await user.click(cancelButton);

      expect(mockOnStop).not.toHaveBeenCalled();
    });
  });

  describe('Star Rating', () => {
    it('should allow selecting complexity rating', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const stopButton = screen.getByText('Stoppen');
      await user.click(stopButton);

      // Find complexity rating stars
      const complexitySection = screen.getByText('Komplexität:').closest('.rating-field');
      const stars = within(complexitySection!).getAllByText('★');

      // Click 5th star
      await user.click(stars[4]);

      // All 5 stars should be active
      expect(stars[0].classList.contains('active')).toBe(true);
      expect(stars[4].classList.contains('active')).toBe(true);
    });

    it('should allow selecting quality rating', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const stopButton = screen.getByText('Stoppen');
      await user.click(stopButton);

      // Find quality rating stars
      const qualitySection = screen.getByText('Qualität:').closest('.rating-field');
      const stars = within(qualitySection!).getAllByText('★');

      // Click 3rd star
      await user.click(stars[2]);

      // First 3 stars should be active
      expect(stars[0].classList.contains('active')).toBe(true);
      expect(stars[2].classList.contains('active')).toBe(true);
      expect(stars[3].classList.contains('active')).toBe(false);
    });
  });

  describe('Refresh Functionality', () => {
    it('should show refresh button', () => {
      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      expect(screen.getByTitle('Aktualisieren')).toBeInTheDocument();
    });

    it('should call onRefresh when refresh button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const refreshButton = screen.getByTitle('Aktualisieren');
      await user.click(refreshButton);

      expect(mockOnRefresh).toHaveBeenCalledTimes(1);
    });
  });

  describe('Expand/Collapse', () => {
    it('should start in expanded state', () => {
      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      expect(screen.getByText('Stoppen')).toBeInTheDocument();
    });

    it('should show minimize button in expanded state', () => {
      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      expect(screen.getByTitle('Minimieren')).toBeInTheDocument();
    });

    it('should collapse when minimize button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const minimizeButton = screen.getByTitle('Minimieren');
      await user.click(minimizeButton);

      // Should hide action buttons in collapsed state
      expect(screen.queryByText('Stoppen')).not.toBeInTheDocument();
    });

    it('should expand when expand button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      // Collapse first
      const minimizeButton = screen.getByTitle('Minimieren');
      await user.click(minimizeButton);

      // Then expand
      const expandButton = screen.getByTitle('Erweitern');
      await user.click(expandButton);

      // Should show action buttons again
      expect(screen.getByText('Stoppen')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should have accessible buttons', () => {
      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });

    it('should have title attributes for icon buttons', () => {
      render(
        <TimerWidget
          runningEntry={mockRunningEntry}
          onStop={mockOnStop}
          onRefresh={mockOnRefresh}
        />
      );

      expect(screen.getByTitle('Pausieren')).toBeInTheDocument();
      expect(screen.getByTitle('Aktualisieren')).toBeInTheDocument();
      expect(screen.getByTitle('Minimieren')).toBeInTheDocument();
    });
  });
});
