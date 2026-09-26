// DataTable (UI-UX-PLAYBOOK 4.5): every list.
//
// - 600px and up: semantic <table> with <caption>, sunken sticky header in
//   sentence case, numeric columns right-aligned with tabular numerals,
//   sortable headers as buttons with aria-sort on the <th>;
// - below 600px: the same rows as a list of ListCards, each one link;
//   (CSS in ui.css switches between the two; the hidden one is display:none,
//   so assistive tech sees only one.)
// - rows navigate through a link in the first column, never <tr onClick>;
// - `hideBelow` hides a column below a breakpoint ('tablet' = below 600px,
//   so it is also left out of the phone card; 'desktop' = below 1024px);
// - `state` delegates loading/error to PageState; no rows renders `empty`.
//
// TODO(W4 StatusBadge): status columns should render <StatusBadge kind status>
// from src/ui/StatusBadge.tsx (built in parallel) via the column `render`.
import React from 'react';
import { Link } from 'react-router-dom';

import { cx } from './devAssert';
import { EmptyState, type EmptyStateProps } from './EmptyState';
import { Icon } from './Icon';
import { ListCard } from './ListCard';
import { PageState, type PageStateValue } from './PageState';

export type SortDirection = 'asc' | 'desc';
export type SortState = { key: string; direction: SortDirection };

export type Column<T> = {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  align?: 'start' | 'end';
  hideBelow?: 'tablet' | 'desktop';
  /** Right-aligned, tabular numerals (prices, weights, hours, dates). */
  numeric?: boolean;
  sortable?: boolean;
  /**
   * Extra class on this column's `<th>`/`<td>` for a page-scoped CSS hook
   * (e.g. permanently hiding the lowest-value column at tablet-and-up
   * widths — `hideBelow` alone tops out at 1024px, the playbook's widest
   * breakpoint, so it cannot express "desktop is too crowded for this
   * column too"; see `.orders-col-description` in orders.css for the
   * precedent this mirrors). Never used for layout/spacing — those still
   * come from the shared scales.
   */
  className?: string;
};

export interface DataTableProps<T> {
  rows: T[];
  columns: Column<T>[];
  getRowKey: (row: T) => string | number;
  /** Link target per row; the first column becomes the link. */
  rowHref?: (row: T) => string;
  /** Table caption and list label (visually hidden unless showCaption). */
  caption: string;
  showCaption?: boolean;
  state?: PageStateValue;
  empty?: EmptyStateProps;
  sort?: SortState;
  onSortChange?: (sort: SortState) => void;
  /** Phone card slots; defaults derive from the columns. */
  cardTitle?: (row: T) => React.ReactNode;
  cardMeta?: (row: T) => React.ReactNode;
  cardBadges?: (row: T) => React.ReactNode;
  cardThumbnail?: (row: T) => React.ReactNode;
  className?: string;
}

const ARIA_SORT: Record<SortDirection, 'ascending' | 'descending'> = {
  asc: 'ascending',
  desc: 'descending',
};

function nextSort(current: SortState | undefined, key: string): SortState {
  if (current?.key === key) {
    return { key, direction: current.direction === 'asc' ? 'desc' : 'asc' };
  }
  return { key, direction: 'asc' };
}

function cellClasses<T>(column: Column<T>): string {
  return cx(
    column.numeric && 'ui-num',
    (column.align === 'end' || (column.numeric && column.align !== 'start')) && 'ui-align-end',
    column.hideBelow && `ui-hide-below-${column.hideBelow}`,
    column.className,
  );
}

function SortableHeader<T>({
  column,
  sort,
  onSortChange,
}: {
  column: Column<T>;
  sort?: SortState;
  onSortChange?: (sort: SortState) => void;
}) {
  const isSortable = Boolean(column.sortable && onSortChange);
  const active = sort?.key === column.key ? sort.direction : undefined;
  if (!isSortable) {
    return (
      <th scope="col" className={cellClasses(column)}>
        {column.header}
      </th>
    );
  }
  const iconName = active === 'asc' ? 'chevron-up' : active === 'desc' ? 'chevron-down' : 'chevrons-up-down';
  return (
    <th scope="col" className={cellClasses(column)} aria-sort={active ? ARIA_SORT[active] : 'none'}>
      <button
        type="button"
        className="ui-table__sort"
        onClick={() => onSortChange?.(nextSort(sort, column.key))}
      >
        {column.header}
        <Icon name={iconName} />
      </button>
    </th>
  );
}

export function DataTable<T>({
  rows,
  columns,
  getRowKey,
  rowHref,
  caption,
  showCaption = false,
  state,
  empty,
  sort,
  onSortChange,
  cardTitle,
  cardMeta,
  cardBadges,
  cardThumbnail,
  className,
}: DataTableProps<T>): React.ReactElement {
  if (state && (state.status === 'loading' || state.status === 'error')) {
    return <PageState state={state} skeleton="list" />;
  }
  if (rows.length === 0 || state?.status === 'empty') {
    return <EmptyState title="Keine Einträge" {...empty} />;
  }

  const [firstColumn, ...restColumns] = columns;
  const cardColumns = restColumns.filter((column) => column.hideBelow !== 'tablet');

  return (
    <div className={cx('ui-data-table', className)}>
      <div className="ui-table-scroll">
        <table className="ui-table">
          <caption className={showCaption ? 'ui-table__caption' : 'ui-visually-hidden'}>
            {caption}
          </caption>
          <thead>
            <tr>
              {columns.map((column) => (
                <SortableHeader
                  key={column.key}
                  column={column}
                  sort={sort}
                  onSortChange={onSortChange}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={getRowKey(row)}>
                {columns.map((column) => {
                  const content = column.render(row);
                  const isLinkCell = column === firstColumn && rowHref;
                  return (
                    <td key={column.key} className={cellClasses(column)}>
                      {isLinkCell ? (
                        <Link to={rowHref(row)} className="ui-table__link">
                          {content}
                        </Link>
                      ) : (
                        content
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="ui-card-list" aria-label={caption}>
        {rows.map((row) => (
          <li key={getRowKey(row)}>
            <ListCard
              href={rowHref?.(row)}
              title={cardTitle ? cardTitle(row) : firstColumn.render(row)}
              meta={cardMeta?.(row)}
              badges={cardBadges?.(row)}
              thumbnail={cardThumbnail?.(row)}
              details={
                cardMeta || cardBadges
                  ? undefined
                  : cardColumns.map((column) => ({
                      key: column.key,
                      label: column.header,
                      value: column.render(row),
                      numeric: column.numeric,
                    }))
              }
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
