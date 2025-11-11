// Time Summary Cards Component
import React, { useEffect, useState } from 'react';
import { timeTrackingApi } from '../../api';
import { TimeSummaryStats } from '../../types';
import { format, subDays, startOfWeek, endOfWeek, startOfMonth, endOfMonth } from 'date-fns';
import '../../styles/time-tracking.css';

type TimePeriod = 'week' | 'month' | '7days' | '30days';

interface TimeSummaryCardsProps {
  onPeriodChange?: (period: TimePeriod) => void;
}

export const TimeSummaryCards: React.FC<TimeSummaryCardsProps> = ({ onPeriodChange }) => {
  const [stats, setStats] = useState<TimeSummaryStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<TimePeriod>('week');

  useEffect(() => {
    fetchStats(selectedPeriod);
  }, [selectedPeriod]);

  const getDateRange = (period: TimePeriod): { start_date: string; end_date: string } => {
    const now = new Date();
    let startDate: Date;
    let endDate: Date = now;

    switch (period) {
      case 'week':
        startDate = startOfWeek(now, { weekStartsOn: 1 }); // Monday
        endDate = endOfWeek(now, { weekStartsOn: 1 });
        break;
      case 'month':
        startDate = startOfMonth(now);
        endDate = endOfMonth(now);
        break;
      case '7days':
        startDate = subDays(now, 7);
        break;
      case '30days':
        startDate = subDays(now, 30);
        break;
      default:
        startDate = startOfWeek(now, { weekStartsOn: 1 });
    }

    return {
      start_date: format(startDate, 'yyyy-MM-dd'),
      end_date: format(endDate, 'yyyy-MM-dd'),
    };
  };

  const fetchStats = async (period: TimePeriod) => {
    try {
      setIsLoading(true);
      setError(null);
      const { start_date, end_date } = getDateRange(period);
      const data = await timeTrackingApi.getSummary({ start_date, end_date });
      setStats(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Statistiken');
    } finally {
      setIsLoading(false);
    }
  };

  const handlePeriodChange = (period: TimePeriod) => {
    setSelectedPeriod(period);
    if (onPeriodChange) {
      onPeriodChange(period);
    }
  };

  const formatHours = (hours: number): string => {
    return hours.toFixed(1);
  };

  const getComparisonClass = (comparison?: number): string => {
    if (!comparison) return '';
    return comparison >= 0 ? 'positive' : 'negative';
  };

  const formatComparison = (comparison?: number): string => {
    if (comparison === undefined || comparison === null) return '';
    const sign = comparison >= 0 ? '+' : '';
    return `${sign}${comparison.toFixed(1)}% vs. vorher`;
  };

  const getPeriodLabel = (period: TimePeriod): string => {
    switch (period) {
      case 'week':
        return 'Diese Woche';
      case 'month':
        return 'Dieser Monat';
      case '7days':
        return 'Letzte 7 Tage';
      case '30days':
        return 'Letzte 30 Tage';
      default:
        return 'Zeitraum';
    }
  };

  if (isLoading) {
    return <div className="time-summary-loading">Lade Statistiken...</div>;
  }

  if (error) {
    return <div className="time-summary-error">❌ {error}</div>;
  }

  if (!stats) {
    return null;
  }

  return (
    <div className="time-summary-container">
      <div className="time-summary-header">
        <h2>Zeiterfassung Übersicht</h2>
        <div className="period-selector">
          <button
            className={`period-btn ${selectedPeriod === 'week' ? 'active' : ''}`}
            onClick={() => handlePeriodChange('week')}
          >
            Diese Woche
          </button>
          <button
            className={`period-btn ${selectedPeriod === 'month' ? 'active' : ''}`}
            onClick={() => handlePeriodChange('month')}
          >
            Dieser Monat
          </button>
          <button
            className={`period-btn ${selectedPeriod === '7days' ? 'active' : ''}`}
            onClick={() => handlePeriodChange('7days')}
          >
            7 Tage
          </button>
          <button
            className={`period-btn ${selectedPeriod === '30days' ? 'active' : ''}`}
            onClick={() => handlePeriodChange('30days')}
          >
            30 Tage
          </button>
        </div>
      </div>

      <div className="time-summary-cards">
        {/* Total Hours Card */}
        <div className="summary-card total-hours">
          <div className="card-header">
            <span className="card-icon">⏱️</span>
            <h3>Gesamtstunden</h3>
          </div>
          <div className="card-value">
            <span className="main-value">{formatHours(stats.total_hours)}h</span>
            {stats.comparison_previous_period !== undefined && (
              <span className={`comparison ${getComparisonClass(stats.comparison_previous_period)}`}>
                {formatComparison(stats.comparison_previous_period)}
              </span>
            )}
          </div>
          <div className="card-footer">
            <span>{getPeriodLabel(selectedPeriod)}</span>
          </div>
        </div>

        {/* Billable Hours Card */}
        <div className="summary-card billable-hours">
          <div className="card-header">
            <span className="card-icon">💰</span>
            <h3>Abrechenbare Stunden</h3>
          </div>
          <div className="card-value">
            <span className="main-value">{formatHours(stats.billable_hours)}h</span>
            <span className="sub-value">
              {stats.total_hours > 0
                ? `${((stats.billable_hours / stats.total_hours) * 100).toFixed(0)}%`
                : '0%'}{' '}
              der Gesamtzeit
            </span>
          </div>
          <div className="card-footer">
            <span>Fakturierbare Arbeit</span>
          </div>
        </div>

        {/* Active Sessions Card */}
        <div className="summary-card active-sessions">
          <div className="card-header">
            <span className="card-icon">📊</span>
            <h3>Arbeitssitzungen</h3>
          </div>
          <div className="card-value">
            <span className="main-value">{stats.entries_count}</span>
            <span className="sub-value">
              Ø {Math.round(stats.average_session_minutes)} min pro Sitzung
            </span>
          </div>
          <div className="card-footer">
            <span>Zeiteinträge erfasst</span>
          </div>
        </div>

        {/* Most Used Activity Card */}
        <div className="summary-card most-used-activity">
          <div className="card-header">
            <span className="card-icon">🔧</span>
            <h3>Häufigste Aktivität</h3>
          </div>
          <div className="card-value">
            <span className="main-value activity-name">
              {stats.most_used_activity || 'Keine Daten'}
            </span>
            {stats.most_used_activity && (
              <span className="sub-value">
                Meistgenutzte Aktivität
              </span>
            )}
          </div>
          <div className="card-footer">
            <span>{getPeriodLabel(selectedPeriod)}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
