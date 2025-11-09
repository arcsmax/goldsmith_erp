# Frontend Testing Guide

This document describes the testing setup and how to run tests for the Goldsmith ERP frontend.

## Testing Stack

- **Test Runner**: [Vitest](https://vitest.dev/) - Fast, Vite-native unit test framework
- **React Testing**: [@testing-library/react](https://testing-library.com/react) - React component testing utilities
- **User Interactions**: [@testing-library/user-event](https://testing-library.com/docs/user-event/intro) - Realistic user interaction simulation
- **API Mocking**: [MSW (Mock Service Worker)](https://mswjs.io/) - API mocking at the network level
- **DOM Environment**: [happy-dom](https://github.com/capricorn86/happy-dom) - Fast DOM implementation for testing

## Installation

Before running tests, install the dependencies:

```bash
cd frontend
yarn install
```

This will install all testing dependencies specified in `package.json`.

## Running Tests

### Run all tests
```bash
yarn test
```

### Run tests in watch mode (auto-rerun on file changes)
```bash
yarn test --watch
```

### Run tests with UI (interactive test explorer)
```bash
yarn test:ui
```

### Run tests with coverage report
```bash
yarn test:coverage
```

Coverage reports will be generated in:
- Terminal output (text format)
- `coverage/` directory (HTML format - open `coverage/index.html` in browser)

### Run specific test file
```bash
yarn test ActivityPicker.test.tsx
```

### Run tests matching a pattern
```bash
yarn test --grep "ActivityPicker"
```

## Test Structure

### Directory Structure
```
frontend/src/
├── api/
│   ├── timeTracking.ts
│   ├── timeTracking.test.ts       # API client tests
│   ├── activities.ts
│   └── activities.test.ts         # API client tests
├── components/
│   ├── ActivityPicker.tsx
│   ├── ActivityPicker.test.tsx    # Component tests
│   ├── TimerWidget.tsx
│   └── TimerWidget.test.tsx       # Component tests
└── test/
    ├── setup.ts                   # Global test setup
    └── mocks/
        ├── server.ts              # MSW server setup
        └── handlers.ts            # API request handlers
```

### Test Types

1. **API Client Tests** (`src/api/*.test.ts`)
   - Tests for time tracking API client
   - Tests for activities API client
   - Use MSW to mock HTTP requests
   - Verify correct API calls and response handling

2. **Component Tests** (`src/components/*.test.tsx`)
   - Tests for React components
   - User interaction testing
   - Rendering and state management
   - Accessibility checks

## API Mocking with MSW

MSW intercepts API requests at the network level and returns mock responses. This approach:
- Works the same in tests, development, and debugging
- Doesn't require changing production code
- Allows testing error scenarios easily

### Mock Data

Mock data is defined in `src/test/mocks/handlers.ts`:

```typescript
export const mockActivities: Activity[] = [...];
export const mockTimeEntries: TimeEntry[] = [...];
export const mockRunningEntry: TimeEntry = {...};
```

### Customizing Mocks in Tests

You can override default handlers in specific tests:

```typescript
import { server } from '../test/mocks/server';
import { http, HttpResponse } from 'msw';

it('should handle API error', async () => {
  // Override the default handler for this test
  server.use(
    http.get('http://localhost:8000/api/activities/', () => {
      return new HttpResponse(null, { status: 500 });
    })
  );

  // Your test code here
});
```

## Writing Tests

### Example: API Client Test

```typescript
import { describe, it, expect } from 'vitest';
import { activitiesApi } from './activities';

describe('activitiesApi', () => {
  describe('getAll', () => {
    it('should return all activities', async () => {
      const activities = await activitiesApi.getAll();

      expect(activities).toBeDefined();
      expect(Array.isArray(activities)).toBe(true);
      expect(activities.length).toBeGreaterThan(0);
    });
  });
});
```

### Example: Component Test

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ActivityPicker from './ActivityPicker';

describe('ActivityPicker', () => {
  it('should render activities', async () => {
    const mockOnSelect = vi.fn();

    render(<ActivityPicker onSelectActivity={mockOnSelect} />);

    await waitFor(() => {
      expect(screen.getByText('Polieren')).toBeInTheDocument();
    });
  });

  it('should handle activity selection', async () => {
    const user = userEvent.setup();
    const mockOnSelect = vi.fn();

    render(<ActivityPicker onSelectActivity={mockOnSelect} />);

    await waitFor(() => {
      expect(screen.getByText('Polieren')).toBeInTheDocument();
    });

    const activity = screen.getByText('Polieren');
    await user.click(activity);

    expect(mockOnSelect).toHaveBeenCalled();
  });
});
```

## Test Coverage

### Coverage Goals

- **API Clients**: 90%+ coverage
- **Core Components**: 80%+ coverage
- **Utility Functions**: 95%+ coverage

### Viewing Coverage

After running `yarn test:coverage`, open `coverage/index.html` in your browser to see:
- Line coverage
- Branch coverage
- Function coverage
- File-by-file breakdown

## Best Practices

### 1. Test Behavior, Not Implementation

❌ Bad:
```typescript
expect(component.state.counter).toBe(5);
```

✅ Good:
```typescript
expect(screen.getByText('Count: 5')).toBeInTheDocument();
```

### 2. Use Testing Library Queries

Priority order:
1. `getByRole` - Most accessible
2. `getByLabelText` - Form elements
3. `getByPlaceholderText` - Form inputs
4. `getByText` - Non-interactive elements
5. `getByTestId` - Last resort

### 3. Wait for Async Operations

Always use `waitFor` or `findBy` queries for async operations:

```typescript
await waitFor(() => {
  expect(screen.getByText('Loaded')).toBeInTheDocument();
});

// Or use findBy (combines getBy + waitFor)
const element = await screen.findByText('Loaded');
```

### 4. Clean Up After Tests

The test setup automatically cleans up after each test:
- Resets MSW handlers
- Cleans up React components
- Clears mocks

### 5. Mock Functions

Use Vitest's `vi.fn()` for mock functions:

```typescript
const mockCallback = vi.fn();

// Assert it was called
expect(mockCallback).toHaveBeenCalled();
expect(mockCallback).toHaveBeenCalledTimes(1);
expect(mockCallback).toHaveBeenCalledWith(expectedArg);
```

## Troubleshooting

### Tests Hang or Timeout

- Check for missing `waitFor` around async operations
- Ensure MSW handlers return responses
- Check for infinite loops in useEffect

### "Not wrapped in act(...)" Warning

- Use `waitFor` or `findBy` queries
- Use `userEvent` instead of `fireEvent`
- Ensure all state updates complete before assertions

### API Calls Not Mocked

- Check MSW handler URL matches exactly
- Ensure server is started in setup.ts
- Check API_BASE constant matches test expectations

### Type Errors in Tests

- Ensure test file has `.tsx` extension for JSX
- Import types from `../types`
- Use `vi.fn()` with proper TypeScript types

## Continuous Integration

Tests should run automatically in CI/CD:

```yaml
# Example GitHub Actions workflow
- name: Run Frontend Tests
  run: |
    cd frontend
    yarn install
    yarn test --coverage
```

## Additional Resources

- [Vitest Documentation](https://vitest.dev/)
- [Testing Library Docs](https://testing-library.com/)
- [MSW Documentation](https://mswjs.io/)
- [Common Testing Mistakes](https://kentcdodds.com/blog/common-mistakes-with-react-testing-library)

## Test Files Overview

### API Client Tests (Completed)
- ✅ `src/api/timeTracking.test.ts` - 11 test suites, 30+ tests
- ✅ `src/api/activities.test.ts` - 8 test suites, 25+ tests

### Component Tests (Completed)
- ✅ `src/components/ActivityPicker.test.tsx` - 10 test suites, 40+ tests
- ✅ `src/components/TimerWidget.test.tsx` - 9 test suites, 35+ tests

### Future Test Files (Recommended)
- `src/components/QuickActionModal.test.tsx`
- `src/components/LocationPicker.test.tsx`
- `src/components/TimeTrackingTab.test.tsx`
- `src/contexts/TimeTrackingContext.test.tsx`

## Next Steps

1. **Install dependencies**: `cd frontend && yarn install`
2. **Run tests**: `yarn test`
3. **Check coverage**: `yarn test:coverage`
4. **Add more tests** as new components are created
5. **Set up E2E tests** with Playwright (separate guide)

---

**Note**: Some tests may fail initially if dependencies are not installed. Run `yarn install` first to resolve all testing dependencies.
