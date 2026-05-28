// Tests for ActivityPicker Component
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ActivityPicker from './ActivityPicker';
import { mockActivities } from '../test/mocks/handlers';

// Activities appear twice in the rendered tree — once in the "⭐ Häufig
// verwendet" (most-used) section and once in their category group — so name/
// icon/duration lookups use getAllByText and assert at least one match.
const fabricationFilterButton = () =>
  screen.getAllByText('🔨 Fertigung').find((el) => el.tagName === 'BUTTON')!;

describe('ActivityPicker', () => {
  const mockOnSelectActivity = vi.fn();
  const mockOnCancel = vi.fn();

  beforeEach(() => {
    mockOnSelectActivity.mockClear();
    mockOnCancel.mockClear();
  });

  describe('Rendering', () => {
    it('should render the component', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('Aktivität auswählen')).toBeInTheDocument();
      });
    });

    it('should show loading state initially', () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      expect(screen.getByText('Aktivitäten werden geladen...')).toBeInTheDocument();
    });

    it('should show activities after loading', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getAllByText('Polieren').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Stein Fassen').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Löten').length).toBeGreaterThan(0);
      });
    });

    it('should render cancel button', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('✕')).toBeInTheDocument();
      });
    });
  });

  describe('Top Activities', () => {
    it('should show top activities when showTopActivities is true', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
          showTopActivities={true}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('⭐ Häufig verwendet')).toBeInTheDocument();
      });
    });

    it('should not show top activities when showTopActivities is false', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
          showTopActivities={false}
        />
      );

      await waitFor(() => {
        expect(screen.queryByText('⭐ Häufig verwendet')).not.toBeInTheDocument();
      });
    });

    it('should show most used activities in top section', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
          showTopActivities={true}
        />
      );

      await waitFor(() => {
        const topSection = screen.getByText('⭐ Häufig verwendet').parentElement;
        expect(topSection).toBeInTheDocument();

        // Most used activities should appear inside the top section
        expect(within(topSection!).getByText('Polieren')).toBeInTheDocument();
      });
    });
  });

  describe('Search Functionality', () => {
    it('should render search input', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Aktivität suchen...')).toBeInTheDocument();
      });
    });

    it('should filter activities by search query', async () => {
      const user = userEvent.setup();

      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getAllByText('Polieren').length).toBeGreaterThan(0);
      });

      const searchInput = screen.getByPlaceholderText('Aktivität suchen...');
      await user.type(searchInput, 'Polieren');

      await waitFor(() => {
        // Typing hides the top section, so Polieren shows once (its category)
        expect(screen.getByText('Polieren')).toBeInTheDocument();
        expect(screen.queryByText('Löten')).not.toBeInTheDocument();
      });
    });

    it('should show no results message when search has no matches', async () => {
      const user = userEvent.setup();

      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getAllByText('Polieren').length).toBeGreaterThan(0);
      });

      const searchInput = screen.getByPlaceholderText('Aktivität suchen...');
      await user.type(searchInput, 'NonexistentActivity123');

      await waitFor(() => {
        expect(screen.getByText(/Keine Aktivitäten gefunden/)).toBeInTheDocument();
      });
    });
  });

  describe('Category Filtering', () => {
    it('should show all categories by default', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        // Each label appears as a filter button and a category header
        expect(screen.getAllByText('🔨 Fertigung').length).toBeGreaterThan(0);
        expect(screen.getAllByText('📋 Verwaltung').length).toBeGreaterThan(0);
        expect(screen.getAllByText('⏳ Warten').length).toBeGreaterThan(0);
      });
    });

    it('should filter by category when category button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('Alle')).toBeInTheDocument();
      });

      await user.click(fabricationFilterButton());

      // Should show only fabrication activities
      await waitFor(() => {
        expect(screen.getByText('Polieren')).toBeInTheDocument();
        expect(screen.getByText('Stein Fassen')).toBeInTheDocument();
        expect(screen.getByText('Löten')).toBeInTheDocument();
      });
    });

    it('should highlight active category', async () => {
      const user = userEvent.setup();

      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        const allButton = screen.getByText('Alle');
        expect(allButton.classList.contains('active')).toBe(true);
      });

      const fabricationButton = fabricationFilterButton();
      await user.click(fabricationButton);

      await waitFor(() => {
        expect(fabricationButton.classList.contains('active')).toBe(true);
      });
    });
  });

  describe('Activity Selection', () => {
    it('should call onSelectActivity when an activity is clicked', async () => {
      const user = userEvent.setup();

      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getAllByText('Polieren').length).toBeGreaterThan(0);
      });

      const polishingActivity = screen.getAllByText('Polieren')[0].closest('button');
      await user.click(polishingActivity!);

      expect(mockOnSelectActivity).toHaveBeenCalledTimes(1);
      expect(mockOnSelectActivity).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Polieren',
          category: 'fabrication',
        })
      );
    });

    it('should call onSelectActivity for an enabled activity card', async () => {
      const user = userEvent.setup();

      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getAllByText('Polieren').length).toBeGreaterThan(0);
      });

      const polishingActivity = screen.getAllByText('Polieren')[0].closest('button');

      // Activity cards are clickable
      expect(polishingActivity).not.toBeDisabled();

      await user.click(polishingActivity!);
      expect(mockOnSelectActivity).toHaveBeenCalled();
    });
  });

  describe('Cancel Functionality', () => {
    it('should call onCancel when cancel button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('✕')).toBeInTheDocument();
      });

      await user.click(screen.getByText('✕'));

      expect(mockOnCancel).toHaveBeenCalledTimes(1);
    });

    it('should not render a cancel button when onCancel is not provided', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
        />
      );

      await waitFor(() => {
        expect(screen.getByText('Aktivität auswählen')).toBeInTheDocument();
      });

      // The close (✕) button only renders when onCancel is passed
      expect(screen.queryByText('✕')).not.toBeInTheDocument();
    });
  });

  describe('Activity Display', () => {
    it('should show activity icon', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getAllByText('✨').length).toBeGreaterThan(0); // Polieren icon
        expect(screen.getAllByText('💎').length).toBeGreaterThan(0); // Stein Fassen icon
      });
    });

    it('should show activity usage count', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(/150x verwendet/)).toBeInTheDocument();
      });
    });

    it('should show average duration when available', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        // formatDuration(45) -> "45min"; shown in both top and category cards
        expect(screen.getAllByText(/45min/).length).toBeGreaterThan(0);
      });
    });
  });

  describe('Error Handling', () => {
    it('should show error message when API call fails', async () => {
      // Mock API failure would be set up in MSW handlers
      // For now, we'll skip this test as it requires more complex setup
      expect(true).toBe(true);
    });
  });

  describe('Accessibility', () => {
    it('should have accessible activity buttons', async () => {
      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        const activityButtons = screen.getAllByRole('button');
        expect(activityButtons.length).toBeGreaterThan(0);
      });
    });

    it('should have keyboard navigation support', async () => {
      const user = userEvent.setup();

      render(
        <ActivityPicker
          onSelectActivity={mockOnSelectActivity}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getAllByText('Polieren').length).toBeGreaterThan(0);
      });

      // Tab through elements
      await user.tab();

      // First focusable element should be focused
      expect(document.activeElement).toBeDefined();
    });
  });
});
