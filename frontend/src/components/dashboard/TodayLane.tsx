// One lane of the "Heute" view (W2-03) plus its row. Rows are links to the
// row's next action; a row without a permitted action renders as plain text.
import React from 'react';
import { Link } from 'react-router-dom';
import { useOrders } from '../../contexts/OrderContext';
import type { RowAction } from './todayLanes';

export type RowTone = 'urgent' | 'soon' | 'ok';

export interface TodayRowProps {
  tone: RowTone;
  badge: string;
  badgeLabel: string;
  title: string;
  meta: ReadonlyArray<string | null | undefined>;
  action: RowAction | null;
}

export const TodayRow: React.FC<TodayRowProps> = ({
  tone,
  badge,
  badgeLabel,
  title,
  meta,
  action,
}) => {
  const { setOrderTab } = useOrders();
  const content = (
    <>
      <div className={`deadline-badge deadline-${tone}`}>
        <span className="deadline-days today-tabular">{badge}</span>
        <span className="deadline-label">{badgeLabel}</span>
      </div>
      <div className="deadline-content">
        <h4 className="deadline-title">{title}</h4>
        <div className="deadline-meta today-meta">
          {meta.filter(Boolean).map((part) => (
            <span key={part} className="today-tabular">
              {part}
            </span>
          ))}
        </div>
      </div>
      {action && <span className="today-row-action">{action.label} ›</span>}
    </>
  );

  const className = `deadline-item deadline-${tone} today-row`;
  if (!action) {
    return <div className={`${className} today-row-static`}>{content}</div>;
  }
  const handleClick = (): void => {
    if (action.orderTab) setOrderTab(action.orderTab.orderId, action.orderTab.tab);
  };
  return (
    <Link to={action.to} className={className} onClick={handleClick}>
      {content}
    </Link>
  );
};

export interface TodayLaneProps {
  id: string;
  title: string;
  count: number;
  emptyText: string;
  emptyAction?: { to: string; label: string };
  children: React.ReactNode;
}

export const TodayLane: React.FC<TodayLaneProps> = ({
  id,
  title,
  count,
  emptyText,
  emptyAction,
  children,
}) => (
  <section className="dashboard-section today-lane" id={id} aria-labelledby={`${id}-title`}>
    <div className="widget-header">
      <h2 id={`${id}-title`}>
        {title} <span className="today-tabular">({count})</span>
      </h2>
    </div>
    {count === 0 ? (
      <div className="no-deadlines">
        <p>{emptyText}</p>
        {emptyAction && (
          <Link to={emptyAction.to} className="btn btn-secondary today-empty-action">
            {emptyAction.label}
          </Link>
        )}
      </div>
    ) : (
      <div className="deadlines-list">{children}</div>
    )}
  </section>
);
