// ConsultationsPage — Beratungen list on TanStack Query (W4-03).
//
// GET /consultations/ answers with a legacy plain list (no Page envelope),
// so it runs inside useQuery with the status filter in the key. Each
// Beratung is a ListCard whose whole card is a link: drafts resume at the
// wizard step where editing left off, everything else opens the summary.
// No realtime channel carries consultation changes; the wizard invalidates
// ['consultations'] after its writes.
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';
import { consultationsApi } from '../api/consultations';
import { queryKeys } from '../api/queryKeys';
import type { ConsultationListItem, ConsultationStatus } from '../types';
import { OCCASION_LABELS, PIECE_TYPE_LABELS } from '../components/consultation/labels';
import { logError } from '../lib/logError';
import { getErrorMessage } from '../lib/errors';
import { CONSULTATION_STATUS, statusLabelsFor } from '../design/status';
import { ButtonLink, ListCard, PageHeader, PageState, type PageStateValue } from '../ui';
import { StatusBadge } from '../ui/StatusBadge';
import '../styles/consultations.css';

const STATUS_LABELS = statusLabelsFor(CONSULTATION_STATUS);

const STATUS_FILTERS: { label: string; value: ConsultationStatus | undefined }[] = [
  { label: 'Alle', value: undefined },
  ...(Object.keys(STATUS_LABELS) as ConsultationStatus[]).map((value) => ({
    label: STATUS_LABELS[value],
    value,
  })),
];

/** Drafts resume at step 2 (occasion/budget; step 1, the customer, is done
 *  for an existing draft); everything else opens the read-only summary. */
const DRAFT_RESUME_STEP = 2;
const SUMMARY_STEP = 7;

function targetStepFor(status: ConsultationStatus): number {
  return status === 'draft' ? DRAFT_RESUME_STEP : SUMMARY_STEP;
}

function formatDay(iso: string): string {
  return format(new Date(iso), 'dd.MM.yyyy');
}

async function fetchConsultations(status: ConsultationStatus | undefined): Promise<ConsultationListItem[]> {
  try {
    return await consultationsApi.getAll({ status });
  } catch (err) {
    logError('Beratungen laden fehlgeschlagen', err);
    throw err;
  }
}

const NewConsultationLink: React.FC = () => (
  <ButtonLink to="/consultations/new" icon="plus">
    Beratung starten
  </ButtonLink>
);

const ConsultationCard: React.FC<{ item: ConsultationListItem }> = ({ item }) => (
  <ListCard
    href={`/consultations/${item.id}?step=${targetStepFor(item.status)}`}
    title={OCCASION_LABELS[item.occasion]}
    badges={<StatusBadge kind="consultation" status={item.status} />}
    meta={
      <>
        <span>{item.piece_type ? PIECE_TYPE_LABELS[item.piece_type] : 'Kein Schmuckstück-Typ'}</span>
        <span aria-hidden="true"> · </span>
        <span className="ui-num">{formatDay(item.created_at)}</span>
        {item.follow_up_at && (
          <span className="consultation-card__followup">
            {' '}
            · Wiedervorlage: <span className="ui-num">{formatDay(item.follow_up_at)}</span>
          </span>
        )}
      </>
    }
  />
);

export const ConsultationsPage: React.FC = () => {
  const [statusFilter, setStatusFilter] = useState<ConsultationStatus | undefined>(undefined);
  const query = useQuery({
    queryKey: queryKeys.consultations.list(statusFilter),
    queryFn: () => fetchConsultations(statusFilter),
  });
  const consultations = query.data ?? [];

  let state: PageStateValue = { status: consultations.length ? 'ready' : 'empty' };
  if (query.isPending) state = { status: 'loading' };
  if (query.isError) {
    state = {
      status: 'error',
      error: getErrorMessage(query.error, 'Beratungen konnten nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }

  return (
    <div className="page-container consultations-page">
      <PageHeader title="Beratungen" primaryAction={<NewConsultationLink />} />

      <div className="chip-group consultation-status-filters" role="group" aria-label="Nach Status filtern">
        {STATUS_FILTERS.map((filter) => (
          <button
            key={filter.label}
            type="button"
            className={`chip${statusFilter === filter.value ? ' selected' : ''}`}
            aria-pressed={statusFilter === filter.value}
            onClick={() => setStatusFilter(filter.value)}
          >
            {filter.label}
          </button>
        ))}
      </div>

      <PageState
        state={state}
        skeleton="cards"
        empty={{
          icon: 'inbox',
          title: 'Keine Beratungen gefunden',
          body: statusFilter ? 'Einen anderen Status wählen.' : 'Starten Sie eine neue Beratung, um loszulegen.',
          action: <NewConsultationLink />,
        }}
      >
        <ul className="consultation-list" aria-label="Beratungen">
          {consultations.map((item) => (
            <li key={item.id}>
              <ConsultationCard item={item} />
            </li>
          ))}
        </ul>
      </PageState>
    </div>
  );
};
