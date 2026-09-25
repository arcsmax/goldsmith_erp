// Promise-based Standort chooser for the scanner (scan tracking + W8
// workshop locations): the configured locations dropdown (LocationPicker)
// in a Modal. Used by "Standort setzen" in the scan sheet and by
// "Standort dieses Geräts" on the scanner page.
//
//   const { promptLocation, dialog } = useLocationPrompt();
//   const picked = await promptLocation({ title, confirmLabel, current });
//   // picked: { id, name } | null (cancelled); render {dialog} once.
import React, { useCallback, useState } from 'react';

import { LocationPicker } from '../LocationPicker';
import { Button, Modal } from '../../ui';

export interface PickedLocation {
  /** Configured location id; null for a stored free-text label. */
  id: number | null;
  name: string;
}

export interface LocationPromptOptions {
  title: string;
  confirmLabel: string;
  description?: string;
  current?: PickedLocation | null;
  /** Offer "Standort entfernen" (resolves { id: null, name: '' }). */
  allowClear?: boolean;
}

interface Pending {
  options: LocationPromptOptions;
  resolve: (value: PickedLocation | null) => void;
}

const LocationPromptDialog: React.FC<{
  pending: Pending;
  onSettle: (value: PickedLocation | null) => void;
}> = ({ pending, onSettle }) => {
  const { options } = pending;
  const [selected, setSelected] = useState<PickedLocation | null>(options.current ?? null);
  const hasSelection = selected !== null && selected.name.trim().length > 0;

  return (
    <Modal
      open
      size="sm"
      title={options.title}
      description={options.description}
      onClose={() => onSettle(null)}
      footer={
        <>
          {options.allowClear && (
            <Button variant="secondary" onClick={() => onSettle({ id: null, name: '' })}>
              Standort entfernen
            </Button>
          )}
          <Button variant="secondary" onClick={() => onSettle(null)}>
            Abbrechen
          </Button>
          <Button disabled={!hasSelection} onClick={() => onSettle(selected)}>
            {options.confirmLabel}
          </Button>
        </>
      }
    >
      <LocationPicker
        id="scanner-location-picker"
        value={selected?.id ?? null}
        currentName={selected?.name ?? null}
        onChange={(location) =>
          setSelected(location === null ? null : { id: location.id, name: location.name })
        }
      />
    </Modal>
  );
};

export function useLocationPrompt(): {
  promptLocation: (options: LocationPromptOptions) => Promise<PickedLocation | null>;
  dialog: React.ReactElement | null;
} {
  const [pending, setPending] = useState<Pending | null>(null);

  const promptLocation = useCallback(
    (options: LocationPromptOptions) =>
      new Promise<PickedLocation | null>((resolve) => setPending({ options, resolve })),
    [],
  );

  const settle = useCallback(
    (value: PickedLocation | null) => {
      pending?.resolve(value);
      setPending(null);
    },
    [pending],
  );

  const dialog = pending ? <LocationPromptDialog pending={pending} onSettle={settle} /> : null;
  return { promptLocation, dialog };
}
