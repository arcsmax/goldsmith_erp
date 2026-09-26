// One status column of the Werkstatt board. The column itself is a focus
// stop: Arrow left/right, Home and End move between columns (handled by the
// board), Tab walks into the cards.
import React, { forwardRef, useId } from 'react';

import type { JobListItem, JobStatus } from '../../api/jobs';
import { Button } from '../../ui/Button';
import { StatusBadge } from '../../ui/StatusBadge';
import { JobCard } from './JobCard';

export interface BoardColumnProps {
  status: JobStatus;
  jobs: readonly JobListItem[];
  total: number | null;
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
  canAdvance: boolean;
  advancingJobId: number | null;
  onAdvance: (job: JobListItem) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLElement>) => void;
  hintId: string;
}

function ColumnBody({
  jobs,
  isLoading,
  error,
  onRetry,
  canAdvance,
  advancingJobId,
  onAdvance,
}: Omit<BoardColumnProps, 'status' | 'total' | 'onKeyDown' | 'hintId'>) {
  if (isLoading) return <p className="workshop-column__note">Wird geladen…</p>;
  if (error) {
    return (
      <div className="workshop-column__note" role="alert">
        <p>{error}</p>
        <Button variant="secondary" icon="refresh" onClick={onRetry}>
          Erneut versuchen
        </Button>
      </div>
    );
  }
  if (jobs.length === 0) return <p className="workshop-column__note">Keine Einträge</p>;
  return (
    <ul className="workshop-column__cards">
      {jobs.map((job) => (
        <li key={job.id}>
          <JobCard
            job={job}
            canAdvance={canAdvance}
            isAdvancing={advancingJobId === job.id}
            onAdvance={onAdvance}
          />
        </li>
      ))}
    </ul>
  );
}

export const BoardColumn = forwardRef<HTMLElement, BoardColumnProps>(function BoardColumn(
  { status, total, onKeyDown, hintId, ...body },
  ref,
) {
  const headingId = useId();
  const truncated = total !== null && total > body.jobs.length;
  return (
    <section
      ref={ref}
      className="workshop-column"
      aria-labelledby={headingId}
      aria-describedby={hintId}
      tabIndex={0}
      onKeyDown={onKeyDown}
      data-status={status}
    >
      <h2 id={headingId} className="workshop-column__heading">
        <StatusBadge kind="job" status={status} />
        <span className="workshop-column__count ui-num" aria-label={`${total ?? 0} Einträge`}>
          {total ?? '–'}
        </span>
      </h2>
      {truncated && (
        <p className="workshop-column__note">
          {`${body.jobs.length} von ${total} angezeigt`}
        </p>
      )}
      <ColumnBody {...body} />
    </section>
  );
});
