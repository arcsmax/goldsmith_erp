// JobPicker — paged typeahead over GET /jobs (kind=order) for the timer.
//
// Time entries book onto an order (time_entries.order_id); repairs have no
// time-entry link yet, so the picker lists orders only. Results page by
// JOB_PICKER_PAGE_SIZE; every row is a 44px button.
import React, { useDeferredValue, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { jobsApi, type JobListItem } from '../../api/jobs';
import { queryKeys } from '../../api/queryKeys';
import { Button, EmptyState, Field } from '../../ui';

export const JOB_PICKER_PAGE_SIZE = 10;

export interface JobPickerProps {
  selectedOrderId: number;
  onSelect: (orderId: number, label: string) => void;
}

export function jobLabel(job: Pick<JobListItem, 'number' | 'title'>): string {
  return job.title ? `${job.number} – ${job.title}` : job.number;
}

export const JobPicker: React.FC<JobPickerProps> = ({ selectedOrderId, onSelect }) => {
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const needle = useDeferredValue(search.trim());
  const params = {
    kind: 'order' as const,
    q: needle.length > 0 ? needle : undefined,
    limit: JOB_PICKER_PAGE_SIZE,
    offset,
  };
  const jobs = useQuery({
    queryKey: queryKeys.jobs.page(params),
    queryFn: ({ signal }) => jobsApi.page(params, signal),
    placeholderData: keepPreviousData,
  });
  const items = (jobs.data?.items ?? []).filter((job) => job.order_id != null);
  const total = jobs.data?.total ?? 0;

  return (
    <div className="timer-edit-jobs">
      <Field label="Auftrag suchen" name="timer-edit-job-search" inputMode="search" help="Nummer, Titel oder Kunde">
        <input
          type="search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
        />
      </Field>

      {jobs.isError && (
        <p className="timer-error" role="alert">
          Aufträge konnten nicht geladen werden.
        </p>
      )}
      {jobs.isPending && <p role="status">Aufträge werden geladen…</p>}
      {jobs.isSuccess && items.length === 0 && (
        <EmptyState
          icon="search"
          title="Keine Aufträge gefunden."
          headingLevel={3}
          action={
            search ? (
              <Button variant="secondary" onClick={() => setSearch('')}>
                Suche zurücksetzen
              </Button>
            ) : undefined
          }
        />
      )}

      <ul className="timer-edit-jobs__list" aria-label="Aufträge">
        {items.map((job) => {
          const orderId = job.order_id as number;
          const isSelected = orderId === selectedOrderId;
          return (
            <li key={job.id}>
              <Button
                variant={isSelected ? 'primary' : 'secondary'}
                block
                aria-pressed={isSelected}
                onClick={() => onSelect(orderId, jobLabel(job))}
              >
                {jobLabel(job)}
              </Button>
            </li>
          );
        })}
      </ul>

      {total > JOB_PICKER_PAGE_SIZE && (
        <div className="timer-edit-jobs__paging">
          <Button
            variant="secondary"
            icon="arrow-left"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - JOB_PICKER_PAGE_SIZE))}
          >
            Vorherige Seite
          </Button>
          <Button
            variant="secondary"
            icon="arrow-right"
            disabled={offset + JOB_PICKER_PAGE_SIZE >= total}
            onClick={() => setOffset(offset + JOB_PICKER_PAGE_SIZE)}
          >
            Nächste Seite
          </Button>
        </div>
      )}
    </div>
  );
};

export default JobPicker;
