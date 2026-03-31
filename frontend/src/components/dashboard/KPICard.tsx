// Reusable KPI Card Component
import React from 'react';
import '../../styles/dashboard.css';

interface KPICardProps {
  title: string;
  value: string | number;
  icon: string;
  comparison?: number; // % change
  trend?: 'up' | 'down' | 'neutral';
  subtitle?: string;
  onClick?: () => void;
  loading?: boolean;
  color?: string;
}

export const KPICard: React.FC<KPICardProps> = ({
  title,
  value,
  icon,
  comparison,
  trend = 'neutral',
  subtitle,
  onClick,
  loading = false,
  color,
}) => {
  const getTrendClass = (): string => {
    if (!comparison) return '';
    if (trend === 'up') return 'positive';
    if (trend === 'down') return 'negative';
    return 'neutral';
  };

  const formatComparison = (): string => {
    if (comparison === undefined || comparison === null) return '';
    const sign = comparison >= 0 ? '+' : '';
    return `${sign}${comparison.toFixed(1)}%`;
  };

  if (loading) {
    return (
      <div className="kpi-card loading">
        <div className="kpi-skeleton">
          <div className="skeleton-icon"></div>
          <div className="skeleton-content">
            <div className="skeleton-title"></div>
            <div className="skeleton-value"></div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`kpi-card ${onClick ? 'clickable' : ''} ${color ? `kpi-${color}` : ''}`}
      onClick={onClick}
    >
      <div className="kpi-header">
        <span className="kpi-icon">{icon}</span>
        <h3 className="kpi-title">{title}</h3>
      </div>

      <div className="kpi-value-container">
        <div className="kpi-value">{value}</div>
        {subtitle && <div className="kpi-subtitle">{subtitle}</div>}
      </div>

      {comparison !== undefined && (
        <div className={`kpi-comparison ${getTrendClass()}`}>
          <span className="comparison-arrow">
            {trend === 'up' && '↗'}
            {trend === 'down' && '↘'}
            {trend === 'neutral' && '→'}
          </span>
          <span className="comparison-value">{formatComparison()}</span>
          <span className="comparison-text">vs. vorher</span>
        </div>
      )}
    </div>
  );
};
