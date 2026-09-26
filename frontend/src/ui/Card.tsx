// Card (UI-UX-PLAYBOOK 4.6): a raised group of related content with an
// optional heading and one header action. With a title it is a labelled
// region; without one it is a plain block. Use cards only where content is
// really a separate group, plain sections elsewhere.
import React, { useId } from 'react';

import { cx } from './devAssert';

export type CardTone = 'info' | 'waiting' | 'danger' | 'done';

export interface CardProps {
  title?: string;
  /** Heading level for the title; default h2. */
  headingLevel?: 2 | 3;
  /** A link or Button shown in the card header. */
  action?: React.ReactNode;
  /** Alert cards only. */
  tone?: CardTone;
  className?: string;
  children: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({
  title,
  headingLevel = 2,
  action,
  tone,
  className,
  children,
}) => {
  const headingId = useId();
  const Heading = headingLevel === 3 ? 'h3' : 'h2';
  const classes = cx('ui-card', tone && `ui-card--${tone}`, className);

  if (!title) {
    return (
      <div className={classes}>
        {action && <div className="ui-card__header ui-card__header--action-only">{action}</div>}
        {children}
      </div>
    );
  }

  return (
    <section className={classes} aria-labelledby={headingId}>
      <div className="ui-card__header">
        <Heading id={headingId} className="ui-card__title">
          {title}
        </Heading>
        {action && <div className="ui-card__action">{action}</div>}
      </div>
      <div className="ui-card__body">{children}</div>
    </section>
  );
};
