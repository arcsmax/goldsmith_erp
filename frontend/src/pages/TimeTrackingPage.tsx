// Zeiterfassung (W4-03): bench-mode page on src/ui primitives and queries.
//
// Data: the signed-in user's entries as one server page at a time
// (GET /time-tracking/user/{id}?offset=…, Page envelope, sorted server-side
// by start_time), activities from the shared query. Create, update and
// delete are mutations that invalidate ['timer'] (lists, running timer,
// summary) and ['dashboard']. A time_tracking_updates hint refreshes the
// same root through lib/realtimeInvalidation.ts. The running timer comes
// from TimeTrackingContext (the one cross-page timer state).
import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { timeTrackingApi, type RunningTimeEntry } from '../api/time-tracking';
import { queryKeys } from '../api/queryKeys';
import { TIME_ENTRY_PAGE_SIZE, userEntriesQuery } from '../api/timeTrackingQueries';
import { pageInfo } from '../api/paged';
import { Pager } from '../components/Pager';
import { BenchModeToggle } from '../components/scanner/BenchModeToggle';
import { RunningTimerEditSheet } from '../components/time-tracking/RunningTimerEditSheet';
import { TimeEntryFormModal } from '../components/time-tracking/TimeEntryFormModal';
import { TimeReportsSection } from '../components/time-tracking/TimeReportsSection';
import { TimeSummaryCards } from '../components/time-tracking/TimeSummaryCards';
import { useAuth, useConfirm, useTimeTracking, useToast } from '../contexts';
import { getErrorMessage } from '../lib/errors';
import { Button, Card, DataTable, Icon, PageHeader, type Column, type PageStateValue } from '../ui';
import { StatusBadge } from '../ui/StatusBadge';
import { formatDateTime, formatDuration } from '../utils/formatters';
import type { Activity, TimeEntry, TimeEntryCreateInput, TimeEntryUpdateInput } from '../types';
import '../styles/pages.css';
import '../styles/time-tracking.css';

type SortOrder = '-start_time' | 'start_time';
const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;

const openTimer = () => window.dispatchEvent(new Event('timer:expand'));

/** "Läuft" / "Pausiert" / duration: icon plus text, never colour alone. */
const EntryState: React.FC<{ entry: TimeEntry }> = ({ entry }) => {
  if (entry.end_time) {
    return <span className="time-entry-duration-cell">{formatDuration(entry.duration_minutes ?? 0)}</span>;
  }
  if (entry.is_paused) return <StatusBadge kind="timeEntry" status="paused" />;
  return (
    <span className="time-entry-running">
      <Icon name="clock" /> Läuft
    </span>
  );
};

function useEntryMutations(onSaved: () => void) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.timer.all }),
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all }),
    ]);
  const create = useMutation({
    mutationFn: (data: TimeEntryCreateInput) => timeTrackingApi.createManual(data),
    onSuccess: async () => {
      await invalidate();
      onSaved();
      showToast('Zeiteintrag angelegt', 'success');
    },
    onError: (err) => showToast(getErrorMessage(err, 'Zeiteintrag konnte nicht angelegt werden'), 'error'),
  });
  const update = useMutation({
    mutationFn: ({ id, data }: { id: string; data: TimeEntryUpdateInput }) => timeTrackingApi.update(id, data),
    onSuccess: async () => {
      await invalidate();
      onSaved();
      showToast('Zeiteintrag gespeichert', 'success');
    },
    onError: (err) => showToast(getErrorMessage(err, 'Zeiteintrag konnte nicht gespeichert werden'), 'error'),
  });
  const remove = useMutation({
    mutationFn: (id: string) => timeTrackingApi.delete(id),
    onSuccess: async () => {
      await invalidate();
      onSaved();
      showToast('Zeiteintrag gelöscht', 'success');
    },
    onError: (err) => showToast(getErrorMessage(err, 'Zeiteintrag konnte nicht gelöscht werden'), 'error'),
  });
  return { create, update, remove };
}

function entryColumns(
  activityName: (id: number) => string,
  onEdit: (entry: TimeEntry) => void,
): Column<TimeEntry>[] {
  return [
    { key: 'start', header: 'Start', numeric: true, render: (e) => formatDateTime(e.start_time) },
    {
      key: 'end',
      header: 'Ende',
      numeric: true,
      hideBelow: 'tablet',
      render: (e) => (e.end_time ? formatDateTime(e.end_time) : '–'),
    },
    { key: 'state', header: 'Dauer', numeric: true, render: (e) => <EntryState entry={e} /> },
    {
      key: 'order',
      header: 'Auftrag',
      render: (e) => <Link to={`/orders/${e.order_id}`}>Auftrag #{e.order_id}</Link>,
    },
    { key: 'activity', header: 'Aktivität', render: (e) => activityName(e.activity_id) },
    {
      key: 'notes',
      header: 'Notizen',
      hideBelow: 'desktop',
      render: (e) => <span className="time-entry-notes-clamp">{e.notes || '–'}</span>,
    },
    {
      key: 'action',
      header: 'Aktion',
      render: (e) =>
        e.end_time ? (
          <Button variant="ghost" icon="pencil" onClick={() => onEdit(e)}>
            Bearbeiten
          </Button>
        ) : (
          <Button variant="secondary" icon="clock" onClick={openTimer}>
            Timer öffnen
          </Button>
        ),
    },
  ];
}

