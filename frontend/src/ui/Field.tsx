// Field (UI-UX-PLAYBOOK 4.4): label, control, help and error as one unit.
//
// Wraps exactly one <input>, <select> or <textarea> and wires it: id/htmlFor,
// name, required + aria-required, aria-invalid, aria-describedby (error first,
// then help, then the unit), inputMode. The label is always visible; a
// placeholder is never the label. Errors say what is wrong and how to fix it
// ("Gewicht fehlt. Bitte in Gramm eingeben."), never just "Ungültig".
import React, { cloneElement, isValidElement, useId } from 'react';

import { cx, devAssert } from './devAssert';
import { Icon } from './Icon';

export type FieldInputMode = 'text' | 'decimal' | 'numeric' | 'tel' | 'email' | 'search';

export interface FieldProps {
  label: string;
  name: string;
  /** Shows the "Pflichtfeld" marker and sets required + aria-required. */
  required?: boolean;
  help?: string;
  error?: string;
  inputMode?: FieldInputMode;
  /** Unit shown after the control ("g", "€"); also announced via the description. */
  suffix?: string;
  className?: string;
  children: React.ReactElement;
}

type ControlProps = {
  id?: string;
  name?: string;
  className?: string;
  required?: boolean;
  inputMode?: FieldInputMode;
  'aria-required'?: boolean;
  'aria-invalid'?: boolean;
  'aria-describedby'?: string;
};

export const Field: React.FC<FieldProps> = ({
  label,
  name,
  required = false,
  help,
  error,
  inputMode,
  suffix,
  className,
  children,
}) => {
  devAssert(isValidElement(children), 'Field needs exactly one input, select or textarea child.');
  const generatedId = useId();
  const child = children as React.ReactElement<ControlProps>;
  const controlId = child.props.id ?? `field-${generatedId}`;
  const errorId = `${controlId}-error`;
  const helpId = `${controlId}-help`;
  const unitId = `${controlId}-unit`;

  const describedBy =
    [error && errorId, help && helpId, suffix && unitId, child.props['aria-describedby']]
      .filter(Boolean)
      .join(' ') || undefined;

  const control = cloneElement(child, {
    id: controlId,
    name: child.props.name ?? name,
    className: cx('ui-field__control', child.props.className),
    required: required || child.props.required,
    inputMode: inputMode ?? child.props.inputMode,
    'aria-required': required || undefined,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': describedBy,
  });

  return (
    <div className={cx('ui-field', error && 'ui-field--invalid', className)}>
      <label className="ui-field__label" htmlFor={controlId}>
        {label}
        {required && (
          <span className="ui-field__required" aria-hidden="true">
            Pflichtfeld
          </span>
        )}
      </label>
      {suffix ? (
        <div className="ui-field__affix">
          {control}
          <span className="ui-field__suffix" aria-hidden="true">
            {suffix}
          </span>
          <span id={unitId} className="ui-visually-hidden">
            Einheit: {suffix}
          </span>
        </div>
      ) : (
        control
      )}
      {error && (
        <p id={errorId} className="ui-field__error">
          <Icon name="alert-triangle" />
          <span>{error}</span>
        </p>
      )}
      {help && (
        <p id={helpId} className="ui-field__help">
          {help}
        </p>
      )}
    </div>
  );
};
