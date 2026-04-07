// Time Tracking Page Component - Optimized
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { timeTrackingApi, activitiesApi } from '../api';
import apiClient from '../api/client';
import { TimeEntry, TimeEntryStartInput, TimeEntryUpdateInput, Activity } from '../types';
// Timer handled by global FAB widget in MainLayout
import { TimeSummaryCards } from '../components/time-tracking/TimeSummaryCards';
import { TimeReportsSection } from '../components/time-tracking/TimeReportsSection';
import { TimeEntryFormModal } from '../components/time-tracking/TimeEntryFormModal';
import { formatDateTime, formatDuration as formatDurationUtil } from '../utils/formatters';
import { useToast, useConfirm } from '../contexts';
import '../styles/pages.css';
import '../styles/time-tracking.css';

// Helper function for duration formatting
const formatDuration = (minutes: number | null): string => {
  if (minutes === null) return 'Läuft...';
  return formatDurationUtil(minutes);
};

export const TimeTrackingPage: React.FC = () => {
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const [entries, setEntries] = useState<TimeEntry[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isFormLoading, setIsFormLoading] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<TimeEntry | null>(null);

  // Filters & Sort
  const [searchQuery, setSearchQuery] = useState('');
  const [filterActivity, setFilterActivity] = useState<number | ''>('');
  const [sortBy, setSortBy] = useState<'date' | 'duration'>('date');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  // Memoized fetch functions
  const fetchEntries = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      // Fetch current user's time entries via /users/me then /time-tracking/user/{id}
      const meResponse = await apiClient.get('/users/me');
      const userId = meResponse.data.id;
      const data = await timeTrackingApi.getForUser(userId);
      setEntries(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Zeiteinträge');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchActivities = useCallback(async () => {
    try {
      const data = await activitiesApi.getAll();
      setActivities(data);
    } catch (err: any) {
      console.error('Fehler beim Laden der Aktivitäten:', err);
      setActivities([]);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
    fetchActivities();
  }, [fetchEntries, fetchActivities]);

  // Create activity lookup map for O(1) performance
  const activityMap = useMemo(() => {
    const map = new Map<number, Activity>();
    activities.forEach(activity => map.set(activity.id, activity));
    return map;
  }, [activities]);

  // Replace useEffect with useMemo for better performance
  const filteredEntries = useMemo(() => {
    let filtered = [...entries];

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (e) =>
          e.id.toLowerCase().includes(query) ||
          (e.notes && e.notes.toLowerCase().includes(query)) ||
          (e.order && e.order.title.toLowerCase().includes(query))
      );
    }

    // Activity filter
    if (filterActivity) {
      filtered = filtered.filter((e) => e.activity_id === filterActivity);
    }

    // Sort
    filtered.sort((a, b) => {
      if (sortBy === 'date') {
        return new Date(b.start_time).getTime() - new Date(a.start_time).getTime();
      } else if (sortBy === 'duration') {
        return (b.duration_minutes || 0) - (a.duration_minutes || 0);
      }
      return 0;
    });

    return filtered;
  }, [entries, searchQuery, filterActivity, sortBy]);

  // Memoized pagination calculations
  const totalPages = useMemo(() => Math.ceil(filteredEntries.length / pageSize), [filteredEntries.length, pageSize]);
  const paginatedEntries = useMemo(
    () => filteredEntries.slice(page * pageSize, (page + 1) * pageSize),
    [filteredEntries, page, pageSize]
  );

  // Memoized event handlers
  const handleCreateEntry = useCallback(async (data: TimeEntryCreateInput) => {
    try {
      setIsFormLoading(true);
      await timeTrackingApi.create(data);
      await fetchEntries();
      setIsModalOpen(false);
      showToast('Zeiterfassung erfolgreich erstellt!', 'success');
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Erstellen der Zeiterfassung', 'error');
    } finally {
      setIsFormLoading(false);
    }
  }, [fetchEntries]);

  const handleUpdateEntry = useCallback(async (data: TimeEntryUpdateInput) => {
    if (!selectedEntry) return;

    try {
      setIsFormLoading(true);
      await timeTrackingApi.update(selectedEntry.id, data);
      await fetchEntries();
      setIsModalOpen(false);
      setSelectedEntry(null);
      showToast('Zeiterfassung erfolgreich aktualisiert!', 'success');
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Aktualisieren der Zeiterfassung', 'error');
    } finally {
      setIsFormLoading(false);
    }
  }, [selectedEntry, fetchEntries]);

  const handleDeleteEntry = useCallback(async (entryId: string) => {
    const confirmed = await showConfirm({
      title: 'Zeiteintrag loschen',
      message: 'Mochten Sie diese Zeiterfassung wirklich loschen?',
      confirmLabel: 'Loschen',
      variant: 'danger',
    });

    if (!confirmed) return;

    try {
      await timeTrackingApi.delete(entryId);
      await fetchEntries();
      showToast('Zeiterfassung erfolgreich geloscht!', 'success');
    } catch (err: any) {
      showToast(err.response?.data?.detail || 'Fehler beim Loschen der Zeiterfassung', 'error');
    }
  }, [fetchEntries, showConfirm, showToast]);

  const openCreateModal = useCallback(() => {
    setSelectedEntry(null);
    setIsModalOpen(true);
  }, []);

  const openEditModal = useCallback((entry: TimeEntry, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedEntry(entry);
    setIsModalOpen(true);
  }, []);

  const closeModal = useCallback(() => {
    setIsModalOpen(false);
    setSelectedEntry(null);
  }, []);

  const handleFormSubmit = useCallback(async (data: TimeEntryCreateInput | TimeEntryUpdateInput) => {
    if (selectedEntry) {
      await handleUpdateEntry(data);
    } else {
      await handleCreateEntry(data as TimeEntryCreateInput);
    }
  }, [selectedEntry, handleUpdateEntry, handleCreateEntry]);

  return (
    <div className="page-container">
      {/* Timer is handled by the global FAB widget in MainLayout */}

      {/* Summary Cards */}
      <TimeSummaryCards />

      {/* Reports Section */}
      <TimeReportsSection />

      {/* Page Header */}
      <header className="page-header">
        <div>
          <h1>Zeiteinträge</h1>
          <p style={{ color: '#666', margin: '0.5rem 0 0 0' }}>
            {filteredEntries.length} Einträge
          </p>
        </div>
        <button className="btn-primary" onClick={openCreateModal}>
          + Manueller Eintrag
        </button>
      </header>

      {/* Search and Filters */}
      <div className="time-tracking-controls">
        <div className="search-box">
          <input
            type="text"
            placeholder="Suche nach ID, Auftrag oder Notizen..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <label>Aktivität:</label>
          <select
            value={filterActivity}
            onChange={(e) => setFilterActivity(Number(e.target.value) || '')}
          >
            <option value="">Alle</option>
            {activities.map((activity) => (
              <option key={activity.id} value={activity.id}>
                {activity.icon && `${activity.icon} `}
                {activity.name}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>Sortieren:</label>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value as 'date' | 'duration')}>
            <option value="date">Datum</option>
            <option value="duration">Dauer</option>
          </select>
        </div>

        <div className="filter-group">
          <label>Pro Seite:</label>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPage(0);
            }}
          >
            <option value="25">25</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="page-loading">Lade Zeiteinträge...</div>
      ) : error ? (
        <div className="page-error">{error}</div>
      ) : filteredEntries.length === 0 ? (
        <div className="empty-state">
          <p>
            {searchQuery || filterActivity
              ? 'Keine Zeiteinträge gefunden.'
              : 'Keine Zeiteinträge vorhanden.'}
          </p>
        </div>
      ) : (
        <>
          <div className="table-container">
            <table className="time-entries-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Startzeit</th>
                  <th>Endzeit</th>
                  <th>Dauer</th>
                  <th>Auftrag</th>
                  <th>Aktivität</th>
                  <th>Standort</th>
                  <th>Notizen</th>
                  <th>Aktionen</th>
                </tr>
              </thead>
              <tbody>
                {paginatedEntries.map((entry) => {
                  const activity = activityMap.get(entry.activity_id);
                  const isRunning = !entry.end_time;

                  return (
                    <tr key={entry.id} className={isRunning ? 'running' : ''}>
                      <td>#{entry.id.slice(0, 8)}</td>
                      <td>{formatDateTime(entry.start_time)}</td>
                      <td>{entry.end_time ? formatDateTime(entry.end_time) : 'Läuft...'}</td>
                      <td>
                        <span className={`duration-badge ${isRunning ? 'running' : ''}`}>
                          {formatDuration(entry.duration_minutes)}
                        </span>
                      </td>
                      <td>
                        {entry.order ? (
                          <span>
                            #{entry.order.id} - {entry.order.title}
                          </span>
                        ) : (
                          `#${entry.order_id}`
                        )}
                      </td>
                      <td>
                        {activity && (
                          <span className="activity-badge">
                            {activity.icon && `${activity.icon} `}
                            {activity.name}
                          </span>
                        )}
                      </td>
                      <td>{entry.location || '-'}</td>
                      <td className="notes-cell">
                        {entry.notes ? (
                          <span title={entry.notes}>
                            {entry.notes.length > 30
                              ? `${entry.notes.slice(0, 30)}...`
                              : entry.notes}
                          </span>
                        ) : (
                          '-'
                        )}
                      </td>
                      <td>
                        <div className="time-page-actions">
                          <button
                            className="btn-icon btn-edit"
                            onClick={(e) => openEditModal(entry, e)}
                            title="Bearbeiten"
                            disabled={isRunning}
                          >
                            ✏️
                          </button>
                          <button
                            className="btn-icon btn-delete"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteEntry(entry.id);
                            }}
                            title="Löschen"
                            disabled={isRunning}
                          >
                            🗑️
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination-controls">
              <div className="pagination-info">
                Seite {page + 1} von {totalPages} • {filteredEntries.length} Einträge
              </div>
              <div className="pagination-buttons">
                <button onClick={() => setPage(0)} disabled={page === 0}>
                  ‹‹ Erste
                </button>
                <button onClick={() => setPage(page - 1)} disabled={page === 0}>
                  ‹ Zurück
                </button>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={page >= totalPages - 1}
                >
                  Weiter ›
                </button>
                <button
                  onClick={() => setPage(totalPages - 1)}
                  disabled={page >= totalPages - 1}
                >
                  Letzte ››
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Time Entry Form Modal */}
      <TimeEntryFormModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onSubmit={handleFormSubmit}
        entry={selectedEntry}
        isLoading={isFormLoading}
      />
    </div>
  );
};
