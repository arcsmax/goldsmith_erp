// BenchModeToggle — the "Werkbank-Modus" switch (UI-UX-PLAYBOOK 5.5).
//
// A 56px toggle button (aria-pressed) that turns the bench layout of this
// device on or off. The label stays the same; aria-pressed carries the
// state (and the icon shows it: check = on). State and persistence live in lib/benchMode.ts.
import React from 'react';

import { useBenchMode } from '../../lib/benchMode';
import { Button } from '../../ui';

export const BenchModeToggle: React.FC<{ className?: string }> = ({ className }) => {
  const { isBenchMode, toggleBenchMode } = useBenchMode();
  return (
    <Button
      variant={isBenchMode ? 'primary' : 'secondary'}
      size="lg"
      icon={isBenchMode ? 'check' : 'hammer'}
      aria-pressed={isBenchMode}
      onClick={toggleBenchMode}
      className={className}
      data-testid="bench-mode-toggle"
    >
      Werkbank-Modus
    </Button>
  );
};

export default BenchModeToggle;
