// ActivityPicker (W4-03, bench mode): pick the activity for a timer.
//
// Data: activitiesQuery(true) (sorted by usage) and mostUsedActivitiesQuery
// from api/timeTrackingQueries.ts, shared with TimeTrackingContext, so the
// picker opens from cache. Every activity is one 56px tap target; the
// most-used ones come first. Category filters are pressed-state buttons.
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { activitiesQuery, mostUsedActivitiesQuery } from '../api/timeTrackingQueries';
import { Button, EmptyState, Field, IconButton, PageState, type PageStateValue } from '../ui';
import { Activity, ActivityCategory } from '../types';
import '../styles/components/ActivityPicker.css';

interface ActivityPickerProps {
  onSelectActivity: (activity: Activity) => void;
  onCancel?: () => void;
  showTopActivities?: boolean;
}

const CATEGORY_LABELS: Readonly<Record<ActivityCategory, string>> = {
  fabrication: 'Fertigung',
  administration: 'Verwaltung',
  waiting: 'Warten',
};
const CATEGORIES = Object.keys(CATEGORY_LABELS) as ActivityCategory[];

function formatDuration(minutes: number | null | undefined): string {
  if (!minutes) return '–';
  if (minutes < 60) return `${Math.round(minutes)} min`;
  return `${Math.floor(minutes / 60)} h ${Math.round(minutes % 60)} min`;
}

interface ActivityCardProps {
  activity: Activity;
  isTop?: boolean;
  onSelect: (activity: Activity) => void;
}

const ActivityCard: React.FC<ActivityCardProps> = ({ activity, isTop = false, onSelect }) => (
  <button
    type="button"
    onClick={() => onSelect(activity)}
    className={`activity-card ${isTop ? 'activity-card-top' : ''}`}
    // Runtime value: the colour the workshop chose for this activity.
    style={activity.color ? { borderInlineStartColor: activity.color } : undefined}
  >
    {activity.icon && (
      <span className="activity-card-icon" aria-hidden="true">
        {activity.icon}
      </span>
    )}
    <span className="activity-card-content">
      <span className="activity-card-name">{activity.name}</span>
      <span className="activity-card-meta">
        {(isTop || activity.usage_count > 0) && (
          <span>{isTop ? `${activity.usage_count}× verwendet` : `${activity.usage_count}×`}</span>
        )}
        {activity.average_duration_minutes ? (
          <span>Ø {formatDuration(activity.average_duration_minutes)}</span>
        ) : null}
        {activity.is_custom && <span className="activity-custom-badge">Eigene</span>}
      </span>
    </span>
  </button>
);

const ActivityPicker: React.FC<ActivityPickerProps> = ({
  onSelectActivity,
  onCancel,
  showTopActivities = true,
}) => {
  const all = useQuery(activitiesQuery(true));
  const top = useQuery({ ...mostUsedActivitiesQuery(), enabled: showTopActivities });
  const [searchQuery, setSearchQuery] = useState('');
  const [category, setCategory] = useState<ActivityCategory | 'all'>('all');

  const needle = searchQuery.trim().toLowerCase();
  const filtered = (all.data ?? []).filter(
    (a) => a.name.toLowerCase().includes(needle) && (category === 'all' || a.category === category),
  );
  const topActivities = showTopActivities ? top.data ?? [] : [];
  const showTop = topActivities.length > 0 && !needle && category === 'all';

  const state: PageStateValue = all.isError
      ? {
          status: 'error',
          error: 'Aktivitäten konnten nicht geladen werden',
          retry: () => void all.refetch(),
        }
      : { status: 'ready' };

  return (
    <div className="activity-picker">
      <div className="activity-picker-header">
        <h2>Aktivität auswählen</h2>
        {onCancel && <IconButton icon="close" label="Schließen" size="lg" onClick={onCancel} />}
      </div>

      {all.isPending ? (
        <p className="activity-picker-loading" role="status">
          Aktivitäten werden geladen…
        </p>
      ) : (
        <PageState state={state}>
          <div className="activity-picker-controls">
            <Field label="Aktivität suchen" name="activity-search" inputMode="search">
              <input type="search" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
            </Field>
            <div className="category-filters" role="group" aria-label="Kategorie">
              {(['all', ...CATEGORIES] as const).map((id) => (
                <Button
                  key={id}
                  variant={category === id ? 'primary' : 'secondary'}
                  size="lg"
                  aria-pressed={category === id}
                  className={category === id ? 'active' : undefined}
                  onClick={() => setCategory(id)}
                >
                  {id === 'all' ? 'Alle' : CATEGORY_LABELS[id]}
                </Button>
              ))}
            </div>
          </div>

          {showTop && (
            <section className="top-activities" aria-label="Häufig verwendet">
              <h3>Häufig verwendet</h3>
              <div className="activity-grid">
                {topActivities.map((activity) => (
                  <ActivityCard key={activity.id} activity={activity} isTop onSelect={onSelectActivity} />
                ))}
              </div>
            </section>
          )}

          <div className="activities-list">
            {CATEGORIES.map((cat) => {
              const items = filtered.filter((a) => a.category === cat);
              if (items.length === 0) return null;
              return (
                <section key={cat} className="activity-category" aria-label={CATEGORY_LABELS[cat]}>
                  <h3 className="category-header">{CATEGORY_LABELS[cat]}</h3>
                  <div className="activity-grid">
                    {items.map((activity) => (
                      <ActivityCard key={activity.id} activity={activity} onSelect={onSelectActivity} />
                    ))}
                  </div>
                </section>
              );
            })}
          </div>

          {all.isSuccess && filtered.length === 0 && (
            <EmptyState
              icon="search"
              title="Keine Aktivitäten gefunden."
              headingLevel={3}
              action={
                needle || category !== 'all' ? (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setSearchQuery('');
                      setCategory('all');
                    }}
                  >
                    Suche zurücksetzen
                  </Button>
                ) : undefined
              }
            />
          )}
        </PageState>
      )}
    </div>
  );
};

export default ActivityPicker;
