// "Standort dieses Geräts" — the bench location a tablet reports with every
// scan (scan tracking, 2026-09 audit). Chosen once per device and kept in
// localStorage (lib/deviceId.ts); without it the scan falls back to the
// running timer's location.
import React, { useState } from 'react';

import { getDeviceLocation, MAX_LOCATION_LENGTH, setDeviceLocation } from '../../lib/deviceId';
import { Button, Icon, usePromptDialog } from '../../ui';
import '../../styles/components/ScanTracking.css';

export interface DeviceLocationSettingProps {
  /** Called after the location changed (tests, parent refresh). */
  onChange?: (location: string | null) => void;
}

export const DeviceLocationSetting: React.FC<DeviceLocationSettingProps> = ({ onChange }) => {
  const [location, setLocation] = useState<string | null>(() => getDeviceLocation());
  const { prompt, dialog } = usePromptDialog();

  const choose = async (): Promise<void> => {
    const typed = await prompt({
      title: 'Standort dieses Geräts',
      label: 'Standort',
      description:
        'Jeder Scan auf diesem Gerät wird mit diesem Standort erfasst. Leer lassen, um ihn zu entfernen.',
      help: 'z. B. Werkbank 2, Empfang, Tresor',
      defaultValue: location ?? '',
      confirmLabel: 'Standort speichern',
      maxLength: MAX_LOCATION_LENGTH,
    });
    if (typed === null) return;
    const saved = setDeviceLocation(typed);
    setLocation(saved);
    onChange?.(saved);
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
