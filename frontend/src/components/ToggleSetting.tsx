// ToggleSetting — accessible labelled toggle for a user-preference row.
//
// Introduced for the Slice 12 Werkbank-Station-Modus toggle; kept generic
// so future settings rows can reuse the same shape. Renders a native
// checkbox styled as a switch — the underlying <input type="checkbox"> is
// always interactive via keyboard and assistive tech per ARIA Authoring
// Practices for toggle switches.

import React, { useCallback } from 'react';

import '../styles/components/ToggleSetting.css';

export interface ToggleSettingProps {
  id: string;
  label: string;
  /** Optional long-form description rendered under the label. */
  description?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  /** Disable the control (UI remains visible but not interactive). */
  disabled?: boolean;
}

export const ToggleSetting: React.FC<ToggleSettingProps> = ({
  id,
  label,
  description,
  checked,
  onChange,
  disabled = false,
}) => {
  const descriptionId =
    description !== undefined ? `${id}-description` : undefined;

  const handleChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>): void => {
      onChange(event.target.checked);
    },
    [onChange],
  );

  return (
    <div
      className={`toggle-setting${disabled ? ' toggle-setting--disabled' : ''}`}
      data-testid={`toggle-setting-${id}`}
    >
      <div className="toggle-setting__text">
        <label
          htmlFor={id}
          className="toggle-setting__label"
          data-testid={`toggle-setting-label-${id}`}
        >
          {label}
        </label>
        {description !== undefined ? (
          <p
            id={descriptionId}
            className="toggle-setting__description"
            data-testid={`toggle-setting-description-${id}`}
          >
            {description}
          </p>
        ) : null}
      </div>
      <span className="toggle-setting__switch">
        <input
          id={id}
          type="checkbox"
          role="switch"
          aria-describedby={descriptionId}
          className="toggle-setting__input"
          checked={checked}
          disabled={disabled}
          onChange={handleChange}
          data-testid={`toggle-setting-input-${id}`}
        />
        <span className="toggle-setting__slider" aria-hidden="true" />
      </span>
    </div>
  );
};

export default ToggleSetting;
