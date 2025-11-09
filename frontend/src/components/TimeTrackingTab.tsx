// Time Tracking Tab Component - Shows time entries for an order
import React, { useState, useEffect } from 'react';
import { timeTrackingApi } from '../api/timeTracking';
import { activitiesApi } from '../api/activities';
import { TimeEntry, TimeTrackingStats, Activity } from '../types';
import ActivityPicker from './ActivityPicker';
import { useTimeTracking } from '../contexts';
import '../styles/components/TimeTrackingTab.css';

interface TimeTrackingTabProps {
  orderId: number;
}

const TimeTrackingTab: React.FC<TimeTrackingTabProps> = ({ orderId }) => {
  const { startTracking } = useTimeTracking();
  const [entries, setEntries] = useState<TimeEntry[]>([]);
  const [stats, setStats] = useState<TimeTrackingStats | null>(null);
  const [activities, setActivities] = useState<Map<number, Activity>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showActivityPicker, setShowActivityPicker] = useState(false);

  // Load data on mount and when orderId changes
  useEffect(() => {
    loadTimeEntries();
  }, [orderId]);

  const loadTimeEntries = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Fetch time entries and stats in parallel
      const [entriesData, statsData, activitiesData] = await Promise.all([
        timeTrackingApi.getForOrder(orderId),
        timeTrackingApi.getTotalForOrder(orderId),
        activitiesApi.getAll(),
      ]);

      setEntries(entriesData);
      setStats(statsData);

      // Create activities map for quick lookup
      const activityMap = new Map<number, Activity>();
      activitiesData.forEach((activity) => {
        activityMap.set(activity.id, activity);
      });
      setActivities(activityMap);
    } catch (err) {
      console.error('Failed to load time entries:', err);
      setError('Zeiteinträge konnten nicht geladen werden');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartTracking = async (activity: Activity) => {
    try {
      await startTracking(orderId, activity.id);
      setShowActivityPicker(false);
      // Refresh entries to show new entry
      await loadTimeEntries();
    } catch (err) {
      console.error('Failed to start tracking:', err);
      alert('Zeiterfassung konnte nicht gestartet werden');
    }
  };

  const formatDuration = (minutes: number | null | undefined): string => {
    if (!minutes) return '-';
    const hours = Math.floor(minutes / 60);
    const mins = Math.round(minutes % 60);
    return `${hours}h ${mins}m`;
  };

  const formatDateTime = (dateStr: string): string => {
    const date = new Date(dateStr);
    return date.toLocaleString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const renderStars = (rating: number | null | undefined): JSX.Element => {
    if (!rating) return <span className="no-rating">-</span>;
    return (
      <div className="star-display">
        {[1, 2, 3, 4, 5].map((star) => (
          <span key={star} className={`star ${star <= rating ? 'filled' : ''}`}>
            ★
          </span>
        ))}
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="time-tracking-tab">
        <div className="loading-message">
          <div className="spinner"></div>
          <p>Lade Zeiteinträge...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="time-tracking-tab">
        <div className="error-message">
          <p>{error}</p>
          <button onClick={loadTimeEntries} className="btn-retry">
            Erneut versuchen
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="time-tracking-tab">
      <div className="tab-header">
        <h2>⏱️ Zeiterfassung</h2>
        <button
          onClick={() => setShowActivityPicker(true)}
          className="btn-start-tracking"
        >
          + Zeit erfassen starten
        </button>
      </div>

      {/* Statistics Summary */}
      {stats && (
        <div className="time-stats-summary">
          <div className="stat-card stat-total">
            <div className="stat-icon">⏱️</div>
            <div className="stat-content">
              <div className="stat-label">Gesamtzeit</div>
              <div className="stat-value">{formatDuration(stats.total_duration_minutes)}</div>
            </div>
          </div>

          <div className="stat-card stat-entries">
            <div className="stat-icon">📊</div>
            <div className="stat-content">
              <div className="stat-label">Einträge</div>
              <div className="stat-value">{stats.entry_count}</div>
            </div>
          </div>

          <div className="stat-card stat-complexity">
            <div className="stat-icon">🎯</div>
            <div className="stat-content">
              <div className="stat-label">Ø Komplexität</div>
              <div className="stat-value">
                {stats.average_complexity ? stats.average_complexity.toFixed(1) : '-'}
              </div>
            </div>
          </div>

          <div className="stat-card stat-quality">
            <div className="stat-icon">✨</div>
            <div className="stat-content">
              <div className="stat-label">Ø Qualität</div>
              <div className="stat-value">
                {stats.average_quality ? stats.average_quality.toFixed(1) : '-'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Activity Breakdown */}
      {stats?.by_activity && Object.keys(stats.by_activity).length > 0 && (
        <div className="activity-breakdown">
          <h3>Zeit pro Aktivität</h3>
          <div className="activity-breakdown-list">
            {Object.entries(stats.by_activity)
              .sort(([, a], [, b]) => b - a) // Sort by duration descending
              .map(([activityName, minutes]) => {
                const percentage = stats.total_duration_minutes
                  ? (minutes / stats.total_duration_minutes) * 100
                  : 0;
                return (
                  <div key={activityName} className="activity-breakdown-item">
                    <div className="activity-breakdown-header">
                      <span className="activity-name">{activityName}</span>
                      <span className="activity-duration">{formatDuration(minutes)}</span>
                    </div>
                    <div className="activity-breakdown-bar">
                      <div
                        className="activity-breakdown-fill"
                        style={{ width: `${percentage}%` }}
                      ></div>
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Time Entries List */}
      <div className="time-entries-section">
        <h3>Alle Zeiteinträge ({entries.length})</h3>

        {entries.length === 0 ? (
          <div className="no-entries-message">
            <p>Noch keine Zeiteinträge für diesen Auftrag.</p>
            <p className="hint">Klicken Sie auf "Zeit erfassen starten" um zu beginnen.</p>
          </div>
        ) : (
          <div className="time-entries-list">
            {entries.map((entry) => {
              const activity = activities.get(entry.activity_id);
              const isRunning = !entry.end_time;

              return (
                <div key={entry.id} className={`time-entry-card ${isRunning ? 'running' : ''}`}>
                  <div className="entry-header">
                    <div className="entry-activity">
                      {activity?.icon && (
                        <span className="activity-icon">{activity.icon}</span>
                      )}
                      <span className="activity-name">
                        {activity?.name || 'Unbekannte Aktivität'}
                      </span>
                      {isRunning && <span className="running-badge">Läuft</span>}
                    </div>
                    <div className="entry-duration">
                      {formatDuration(entry.duration_minutes)}
                    </div>
                  </div>

                  <div className="entry-details">
                    <div className="entry-detail-row">
                      <span className="detail-label">Start:</span>
                      <span className="detail-value">{formatDateTime(entry.start_time)}</span>
                    </div>
                    {entry.end_time && (
                      <div className="entry-detail-row">
                        <span className="detail-label">Ende:</span>
                        <span className="detail-value">{formatDateTime(entry.end_time)}</span>
                      </div>
                    )}
                    {entry.location && (
                      <div className="entry-detail-row">
                        <span className="detail-label">Ort:</span>
                        <span className="detail-value">{entry.location}</span>
                      </div>
                    )}
                  </div>

                  {!isRunning && (entry.complexity_rating || entry.quality_rating) && (
                    <div className="entry-ratings">
                      {entry.complexity_rating && (
                        <div className="rating-item">
                          <span className="rating-label">Komplexität:</span>
                          {renderStars(entry.complexity_rating)}
                        </div>
                      )}
                      {entry.quality_rating && (
                        <div className="rating-item">
                          <span className="rating-label">Qualität:</span>
                          {renderStars(entry.quality_rating)}
                        </div>
                      )}
                    </div>
                  )}

                  {entry.rework_required && (
                    <div className="entry-rework-badge">
                      ⚠️ Nacharbeit erforderlich
                    </div>
                  )}

                  {entry.notes && (
                    <div className="entry-notes">
                      <strong>Notizen:</strong> {entry.notes}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Activity Picker Modal */}
      {showActivityPicker && (
        <div className="modal-overlay" onClick={() => setShowActivityPicker(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <ActivityPicker
              onSelectActivity={handleStartTracking}
              onCancel={() => setShowActivityPicker(false)}
              showTopActivities={true}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default TimeTrackingTab;
