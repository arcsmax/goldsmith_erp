// DeadlineChip (UI-UX-PLAYBOOK 3.2 and 4.2): deadline urgency by shape plus
// text, never colour alone (design-investigation I-04):
//   ● "in 9 Tagen"         neutral  (more than 3 days left)
//   ▲ "in 2 Tagen"         waiting  (0 to 3 days: heute / morgen / in N Tagen)
//   ■ "3 Tage überfällig"  danger   (past the deadline)
// Days are counted in local calendar days, so "heute" means today's date,
// not "within 24 hours". The exact date is in a <time> with a title.
import React from 'react';

import { cx } from './devAssert';

export type DeadlineTone = 'neutral' | 'waiting' | 'danger' | 'none';

export const DEADLINE_SOON_DAYS = 3;
const MS_PER_DAY = 24 * 60 * 60 * 1000;
const SHAPES: Record<Exclude<DeadlineTone, 'none'>, string> = {
  neutral: '●',
  waiting: '▲',
  danger: '■',
};

export interface DeadlineDescription {
  tone: DeadlineTone;
  label: string;
  /** Calendar days until the deadline (negative = overdue); null without a deadline. */
  days: number | null;
  date: Date | null;
}

/** Parse "YYYY-MM-DD" as a local date and ISO date-times as instants. */
function parseDeadline(value: string): Date | null {
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function describeDeadline(deadline: string | null | undefined, now: Date = new Date()): DeadlineDescription {
  const date = deadline ? parseDeadline(deadline) : null;
  if (!date) return { tone: 'none', label: 'Keine Frist', days: null, date: null };

  const days = Math.round((startOfDay(date) - startOfDay(now)) / MS_PER_DAY);
  if (days < 0) {
    return { tone: 'danger', label: `${plural(-days, 'Tag', 'Tage')} überfällig`, days, date };
  }
  if (days === 0) return { tone: 'waiting', label: 'heute fällig', days, date };
  if (days === 1) return { tone: 'waiting', label: 'morgen fällig', days, date };
  const tone: DeadlineTone = days <= DEADLINE_SOON_DAYS ? 'waiting' : 'neutral';
  return { tone, label: `in ${days} Tagen`, days, date };
}

const DATE_FORMAT = new Intl.DateTimeFormat('de-DE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

function toIsoDate(date: Date): string {
  const pad = (n: number): string => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export interface DeadlineChipProps {
  deadline: string | null;
  /** Injected for tests and the demo page. */
  now?: Date;
  size?: 'md' | 'lg';
  className?: string;
}

export const DeadlineChip: React.FC<DeadlineChipProps> = ({ deadline, now, size = 'md', className }) => {
  const { tone, label, date } = describeDeadline(deadline, now);
  const classes = cx('ui-deadline-chip', `ui-deadline-chip--${tone}`, `ui-deadline-chip--${size}`, className);

  if (tone === 'none' || !date) {
    return <span className={classes}>{label}</span>;
  }
  return (
    <span className={classes}>
      <span className="ui-deadline-chip__shape" aria-hidden="true">
        {SHAPES[tone]}
      </span>
      <time dateTime={toIsoDate(date)} title={`Frist: ${DATE_FORMAT.format(date)}`}>
        {label}
      </time>
    </span>
  );
};
