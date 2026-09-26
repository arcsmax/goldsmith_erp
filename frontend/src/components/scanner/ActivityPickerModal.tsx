// ActivityPickerModal — FE-02 activity step for scan-driven timer starts.
//
// Fired through modal-stack by ActionHandlers (start_timer / switch_timer)
// when neither the caller nor this user's last-used activity supplies an
// activity_id. W4-03: a src/ui Sheet around the bench ActivityPicker
// (most-used first, 56px targets). Resolves with the chosen activity id;
// rejects on the close button or Escape so the handler can surface a German
// error without starting a timer.
//
// The sheet opens on top of the ScanOverlay and QuickActionModalV2, which
// run their own document keydown handlers (Escape closes the overlay, Tab
// is trapped inside it). A capture-phase listener keeps Escape and Tab for
// this sheet and stops them there, as the pre-W4-03 modal did; the sheet's
// root is lifted above the overlay in ActivityPicker.css.
import React, { useEffect, useRef } from 'react';

import ActivityPicker from '../ActivityPicker';
import type { ModalStackInjectedProps } from '../../lib/modal-stack';
import { Sheet } from '../../ui';
import { trapTab } from '../../ui/focus';

type ActivityPickerModalProps = ModalStackInjectedProps<number>;

const SHEET_CLASS = 'activity-picker-sheet';

export const ActivityPickerModal: React.FC<ActivityPickerModalProps> = ({ resolve, reject }) => {
  const rejectRef = useRef(reject);
  rejectRef.current = reject;
  const cancel = () => rejectRef.current(new Error('activity-picker-cancelled'));

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        rejectRef.current(new Error('activity-picker-cancelled'));
        return;
      }
      if (event.key !== 'Tab') return;
      const sheet = document.querySelector<HTMLElement>(`.${SHEET_CLASS}`);
      if (!sheet) return;
      event.stopPropagation();
      trapTab(event, sheet);
    };
    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, []);

  return (
    <Sheet open onClose={cancel} title="Aktivität für den Timer wählen" size="lg" className={SHEET_CLASS}>
      <div data-testid="activity-picker-modal">
        <ActivityPicker onSelectActivity={(activity) => resolve(activity.id)} />
      </div>
    </Sheet>
  );
};

export default ActivityPickerModal;
