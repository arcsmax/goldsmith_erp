// ActivityPickerModal — FE-02 activity step for scan-driven timer starts.
//
// Fired through modal-stack by ActionHandlers (start_timer / switch_timer)
// when neither the caller nor this user's last-used activity supplies an
// activity_id. Wraps the existing ActivityPicker (top-5 most-used as big
// buttons + grouped list). Resolves with the chosen activity id; rejects
// on cancel / Esc / backdrop click so the handler can surface a German
// error without starting a timer.

import React, { useEffect } from 'react';

import ActivityPicker from '../ActivityPicker';
import type { ModalStackInjectedProps } from '../../lib/modal-stack';

type ActivityPickerModalProps = ModalStackInjectedProps<number>;

const BACKDROP_STYLE: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  zIndex: 'var(--modal-stack-z, 1600)',
  background: 'rgba(0, 0, 0, 0.55)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '16px',
};

const PANEL_STYLE: React.CSSProperties = {
  width: '100%',
  maxWidth: '720px',
  maxHeight: '90vh',
  overflowY: 'auto',
  borderRadius: '12px',
  background: 'var(--color-surface, #fff)',
};

export const ActivityPickerModal: React.FC<ActivityPickerModalProps> = ({
  resolve,
  reject,
}) => {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        reject(new Error('activity-picker-cancelled'));
      }
    };
    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [reject]);

  return (
    <div
      style={BACKDROP_STYLE}
      data-testid="activity-picker-modal"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          reject(new Error('activity-picker-cancelled'));
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Aktivität für den Timer wählen"
        style={PANEL_STYLE}
      >
        <ActivityPicker
          onSelectActivity={(activity) => resolve(activity.id)}
          onCancel={() => reject(new Error('activity-picker-cancelled'))}
        />
      </div>
    </div>
  );
};

export default ActivityPickerModal;
