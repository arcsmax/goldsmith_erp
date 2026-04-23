// ErrorBoundary — class component (hooks cannot catch render errors).
// Two variants:
//   - "app"  wraps the root <Suspense>/router; fallback offers a single
//            "Neu laden" action (no point navigating home when the whole
//            shell failed to mount).
//   - "page" wraps MainLayout's <Outlet/>; a single page crash keeps the
//            nav, timer widget, scan FAB and notification bell alive.
// Fallback UX uses German copy to match the rest of the app.
import { Component, type ReactNode, type ErrorInfo } from 'react';
import '../styles/components/ErrorBoundary.css';

export type ErrorBoundaryVariant = 'app' | 'page';

interface Props {
  variant: ErrorBoundaryVariant;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Fail loudly (project rule) — do not swallow.
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught', error, info);
    // V1.2 hook: once Sentry lands (see FIX-PLAN.md §1.8c) add
    //   Sentry.captureException(error, { contexts: { react: info } });
  }

  componentDidUpdate(prevProps: Props): void {
    // If the children prop identity changes after an error (e.g. the user
    // navigated to a different route after a page-level crash), clear the
    // error so the new children get a chance to render. Without this the
    // boundary would cling to the stale error forever.
    if (this.state.error && prevProps.children !== this.props.children) {
      this.setState({ error: null });
    }
  }

  handleRetry = (): void => {
    this.setState({ error: null });
  };

  handleHome = (): void => {
    window.location.href = '/';
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      const isApp = this.props.variant === 'app';
      return (
        <div
          role="alert"
          className="error-boundary"
          data-variant={this.props.variant}
        >
          <h1>Etwas ist schiefgelaufen.</h1>
          <p>
            {isApp
              ? 'Die Anwendung konnte nicht geladen werden. Bitte neu laden.'
              : 'Diese Seite hat einen Fehler. Du kannst es erneut versuchen oder zur Startseite zurückkehren.'}
          </p>
          {import.meta.env.DEV && (
            <pre className="error-boundary__details">{error.message}</pre>
          )}
          <div className="error-boundary__actions">
            <button type="button" onClick={this.handleRetry}>
              Neu laden
            </button>
            {!isApp && (
              <button type="button" onClick={this.handleHome}>
                Zur Startseite
              </button>
            )}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
