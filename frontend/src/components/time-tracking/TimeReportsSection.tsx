// Time Reports Section Component with Recharts
import React, { useEffect, useState } from 'react';
import { timeTrackingApi } from '../../api';
import { ActivityBreakdownData, WeeklyTimeData } from '../../types';
import { format, subDays, startOfWeek, endOfWeek } from 'date-fns';
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

      const now = new Date();
      const startDate = format(subDays(now, 30), 'yyyy-MM-dd');
      const endDate = format(now, 'yyyy-MM-dd');

      // Fetch weekly trend data
      const weeklyResult = await timeTrackingApi.getWeeklyReport({ weeks: 4 });
      const formattedWeeklyData = weeklyResult.map((week: WeeklyTimeData) => ({
        week: format(new Date(week.week_start), 'dd.MM'),
        hours: parseFloat(week.total_hours.toFixed(1)),
        entries: week.entries_count,
      }));
      setWeeklyData(formattedWeeklyData);

      // Fetch activity breakdown
      const activityResult = await timeTrackingApi.getActivityBreakdown({
        start_date: startDate,
        end_date: endDate,
      });
      setActivityData(activityResult);

      // Fetch daily distribution
      const dailyResult = await timeTrackingApi.getDailyDistribution({
        start_date: startDate,
        end_date: endDate,
      });
      setDailyData(dailyResult.map((d) => ({
        day: d.day,
        hours: parseFloat(d.hours.toFixed(1)),
      })));

    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Berichte');
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
          label={(entry) => `${entry.activity_name}: ${entry.percentage.toFixed(1)}%`}
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
