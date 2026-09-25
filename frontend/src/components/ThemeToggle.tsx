// ThemeToggle — "System / Hell / Dunkel" colour scheme choice (W4-05).
//
// A native radio group (arrow keys move between options, one tab stop),
// styled as a segmented control. The choice is stored per device by
// hooks/useTheme.ts. `variant="header"` sits on the amber app header.
import React, { useId } from 'react';

import { useColorScheme, type ColorSchemePreference } from '../hooks/useTheme';
import '../styles/components/ThemeToggle.css';

const OPTIONS: ReadonlyArray<{ value: ColorSchemePreference; label: string }> = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Hell' },
  { value: 'dark', label: 'Dunkel' },
];

type ThemeToggleProps = {
  variant?: 'default' | 'header';
  /** Show the "Farbschema" legend (settings page); hidden but announced otherwise. */
  showLegend?: boolean;
  className?: string;
};

export const ThemeToggle: React.FC<ThemeToggleProps> = ({
  variant = 'default',
  showLegend = false,
  className,
}) => {
  const { preference, setPreference } = useColorScheme();
  const name = useId();
  const classes = ['theme-toggle', `theme-toggle--${variant}`, className].filter(Boolean).join(' ');

  return (
    <fieldset className={classes} data-testid="theme-toggle">
      <legend className={showLegend ? 'theme-toggle__legend' : 'ui-visually-hidden'}>
        Farbschema
      </legend>
      <div className="theme-toggle__options">
        {OPTIONS.map((option) => (
          <label key={option.value} className="theme-toggle__option">
            <input
              type="radio"
              className="theme-toggle__input"
              name={name}
              value={option.value}
              checked={preference === option.value}
              onChange={() => setPreference(option.value)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
};

export default ThemeToggle;
