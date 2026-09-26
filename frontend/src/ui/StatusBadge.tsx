// <StatusBadge kind status> (UI-UX-PLAYBOOK 4.2; LV-05).
//
// Always icon plus German label, sentence case, tone from src/design/status.ts.
// Colour is never the only cue: the icon, the label and the border style
// (dashed draft, double handover, struck-through cancelled) carry it too.
// An unknown value renders raw in the neutral tone and logs a warning, so a
// new backend status gets noticed instead of silently mislabelled.
// Styles: .ui-status-badge* in styles/status-tones.css (global).
import { getStatusMeta, type StatusKind } from '../design/status';
import { Icon } from './Icon';

export interface StatusBadgeProps {
  kind: StatusKind;
  status: string;
  size?: 'md' | 'lg';
  /**
   * Customer-facing wording (portal, emails): replaces the staff label from
   * status.ts while tone and icon still come from the map. Staff screens
   * never pass it.
   */
  label?: string;
  className?: string;
}

export function StatusBadge({ kind, status, size = 'md', label, className }: StatusBadgeProps) {
  const found = getStatusMeta(kind, status);
  if (!found) {
    console.warn('StatusBadge: unknown status', { kind, status });
  }
  const tone = found?.tone ?? 'neutral';
  const border = found?.border ?? 'solid';
  const classes = [
    'status-badge',
    'ui-status-badge',
    `ui-status-badge--${tone}`,
    `ui-status-badge--${border}`,
    size === 'lg' ? 'ui-status-badge--lg' : null,
    className ?? null,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <span className={classes} data-status={status} data-kind={kind}>
      <Icon name={found?.icon ?? 'circle-help'} className="ui-status-badge__icon" />
      <span className="ui-status-badge__label">{label ?? found?.label ?? status}</span>
    </span>
  );
}

export default StatusBadge;
