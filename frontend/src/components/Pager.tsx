// Pager — previous/next controls for a server-paged list (W3-03).
// Uses the src/ui Button; the page number and total come from the Page
// envelope, never from the rows on screen.
import React from 'react';
import { Button } from '../ui';

export interface PagerProps {
  /** 1-based. */
  pageNumber: number;
  /** Omit when the endpoint sends no total (legacy lists): shows "Seite N". */
  pageCount?: number;
  /** Optional summary text, e.g. "60 Kunden". */
  summary?: string;
  onPrevious: () => void;
  onNext: () => void;
  hasNext: boolean;
  /** A new page is on its way (the current rows stay visible meanwhile). */
  isFetching?: boolean;
  label: string;
}

export const Pager: React.FC<PagerProps> = ({
  pageNumber,
  pageCount,
  summary,
  onPrevious,
  onNext,
  hasNext,
  isFetching = false,
  label,
}) => (
  <nav className="pagination-controls" aria-label={label}>
    <p className="pagination-info" aria-live="polite">
      Seite {pageNumber}
      {pageCount !== undefined && ` von ${pageCount}`}
      {summary && ` • ${summary}`}
      {isFetching && <span className="ui-visually-hidden"> Wird geladen…</span>}
    </p>
    <div className="pager-buttons">
      <Button
        variant="secondary"
        onClick={onPrevious}
        disabled={pageNumber <= 1}
        aria-label="Vorherige Seite"
      >
        ‹ Zurück
      </Button>{' '}
      <Button variant="secondary" onClick={onNext} disabled={!hasNext} aria-label="Nächste Seite">
        Weiter ›
      </Button>
    </div>
  </nav>
);
