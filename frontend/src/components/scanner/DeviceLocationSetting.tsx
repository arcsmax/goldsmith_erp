// "Standort dieses Geräts" — the bench location a tablet reports with every
// scan (scan tracking, 2026-09 audit). Chosen once per device and kept in
// localStorage (lib/deviceId.ts) as the configured workshop location (W8
// dropdown, id + name); without it the scan falls back to the running
// timer's location.
import React, { useState } from 'react';

import { getDeviceLocationEntry, setDeviceLocation } from '../../lib/deviceId';
import { Button, Icon } from '../../ui';
import { useLocationPrompt } from './LocationPrompt';
import '../../styles/components/ScanTracking.css';

export interface DeviceLocationSettingProps {
  /** Called after the location changed (tests, parent refresh). */
  onChange?: (location: string | null) => void;
}

export const DeviceLocationSetting: React.FC<DeviceLocationSettingProps> = ({ onChange }) => {
  const [entry, setEntry] = useState(() => getDeviceLocationEntry());
  const { promptLocation, dialog } = useLocationPrompt();
  const location = entry?.name ?? null;

  const choose = async (): Promise<void> => {
    const picked = await promptLocation({
      title: 'Standort dieses Geräts',
      description: 'Jeder Scan auf diesem Gerät wird mit diesem Standort erfasst.',
      confirmLabel: 'Standort speichern',
      current: entry,
      allowClear: entry !== null,
    });
    if (picked === null) return;
    const saved = setDeviceLocation(picked.name ? picked : null);
    setEntry(saved);
    onChange?.(saved?.name ?? null);
  };

  return (
    <div className="scanner-device-location" data-testid="scanner-device-location">
      <Icon name="home" />
      <span>
        Standort dieses Geräts:{' '}
        <strong data-testid="scanner-device-location-value">{location ?? 'nicht festgelegt'}</strong>
      </span>
      <Button
        variant="secondary"
        size="lg"
        icon="pencil"
        onClick={() => void choose()}
        data-testid="scanner-device-location-edit"
      >
        {location === null ? 'Standort festlegen' : 'Standort ändern'}
      </Button>
      {dialog}
    </div>
  );
};

export default DeviceLocationSetting;
