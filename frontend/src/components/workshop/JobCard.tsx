// One card on the Werkstatt board: number (link to the order or repair),
// title, customer, finer per-kind stage, deadline and the "Weiter" step.
import { Link } from 'react-router-dom';

import type { JobListItem } from '../../api/jobs';
import { getStatusLabel } from '../../design/status';
import { Button } from '../../ui/Button';
import { DeadlineChip } from '../../ui/DeadlineChip';
import { StatusBadge } from '../../ui/StatusBadge';
import { advanceStep, jobHref, KIND_LABELS } from './boardModel';

export interface JobCardProps {
  job: JobListItem;
  canAdvance: boolean;
  isAdvancing: boolean;
  onAdvance: (job: JobListItem) => void;
}

export function JobCard({ job, canAdvance, isAdvancing, onAdvance }: JobCardProps) {
  const href = jobHref(job);
  const step = canAdvance ? advanceStep(job) : null;
  const nextLabel = step ? getStatusLabel(step.statusKind, step.target) : null;

  return (
    <article className="workshop-card" aria-label={`${KIND_LABELS[job.kind]} ${job.number}`}>
      <div className="workshop-card__head">
        <span className="workshop-card__kind">{KIND_LABELS[job.kind]}</span>
        {href ? (
          <Link to={href} className="workshop-card__number ui-num">
            {job.number}
          </Link>
        ) : (
          <span className="workshop-card__number ui-num">{job.number}</span>
        )}
      </div>
      {job.title && <p className="workshop-card__title">{job.title}</p>}
      <p className="workshop-card__customer">{job.customer?.display_name ?? 'Ohne Kunde'}</p>
      <div className="workshop-card__badges">
        <StatusBadge kind={job.kind} status={job.kind_status} />
        <DeadlineChip deadline={job.deadline ?? null} />
      </div>
      {step && nextLabel && (
        <Button
          variant="secondary"
          icon="arrow-right"
          block
          loading={isAdvancing}
          onClick={() => onAdvance(job)}
          aria-label={`Weiter: ${nextLabel} (${job.number})`}
        >
          {`Weiter: ${nextLabel}`}
        </Button>
      )}
    </article>
  );
}
