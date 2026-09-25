// PageState (UI-UX-PLAYBOOK 4.8; review 04 section F item 5 "AsyncState"):
// loading, error and empty for a whole page or region, one component instead
// of 54 copies of loading/error boilerplate.
//
// - loading: "Wird geladen…" in a polite live region at once; the skeleton
//   (aria-hidden, mirrors the layout) appears only after 300ms to avoid flicker;
// - error: what failed (role="alert") and "Erneut versuchen" when retry exists;
//   pass getErrorMessage(err) from src/lib/errors as `error`;
// - empty: the EmptyState;
// - ready: children.
import React, { useEffect, useState } from 'react';

import { Button } from './Button';
import { cx } from './devAssert';
import { EmptyState, type EmptyStateProps } from './EmptyState';
import { Icon } from './Icon';

export const SKELETON_DELAY_MS = 300;
const DEFAULT_ERROR = 'Daten konnten nicht geladen werden.';

export type PageStateValue = {
  status: 'loading' | 'error' | 'empty' | 'ready';
  error?: string;
  retry?: () => void;
};

export type SkeletonLayout = 'list' | 'detail' | 'cards';

export interface PageStateProps {
  state: PageStateValue;
  skeleton?: SkeletonLayout;
  /** Rows (list) or blocks (detail/cards) the skeleton draws. */
  skeletonCount?: number;
  empty?: EmptyStateProps;
  className?: string;
  children?: React.ReactNode;
}

const Skeleton: React.FC<{ layout: SkeletonLayout; count: number }> = ({ layout, count }) => (
  <div className={cx('ui-skeleton', `ui-skeleton--${layout}`)} aria-hidden="true">
    {Array.from({ length: count }, (_, index) => (
      <div key={index} className="ui-skeleton__block" />
    ))}
  </div>
);

const Loading: React.FC<{ layout: SkeletonLayout; count: number }> = ({ layout, count }) => {
  const [showSkeleton, setShowSkeleton] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setShowSkeleton(true), SKELETON_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);
  return (
    <div className="ui-page-state ui-page-state--loading">
      <p role="status" aria-live="polite" className="ui-visually-hidden">
        Wird geladen…
      </p>
      {showSkeleton && <Skeleton layout={layout} count={count} />}
    </div>
  );
};

export const PageState: React.FC<PageStateProps> = ({
  state,
  skeleton = 'list',
  skeletonCount = 5,
  empty,
  className,
  children,
}) => {
  if (state.status === 'loading') {
    return (
      <div className={className}>
        <Loading layout={skeleton} count={skeletonCount} />
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className={cx('ui-page-state', 'ui-page-state--error', className)}>
        <div role="alert" className="ui-page-state__message">
          <Icon name="alert-triangle" />
          <p>{state.error || DEFAULT_ERROR}</p>
        </div>
        {state.retry && (
          <Button variant="secondary" icon="refresh" onClick={state.retry}>
            Erneut versuchen
          </Button>
        )}
      </div>
    );
  }

  if (state.status === 'empty') {
    return <EmptyState title="Keine Einträge" {...empty} className={className} />;
  }

  return <>{children}</>;
};
