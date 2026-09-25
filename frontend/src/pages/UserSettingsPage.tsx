// UserSettingsPage — Slice 12 minimal shell.
//
// V1.1 does not ship a full settings experience. This page exists so the
// Werkbank-Station-Modus toggle (A12.2) has a concrete home and so the
// HID burst-detection nudge (A12.1) can link users directly to the
// relevant control.
//
// Full user-preferences UI is out of scope for V1.1; later slices will
// grow this page (notification preferences, audio volume, language, etc).

import React from 'react';

import { useScannerContext } from '../contexts/ScannerContext';
import { ToggleSetting } from '../components/ToggleSetting';
import { ThemeToggle } from '../components/ThemeToggle';
import { Card, PageHeader } from '../ui';
import '../styles/user-settings.css';

export const UserSettingsPage: React.FC = () => {
  const { benchModeEnabled, toggleBenchMode } = useScannerContext();

  return (
    <div className="user-settings-container" data-testid="user-settings-page">
      <PageHeader title="Einstellungen" stickyPrimary={false} />

      {/* W4-05: colour scheme per device; "System" follows the device setting. */}
      <Card title="Darstellung" className="user-settings-section">
        <ThemeToggle showLegend />
      </Card>

      <Card title="Scanner-Einstellungen" className="user-settings-section">

        <ToggleSetting
          id="bench-mode-toggle"
          label="Werkbank-Station-Modus aktivieren"
          description={
            'Aktiviert den USB-HID-Scanner für die Werkbank. ' +
            'Tastatureingaben werden als Scans interpretiert, wenn kein ' +
            'Eingabefeld fokussiert ist.'
          }
          checked={benchModeEnabled}
          onChange={toggleBenchMode}
        />
      </Card>
    </div>
  );
};

export default UserSettingsPage;
