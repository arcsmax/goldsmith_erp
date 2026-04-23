// Tests for ErrorBoundary component (A5).
// Verifies: children render when healthy, fallback renders on throw,
// retry clears state, and console.error is called so errors remain observable.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from './ErrorBoundary';

function Boom({ msg = 'kaboom' }: { msg?: string }): JSX.Element {
  throw new Error(msg);
}

describe('ErrorBoundary', () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // React logs caught errors to console.error in dev; suppress noise + assert.
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('renders children when no error', () => {
    render(
      <ErrorBoundary variant="page">
        <div>hello</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('hello')).toBeInTheDocument();
  });

  it('renders fallback when child throws', () => {
    render(
      <ErrorBoundary variant="page">
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /neu laden/i })
    ).toBeInTheDocument();
  });

  it('clears error when retry is clicked', () => {
    const { rerender } = render(
      <ErrorBoundary variant="page">
        <Boom />
      </ErrorBoundary>
    );
    fireEvent.click(screen.getByRole('button', { name: /neu laden/i }));
    // After retry the boundary state resets; re-render with a healthy child.
    rerender(
      <ErrorBoundary variant="page">
        <div>recovered</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('recovered')).toBeInTheDocument();
  });

  it('calls console.error (visible in dev)', () => {
    render(
      <ErrorBoundary variant="page">
        <Boom msg="visible-error" />
      </ErrorBoundary>
    );
    expect(consoleErrorSpy).toHaveBeenCalled();
  });

  it('app variant hides the Startseite button', () => {
    render(
      <ErrorBoundary variant="app">
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /zur startseite/i })
    ).not.toBeInTheDocument();
  });

  it('page variant exposes the Startseite button', () => {
    render(
      <ErrorBoundary variant="page">
        <Boom />
      </ErrorBoundary>
    );
    expect(
      screen.getByRole('button', { name: /zur startseite/i })
    ).toBeInTheDocument();
  });
});
