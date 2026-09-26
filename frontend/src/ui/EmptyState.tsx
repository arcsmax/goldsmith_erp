// EmptyState (UI-UX-PLAYBOOK 4.7): tell the user what to do when there is
// nothing to show. Lists the user can fill must pass an `action`
// ("Ersten Auftrag anlegen"); only truly read-only views may omit it.
import React from 'react';

import { cx } from './devAssert';
import { Icon, type IconName } from './Icon';

export interface EmptyStateProps {
  icon?: IconName;
  title: string;
  body?: string;
  /** Primary action: a Button or ButtonLink. */
  action?: React.ReactNode;
  secondaryAction?: React.ReactNode;
  /** Heading level; default h2 (use 3 inside a titled Card). */
  headingLevel?: 2 | 3;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon = 'inbox',
  title,
  body,
  action,
  secondaryAction,
  headingLevel = 2,
  className,
}) => {
  const Heading = headingLevel === 3 ? 'h3' : 'h2';
  return (
    <div className={cx('ui-empty-state', className)}>
      <Icon name={icon} className="ui-empty-state__icon" />
      <Heading className="ui-empty-state__title">{title}</Heading>
      {body && <p className="ui-empty-state__body">{body}</p>}
      {(action || secondaryAction) && (
        <div className="ui-empty-state__actions">
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  );
};
