// useDirtyGuard — "Änderungen verwerfen?" before a dirty form closes
// (UI-UX-PLAYBOOK 4.3, CLAUDE.md UI rules: dirty forms ask before closing;
// review 04 FE-16 unsaved-changes protection).
//
// `requestClose()` closes immediately when clean; when dirty it switches to
// the confirming state and the caller renders the question. While dirty the
// hook also asks the browser to warn on reload / tab close.
import { useCallback, useEffect, useState } from 'react';

export interface DirtyGuard {
  /** True while the "Änderungen verwerfen?" question is showing. */
  isConfirming: boolean;
  /** Close now if clean, otherwise ask first. */
  requestClose: () => void;
  /** Confirm the question: drop the changes and close. */
  discard: () => void;
  /** Dismiss the question and keep the form open. */
  keepEditing: () => void;
}

export function useDirtyGuard(isDirty: boolean, onClose: () => void): DirtyGuard {
  const [isConfirming, setIsConfirming] = useState(false);

  // A form that became clean again (saved) must not keep asking.
  useEffect(() => {
    if (!isDirty) setIsConfirming(false);
  }, [isDirty]);

  useEffect(() => {
    if (!isDirty) return undefined;
    const handleBeforeUnload = (event: BeforeUnloadEvent): void => {
      event.preventDefault();
      // Legacy browsers need a truthy returnValue to show the prompt.
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  const requestClose = useCallback(() => {
    if (isDirty) {
      setIsConfirming(true);
      return;
    }
    onClose();
  }, [isDirty, onClose]);

  const discard = useCallback(() => {
    setIsConfirming(false);
    onClose();
  }, [onClose]);

  const keepEditing = useCallback(() => setIsConfirming(false), []);

  return { isConfirming, requestClose, discard, keepEditing };
}
