// ListCard (UI-UX-PLAYBOOK 4.5): one list row on tablet and phone. The whole
// card is one link (never a clickable <div>). Slots follow the list-page
// template: thumbnail, title, meta (customer), and badges (DeadlineChip,
// StatusBadge).
import React from 'react';
import { Link } from 'react-router-dom';

import { cx } from './devAssert';

export interface ListCardProps {
  href?: string;
  title: React.ReactNode;
  meta?: React.ReactNode;
  /** DeadlineChip, StatusBadge; rendered on their own line. */
  badges?: React.ReactNode;
  thumbnail?: React.ReactNode;
  /** Extra label/value lines (DataTable passes its visible columns). */
  details?: Array<{ key: string; label: string; value: React.ReactNode; numeric?: boolean }>;
  className?: string;
}

export const ListCard: React.FC<ListCardProps> = ({
  href,
  title,
  meta,
  badges,
  thumbnail,
  details,
  className,
}) => {
  const content = (
    <>
      {thumbnail && <span className="ui-list-card__thumb">{thumbnail}</span>}
      <span className="ui-list-card__main">
        <span className="ui-list-card__title">{title}</span>
        {meta && <span className="ui-list-card__meta">{meta}</span>}
        {badges && <span className="ui-list-card__badges">{badges}</span>}
        {details && details.length > 0 && (
          <span className="ui-list-card__details">
            {details.map((detail) => (
              <span key={detail.key} className="ui-list-card__detail">
                <span className="ui-list-card__detail-label">{detail.label}</span>
                <span className={cx(detail.numeric && 'ui-num')}>{detail.value}</span>
              </span>
            ))}
          </span>
        )}
      </span>
    </>
  );

  if (href) {
    return (
      <Link to={href} className={cx('ui-list-card', 'ui-list-card--link', className)}>
        {content}
      </Link>
    );
  }
  return <div className={cx('ui-list-card', className)}>{content}</div>;
};
