// Time Tracking Page Component
import React, { useEffect, useState } from 'react';
import { timeTrackingApi } from '../api';
import { TimeEntryType, TimeEntryCreateInput, TimeEntryUpdateInput, ActivityType } from '../types';
import { ActiveTimerWidget } from '../components/time-tracking/ActiveTimerWidget';
import { TimeSummaryCards } from '../components/time-tracking/TimeSummaryCards';
import { TimeReportsSection } from '../components/time-tracking/TimeReportsSection';
import { TimeEntryFormModal } from '../components/time-tracking/TimeEntryFormModal';
import '../styles/pages.css';
import '../styles/time-tracking.css';

export const TimeTrackingPage: React.FC = () => {
  const [entries, setEntries] = useState<TimeEntryType[]>([]);
  const [filteredEntries, setFilteredEntries] = useState<TimeEntryType[]>([]);
  const [activities, setActivities] = useState<ActivityType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isFormLoading, setIsFormLoading] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<TimeEntryType | null>(null);

  // Filters & Sort
  const [searchQuery, setSearchQuery] = useState('');
  const [filterActivity, setFilterActivity] = useState<number | ''>('');
  const [sortBy, setSortBy] = useState<'date' | 'duration'>('date');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  useEffect(() => {
    fetchEntries();
    fetchActivities();
  }, []);

  useEffect(() => {
    filterAndSortEntries();
  }, [entries, searchQuery, filterActivity, sortBy]);

  const fetchEntries = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await timeTrackingApi.getAll({ limit: 1000 });
      setEntries(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Zeiteinträge');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchActivities = async () => {
    try {
      const data = await timeTrackingApi.getAllActivities();
      setActivities(data);
    } catch (err: any) {
      console.error('Failed to fetch activities:', err);
    }
  };

  const filterAndSortEntries = () => {
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

    setFilteredEntries(filtered);
  };

  const handleCreateEntry = async (data: TimeEntryCreateInput) => {
    try {
      setIsFormLoading(true);
      await timeTrackingApi.create(data);
      await fetchEntries();
      setIsModalOpen(false);
      alert('Zeiterfassung erfolgreich erstellt!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Erstellen der Zeiterfassung');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleUpdateEntry = async (data: TimeEntryUpdateInput) => {
    if (!selectedEntry) return;

    try {
      setIsFormLoading(true);
      await timeTrackingApi.update(selectedEntry.id, data);
      await fetchEntries();
      setIsModalOpen(false);
      setSelectedEntry(null);
      alert('Zeiterfassung erfolgreich aktualisiert!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Aktualisieren der Zeiterfassung');
    } finally {
      setIsFormLoading(false);
    }
  };

  const handleDeleteEntry = async (entryId: string) => {
    const confirmed = window.confirm(
      'Möchten Sie diese Zeiterfassung wirklich löschen?'
    );

    if (!confirmed) return;

    try {
      await timeTrackingApi.delete(entryId);
      await fetchEntries();
      alert('Zeiterfassung erfolgreich gelöscht!');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Fehler beim Löschen der Zeiterfassung');
    }
  };

  const openCreateModal = () => {
    setSelectedEntry(null);
    setIsModalOpen(true);
  };

  const openEditModal = (entry: TimeEntryType, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedEntry(entry);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedEntry(null);
  };

  const handleFormSubmit = async (data: TimeEntryCreateInput | TimeEntryUpdateInput) => {
    if (selectedEntry) {
      await handleUpdateEntry(data);
    } else {
      await handleCreateEntry(data as TimeEntryCreateInput);
    }
  };

  const formatDate = (dateStr: string): string => {
    return new Date(dateStr).toLocaleString('de-DE', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDuration = (minutes: number | null): string => {
    if (minutes === null) return 'Läuft...';
    const hrs = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hrs}h ${mins}m`;
  };

  // Pagination
  const totalPages = Math.ceil(filteredEntries.length / pageSize);
  const paginatedEntries = filteredEntries.slice(
    page * pageSize,
    (page + 1) * pageSize
  );

  return (
    <div className="page-container">
      {/* Active Timer Widget */}
      <ActiveTimerWidget />

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
                  const activity = activities.find((a) => a.id === entry.activity_id);
                  const isRunning = !entry.end_time;

                  return (
                    <tr key={entry.id} className={isRunning ? 'running' : ''}>
                      <td>#{entry.id.slice(0, 8)}</td>
                      <td>{formatDate(entry.start_time)}</td>
                      <td>{entry.end_time ? formatDate(entry.end_time) : 'Läuft...'}</td>
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
