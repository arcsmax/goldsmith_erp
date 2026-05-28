// Time Reports Section Component with Recharts
import React, { useEffect, useState } from 'react';
import { timeTrackingApi, activitiesApi } from '../../api';
import apiClient from '../../api/client';
import { TimeEntry, Activity, ActivityBreakdownData } from '../../types';
import { parseUTC } from '../../utils/formatters';
import { format, subDays, startOfWeek, getDay } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import '../../styles/time-tracking.css';

type ChartType = 'weekly' | 'activity' | 'daily';

const CHART_COLORS = [
  '#3498db', // Blue
  '#2ecc71', // Green
  '#e74c3c', // Red
  '#f39c12', // Orange
  '#9b59b6', // Purple
  '#1abc9c', // Turquoise
  '#34495e', // Dark Gray
  '#e67e22', // Carrot
];

export const TimeReportsSection: React.FC = () => {
  const [activeChart, setActiveChart] = useState<ChartType>('weekly');
  const [weeklyData, setWeeklyData] = useState<any[]>([]);
  const [activityData, setActivityData] = useState<ActivityBreakdownData[]>([]);
  const [dailyData, setDailyData] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAllChartData();
  }, []);

  const fetchAllChartData = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Get current user ID and their entries
      const meResponse = await apiClient.get('/users/me');
      const userId = meResponse.data.id;
      const entries: TimeEntry[] = await timeTrackingApi.getForUser(userId);
      const allActivities: Activity[] = await activitiesApi.getAll();
      const activityMap = new Map(allActivities.map(a => [a.id, a]));

      // Only use completed entries with duration
      const completed = entries.filter(e => e.end_time && e.duration_minutes);

      // --- Weekly trend (last 4 weeks) ---
      const weekBuckets = new Map<string, { hours: number; entries: number }>();
      for (let i = 3; i >= 0; i--) {
        const weekStart = startOfWeek(subDays(new Date(), i * 7), { weekStartsOn: 1 });
        const key = format(weekStart, 'dd.MM');
        weekBuckets.set(key, { hours: 0, entries: 0 });
      }
      for (const e of completed) {
        const entryDate = parseUTC(e.start_time);
        const weekStart = startOfWeek(entryDate, { weekStartsOn: 1 });
        const key = format(weekStart, 'dd.MM');
        const bucket = weekBuckets.get(key);
        if (bucket) {
          bucket.hours += (e.duration_minutes || 0) / 60;
          bucket.entries += 1;
        }
      }
      setWeeklyData(
        Array.from(weekBuckets.entries()).map(([week, data]) => ({
          week,
          hours: parseFloat(data.hours.toFixed(1)),
          entries: data.entries,
        }))
      );

      // --- Activity breakdown (last 30 days) ---
      const thirtyDaysAgo = subDays(new Date(), 30);
      const actHours = new Map<number, number>();
      let totalMinutes = 0;
      for (const e of completed) {
        if (parseUTC(e.start_time) >= thirtyDaysAgo) {
          const mins = e.duration_minutes || 0;
          actHours.set(e.activity_id, (actHours.get(e.activity_id) || 0) + mins);
          totalMinutes += mins;
        }
      }
      const actBreakdown = Array.from(actHours.entries()).map(([actId, mins]) => {
        const act = activityMap.get(actId);
        return {
          activity_name: act ? `${act.icon || ''} ${act.name}`.trim() : `Aktivität #${actId}`,
          hours: parseFloat((mins / 60).toFixed(1)),
          percentage: totalMinutes > 0 ? (mins / totalMinutes) * 100 : 0,
          color: act?.color || '#8884d8',
        };
      }).sort((a, b) => b.hours - a.hours);
      setActivityData(actBreakdown);

      // --- Daily distribution (average hours per weekday) ---
      const dayNames = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
      const dayTotals = new Array(7).fill(0);
      const dayCounts = new Array(7).fill(0);
      const seenWeekDays = new Set<string>();
      for (const e of completed) {
        if (parseUTC(e.start_time) >= thirtyDaysAgo) {
          const d = parseUTC(e.start_time);
          const dayIdx = getDay(d); // 0=Sun
          dayTotals[dayIdx] += (e.duration_minutes || 0) / 60;
          const weekKey = `${dayIdx}-${format(d, 'yyyy-ww')}`;
          if (!seenWeekDays.has(weekKey)) {
            seenWeekDays.add(weekKey);
            dayCounts[dayIdx] += 1;
          }
        }
      }
      // Start from Monday
      const orderedDays = [1, 2, 3, 4, 5, 6, 0];
      setDailyData(
        orderedDays.map(i => ({
          day: dayNames[i],
          hours: parseFloat((dayCounts[i] > 0 ? dayTotals[i] / dayCounts[i] : 0).toFixed(1)),
        }))
      );

    } catch (err: any) {
      console.error('Failed to compute reports:', err);
      setError('Berichte konnten nicht geladen werden');
    } finally {
      setIsLoading(false);
    }
  };

  const renderWeeklyChart = () => (
    <ResponsiveContainer width="100%" height={350}>
      <LineChart data={weeklyData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
        <XAxis dataKey="week" stroke="#666" />
        <YAxis stroke="#666" label={{ value: 'Stunden', angle: -90, position: 'insideLeft' }} />
        <Tooltip
          contentStyle={{ background: '#fff', border: '1px solid #ccc', borderRadius: '8px' }}
          labelStyle={{ fontWeight: 'bold' }}
        />
        <Legend />
        <Line
          type="monotone"
          dataKey="hours"
          name="Stunden"
          stroke="#3498db"
          strokeWidth={3}
          dot={{ fill: '#3498db', r: 5 }}
          activeDot={{ r: 7 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );

  const renderActivityChart = () => (
    <ResponsiveContainer width="100%" height={350}>
      <PieChart>
        <Pie
          data={activityData}
          cx="50%"
          cy="50%"
          labelLine={false}
          label={(entry) => {
            const d = entry as unknown as ActivityBreakdownData;
            return `${d.activity_name}: ${d.percentage.toFixed(1)}%`;
          }}
          outerRadius={120}
          fill="#8884d8"
          dataKey="hours"
        >
          {activityData.map((entry, index) => (
            <Cell
              key={`cell-${index}`}
              fill={entry.color || CHART_COLORS[index % CHART_COLORS.length]}
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ background: '#fff', border: '1px solid #ccc', borderRadius: '8px' }}
          formatter={(value: any) => `${parseFloat(value).toFixed(1)}h`}
        />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );

  const renderDailyChart = () => (
    <ResponsiveContainer width="100%" height={350}>
      <BarChart data={dailyData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
        <XAxis dataKey="day" stroke="#666" />
        <YAxis stroke="#666" label={{ value: 'Stunden', angle: -90, position: 'insideLeft' }} />
        <Tooltip
          contentStyle={{ background: '#fff', border: '1px solid #ccc', borderRadius: '8px' }}
          formatter={(value: any) => `${value}h`}
        />
        <Legend />
        <Bar dataKey="hours" name="Stunden" fill="#2ecc71" />
      </BarChart>
    </ResponsiveContainer>
  );

  if (isLoading) {
    return <div className="time-reports-loading">Lade Berichte...</div>;
  }

  if (error) {
    return <div className="time-reports-error">❌ {error}</div>;
  }

  return (
    <div className="time-reports-container">
      <div className="time-reports-header">
        <h2>Berichte & Analysen</h2>
        <div className="chart-selector">
          <button
            className={`chart-btn ${activeChart === 'weekly' ? 'active' : ''}`}
            onClick={() => setActiveChart('weekly')}
          >
            📈 Wochenverlauf
          </button>
          <button
            className={`chart-btn ${activeChart === 'activity' ? 'active' : ''}`}
            onClick={() => setActiveChart('activity')}
          >
            🎯 Aktivitäten
          </button>
          <button
            className={`chart-btn ${activeChart === 'daily' ? 'active' : ''}`}
            onClick={() => setActiveChart('daily')}
          >
            📊 Tagesverteilung
          </button>
        </div>
      </div>

      <div className="chart-container">
        {activeChart === 'weekly' && (
          <div className="chart-wrapper">
            <h3>Stundenverlauf (letzte 4 Wochen)</h3>
            {weeklyData.length > 0 ? (
              renderWeeklyChart()
            ) : (
              <div className="chart-empty">Keine Daten für Wochenverlauf vorhanden</div>
            )}
          </div>
        )}

        {activeChart === 'activity' && (
          <div className="chart-wrapper">
            <h3>Zeitverteilung nach Aktivität (letzte 30 Tage)</h3>
            {activityData.length > 0 ? (
              renderActivityChart()
            ) : (
              <div className="chart-empty">Keine Daten für Aktivitäten vorhanden</div>
            )}
          </div>
        )}

        {activeChart === 'daily' && (
          <div className="chart-wrapper">
            <h3>Durchschnittliche Stunden pro Wochentag (letzte 30 Tage)</h3>
            {dailyData.length > 0 ? (
              renderDailyChart()
            ) : (
              <div className="chart-empty">Keine Daten für Tagesverteilung vorhanden</div>
            )}
          </div>
        )}
      </div>

      <div className="chart-insights">
        {activeChart === 'weekly' && weeklyData.length > 0 && (
          <div className="insight">
            <span className="insight-icon">💡</span>
            <span className="insight-text">
              Diese Woche: {weeklyData[weeklyData.length - 1]?.hours || 0}h erfasst
            </span>
          </div>
        )}
        {activeChart === 'activity' && activityData.length > 0 && (
          <div className="insight">
            <span className="insight-icon">💡</span>
            <span className="insight-text">
              Meiste Zeit: {activityData[0]?.activity_name} (
              {activityData[0]?.hours.toFixed(1)}h)
            </span>
          </div>
        )}
        {activeChart === 'daily' && dailyData.length > 0 && (
          <div className="insight">
            <span className="insight-icon">💡</span>
            <span className="insight-text">
              Produktivster Tag:{' '}
              {dailyData.reduce((max, day) => (day.hours > max.hours ? day : max), dailyData[0])
                ?.day}{' '}
              (
              {dailyData
                .reduce((max, day) => (day.hours > max.hours ? day : max), dailyData[0])
                ?.hours.toFixed(1)}
              h)
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