const RunningTimerCard: React.FC<{ entry: RunningTimeEntry; activityName: string }> = ({
  entry,
  activityName,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const jobLabel = entry.order_title
    ? `Auftrag #${entry.order_id} – ${entry.order_title}`
    : `Auftrag #${entry.order_id}`;
  return (
    <Card title="Läuft gerade" tone={entry.is_paused ? 'waiting' : 'info'} className="time-running-card">
      <div className="time-running-card__body">
        <p className="time-running-card__order">
          {jobLabel} · {entry.activity_name ?? activityName}
          {entry.location ? ` · ${entry.location}` : ''}
        </p>
        {entry.is_paused && <StatusBadge kind="timeEntry" status="paused" size="lg" />}
        <Button size="lg" variant="secondary" icon="pencil" onClick={() => setIsEditing(true)}>
          Timer bearbeiten
        </Button>
        <Button size="lg" icon="clock" onClick={openTimer}>
          Timer öffnen
        </Button>
      </div>
      {isEditing && <RunningTimerEditSheet entry={entry} onClose={() => setIsEditing(false)} />}
    </Card>
  );
};

export const TimeTrackingPage: React.FC = () => {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const { showConfirm } = useConfirm();
  const { runningEntry, activities } = useTimeTracking();
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState<number>(TIME_ENTRY_PAGE_SIZE);
  const [sort, setSort] = useState<SortOrder>('-start_time');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<TimeEntry | null>(null);

  const params = { limit: pageSize, offset: pageIndex * pageSize, sort };
  const query = useQuery({ ...userEntriesQuery(userId ?? 0, params), enabled: userId !== null });

  const activityMap = useMemo(
    () => new Map<number, Activity>(activities.map((a) => [a.id, a])),
    [activities],
  );
  const activityName = (id: number) => activityMap.get(id)?.name ?? `Aktivität #${id}`;

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedEntry(null);
  };
  const { create, update, remove } = useEntryMutations(closeModal);

  const openEdit = (entry: TimeEntry) => {
    setSelectedEntry(entry);
    setIsModalOpen(true);
  };
  const openCreate = () => {
    setSelectedEntry(null);
    setIsModalOpen(true);
  };

  const handleSubmit = async (data: TimeEntryCreateInput | TimeEntryUpdateInput) => {
    if (selectedEntry) {
      // onError already shows the toast; the modal stays open for a retry.
      await update.mutateAsync({ id: selectedEntry.id, data }).catch(() => undefined);
    } else {
      await create.mutateAsync(data as TimeEntryCreateInput).catch(() => undefined);
    }
  };

  const handleDelete = async (entry: TimeEntry) => {
    const confirmed = await showConfirm({
      title: 'Zeiteintrag löschen',
      message: `Möchten Sie den Zeiteintrag vom ${formatDateTime(entry.start_time)} wirklich löschen?`,
      confirmLabel: 'Löschen',
      variant: 'danger',
    });
    if (confirmed) remove.mutate(entry.id);
  };

  const state: PageStateValue =
    userId === null || query.isPending
      ? { status: 'loading' }
      : query.isError && !query.data
        ? {
            status: 'error',
            error: getErrorMessage(query.error, 'Zeiteinträge konnten nicht geladen werden.'),
            retry: () => void query.refetch(),
          }
        : { status: query.data?.items.length ? 'ready' : 'empty' };
  const page = query.data;
  const { pageNumber, pageCount } = page ? pageInfo(page) : { pageNumber: 1, pageCount: 1 };

  return (
    <div className="page-container time-tracking-page">
      <PageHeader
        title="Zeiterfassung"
        meta={page ? `${page.total} Einträge` : undefined}
        primaryAction={
          <Button size="lg" icon="plus" onClick={openCreate}>
            Eintrag anlegen
          </Button>
        }
        secondaryActions={<BenchModeToggle />}
      />

      {runningEntry && (
        <RunningTimerCard entry={runningEntry} activityName={activityName(runningEntry.activity_id)} />
      )}

      <TimeSummaryCards />

      <section id="zeiteintraege" className="time-entries" aria-labelledby="time-entries-title">
        <div className="time-entries__header">
          <h2 id="time-entries-title">Zeiteinträge</h2>
          <div className="time-entries__controls">
            <label className="time-entries__control">
              Sortieren
              <select
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value as SortOrder);
                  setPageIndex(0);
                }}
              >
                <option value="-start_time">Neueste zuerst</option>
                <option value="start_time">Älteste zuerst</option>
              </select>
            </label>
            <label className="time-entries__control">
              Pro Seite
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPageIndex(0);
                }}
              >
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <DataTable
          rows={page?.items ?? []}
          columns={entryColumns(activityName, openEdit)}
          getRowKey={(e) => e.id}
          caption="Zeiteinträge"
          state={state}
          empty={{
            icon: 'clock',
            title: 'Noch keine Zeiteinträge',
            body: 'Starten Sie einen Timer oder tragen Sie eine Zeit nach.',
            action: (
              <Button size="lg" icon="plus" onClick={openCreate}>
                Eintrag anlegen
              </Button>
            ),
          }}
          cardTitle={(e) => `Auftrag #${e.order_id} · ${activityName(e.activity_id)}`}
          cardMeta={(e) => formatDateTime(e.start_time)}
          cardBadges={(e) => <EntryState entry={e} />}
        />

        {page && page.items.length > 0 && (
          <Pager
            label="Seiten der Zeiteinträge"
            pageNumber={pageNumber}
            pageCount={pageCount}
            summary={`${page.total} Einträge`}
            hasNext={page.next_offset != null}
            isFetching={query.isFetching}
            onPrevious={() => setPageIndex((index) => Math.max(index - 1, 0))}
            onNext={() => setPageIndex((index) => index + 1)}
          />
        )}
      </section>

      <TimeReportsSection />

      <TimeEntryFormModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onSubmit={handleSubmit}
        entry={selectedEntry}
        isLoading={create.isPending || update.isPending || remove.isPending}
        onDelete={(entry) => void handleDelete(entry)}
      />
    </div>
  );
};
