import React, { useState, useEffect } from 'react';
import { Activity, ActivityCategory } from '../types';
import { activitiesApi } from '../api/activities';
import '../styles/components/ActivityPicker.css';

interface ActivityPickerProps {
  onSelectActivity: (activity: Activity) => void;
  onCancel?: () => void;
  showTopActivities?: boolean;
}

const ActivityPicker: React.FC<ActivityPickerProps> = ({
  onSelectActivity,
  onCancel,
  showTopActivities = true,
}) => {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [topActivities, setTopActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<ActivityCategory | 'all'>('all');

  useEffect(() => {
    loadActivities();
  }, []);

  const loadActivities = async () => {
    try {
      setLoading(true);
      setError(null);

      // Load all activities and top activities in parallel
      const [allActivities, mostUsed] = await Promise.all([
        activitiesApi.getAll({ sortByUsage: true }),
        showTopActivities ? activitiesApi.getMostUsed(5) : Promise.resolve([]),
      ]);

      setActivities(allActivities);
      setTopActivities(mostUsed);
    } catch (err) {
      console.error('Failed to load activities:', err);
      setError('Aktivitäten konnten nicht geladen werden');
    } finally {
      setLoading(false);
    }
  };

  const formatDuration = (minutes: number | null | undefined): string => {
    if (!minutes) return '-';
    if (minutes < 60) return `${Math.round(minutes)}min`;
    const hours = Math.floor(minutes / 60);
    const mins = Math.round(minutes % 60);
    return `${hours}h ${mins}min`;
  };

  const getCategoryLabel = (category: ActivityCategory): string => {
    const labels: Record<ActivityCategory, string> = {
      fabrication: '🔨 Fertigung',
      administration: '📋 Verwaltung',
      waiting: '⏳ Warten',
    };
    return labels[category];
  };

  const filteredActivities = activities.filter((activity) => {
    const matchesSearch =
      activity.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory =
      selectedCategory === 'all' || activity.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  // Group activities by category
  const groupedActivities: Record<ActivityCategory, Activity[]> = {
    fabrication: [],
    administration: [],
    waiting: [],
  };

  filteredActivities.forEach((activity) => {
    groupedActivities[activity.category].push(activity);
  });

  if (loading) {
    return (
      <div className="activity-picker">
        <div className="activity-picker-loading">Aktivitäten werden geladen...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="activity-picker">
        <div className="activity-picker-error">
          {error}
          <button onClick={loadActivities} className="retry-button">
            Erneut versuchen
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="activity-picker">
      <div className="activity-picker-header">
        <h2>Aktivität auswählen</h2>
        {onCancel && (
          <button onClick={onCancel} className="close-button">
            ✕
          </button>
        )}
      </div>

      {/* Search and Filter */}
      <div className="activity-picker-controls">
        <input
          type="text"
          placeholder="Aktivität suchen..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="activity-search-input"
        />

        <div className="category-filters">
          <button
            onClick={() => setSelectedCategory('all')}
            className={`category-filter ${selectedCategory === 'all' ? 'active' : ''}`}
          >
            Alle
          </button>
          <button
            onClick={() => setSelectedCategory('fabrication')}
            className={`category-filter ${selectedCategory === 'fabrication' ? 'active' : ''}`}
          >
            🔨 Fertigung
          </button>
          <button
            onClick={() => setSelectedCategory('administration')}
            className={`category-filter ${selectedCategory === 'administration' ? 'active' : ''}`}
          >
            📋 Verwaltung
          </button>
          <button
            onClick={() => setSelectedCategory('waiting')}
            className={`category-filter ${selectedCategory === 'waiting' ? 'active' : ''}`}
          >
            ⏳ Warten
          </button>
        </div>
      </div>

      {/* Top Activities (Most Used) */}
      {showTopActivities && topActivities.length > 0 && !searchQuery && selectedCategory === 'all' && (
        <div className="top-activities">
          <h3>⭐ Häufig verwendet</h3>
          <div className="activity-grid">
            {topActivities.map((activity) => (
              <button
                key={activity.id}
                onClick={() => onSelectActivity(activity)}
                className="activity-card activity-card-top"
                style={{ borderLeftColor: activity.color || '#3b82f6' }}
              >
                <div className="activity-card-icon">
                  {activity.icon || '📌'}
                </div>
                <div className="activity-card-content">
                  <div className="activity-card-name">{activity.name}</div>
                  <div className="activity-card-meta">
                    <span className="activity-usage-count">
                      {activity.usage_count}x verwendet
                    </span>
                    {activity.average_duration_minutes && (
                      <span className="activity-duration">
                        ⏱ {formatDuration(activity.average_duration_minutes)}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* All Activities (Grouped by Category) */}
      <div className="activities-list">
        {(Object.keys(groupedActivities) as ActivityCategory[]).map((category) => {
          const categoryActivities = groupedActivities[category];

          if (categoryActivities.length === 0) return null;

          return (
            <div key={category} className="activity-category">
              <h3 className="category-header">{getCategoryLabel(category)}</h3>
              <div className="activity-grid">
                {categoryActivities.map((activity) => (
                  <button
                    key={activity.id}
                    onClick={() => onSelectActivity(activity)}
                    className="activity-card"
                    style={{ borderLeftColor: activity.color || '#3b82f6' }}
                  >
                    <div className="activity-card-icon">
                      {activity.icon || '📌'}
                    </div>
                    <div className="activity-card-content">
                      <div className="activity-card-name">{activity.name}</div>
                      <div className="activity-card-meta">
                        {activity.usage_count > 0 && (
                          <span className="activity-usage-count">
                            {activity.usage_count}x
                          </span>
                        )}
                        {activity.average_duration_minutes && (
                          <span className="activity-duration">
                            ⏱ {formatDuration(activity.average_duration_minutes)}
                          </span>
                        )}
                        {activity.is_custom && (
                          <span className="activity-custom-badge">Custom</span>
                        )}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {filteredActivities.length === 0 && (
        <div className="activity-picker-empty">
          Keine Aktivitäten gefunden.
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="clear-search-button"
            >
              Suche zurücksetzen
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default ActivityPicker;
