// Button, ButtonLink and IconButton (UI-UX-PLAYBOOK 4.1).
//
// Every clickable action. Targets are never smaller than --touch-min (44px);
// size "lg" is the 56px bench size. Loading keeps the width, shows a spinner,
// sets aria-busy and disables the button so a double tap cannot submit twice.
// Links that navigate use ButtonLink (a real <a>), never a button.
import React, { forwardRef } from 'react';
import { Link, type LinkProps } from 'react-router-dom';

import { cx, devAssert } from './devAssert';
import { Icon, type IconName } from './Icon';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
/** md = 44px (default), lg = 56px (bench / Werkbank-Modus). No size below 44px. */
export type ButtonSize = 'md' | 'lg';

export type ButtonProps = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  /** Leading icon, decorative (aria-hidden). */
  icon?: IconName;
  type?: 'button' | 'submit';
  /** Stretch to the container width (phone footers). */
  block?: boolean;
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'type'>;

function buttonClasses(
  variant: ButtonVariant,
  size: ButtonSize,
  extra?: string,
  block?: boolean,
): string {
  return cx('ui-button', `ui-button--${variant}`, `ui-button--${size}`, block && 'ui-button--block', extra);
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading = false,
    icon,
    type = 'button',
    block,
    className,
    disabled,
    children,
    onClick,
    ...rest
  },
  ref,
) {
  const isDisabled = disabled || loading;
  return (
    <button
      ref={ref}
      type={type}
      className={buttonClasses(variant, size, className, block)}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      onClick={isDisabled ? undefined : onClick}
      {...rest}
    >
      {loading ? (
        <span className="ui-spinner" aria-hidden="true" />
      ) : (
        icon && <Icon name={icon} />
      )}
      <span className="ui-button__label">{children}</span>
    </button>
  );
});

export type ButtonLinkProps = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  block?: boolean;
} & LinkProps;

/** A navigation link styled as a button (react-router <Link>). */
export const ButtonLink = forwardRef<HTMLAnchorElement, ButtonLinkProps>(function ButtonLink(
  { variant = 'primary', size = 'md', icon, block, className, children, ...rest },
  ref,
) {
  return (
    <Link ref={ref} className={buttonClasses(variant, size, className, block)} {...rest}>
      {icon && <Icon name={icon} />}
      <span className="ui-button__label">{children}</span>
    </Link>
  );
});

export type IconButtonProps = {
  icon: IconName;
  /** Required German label; becomes aria-label and the tooltip. */
  label: string;
  variant?: Exclude<ButtonVariant, 'primary'>;
  size?: ButtonSize;
  type?: 'button' | 'submit';
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'type' | 'aria-label' | 'title' | 'children'>;

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { icon, label, variant = 'ghost', size = 'md', type = 'button', className, ...rest },
  ref,
) {
  devAssert(
    typeof label === 'string' && label.trim().length > 0,
    `IconButton "${String(icon)}" needs a German label (used as aria-label).`,
  );
  return (
    <button
      ref={ref}
      type={type}
      className={cx('ui-button', 'ui-icon-button', `ui-button--${variant}`, `ui-button--${size}`, className)}
      aria-label={label}
      title={label}
      {...rest}
    >
      <Icon name={icon} />
    </button>
  );
});
