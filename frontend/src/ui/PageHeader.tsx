// PageHeader (UI-UX-PLAYBOOK 4.10): the page title (the only h1), context
// meta, an optional back link and the one primary action. On phones the
// primary action moves into a sticky bottom bar (ui.css).
import React from 'react';
import { Link } from 'react-router-dom';

import { cx } from './devAssert';
import { Icon } from './Icon';

export interface PageHeaderProps {
  title: string;
  /** Context under the title ("12 von 40", StatusBadge + DeadlineChip on detail pages). */
  meta?: React.ReactNode;
  back?: { to: string; label: string };
  /** The one primary action: a Button or ButtonLink. */
  primaryAction?: React.ReactNode;
  secondaryActions?: React.ReactNode;
  /** Below 600px pin the primary action to a bottom bar (default true). */
  stickyPrimary?: boolean;
  className?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  meta,
  back,
  primaryAction,
  secondaryActions,
  stickyPrimary = true,
  className,
}) => (
  <header
    className={cx(
      'ui-page-header',
      stickyPrimary && Boolean(primaryAction) && 'ui-page-header--sticky-primary',
      className,
    )}
  >
    {back && (
      <Link to={back.to} className="ui-page-header__back">
        <Icon name="arrow-left" />
        {back.label}
      </Link>
    )}
    <div className="ui-page-header__row">
      <div className="ui-page-header__text">
        <h1 className="ui-page-header__title">{title}</h1>
        {meta && <div className="ui-page-header__meta">{meta}</div>}
      </div>
      {(primaryAction || secondaryActions) && (
        <div className="ui-page-header__actions">
          {secondaryActions}
          {primaryAction && <div className="ui-page-header__primary">{primaryAction}</div>}
        </div>
      )}
    </div>
  </header>
);
