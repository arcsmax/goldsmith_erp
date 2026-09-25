// StatusAdvanceButton — the order page's next action (W2-08, DOM-18).
//
// One large "Weiter: <next status>" primary button (56px, glove-friendly)
// for the obvious next step from the transition table, plus a small
// "Weitere Statuswechsel" menu for every other allowed move. Storniert sits
// last in the menu, separated, never beside the frequent action.
import { useEffect, useId, useRef, type KeyboardEvent } from 'react';
import type { OrderStatus } from '../../types';
import { OrderIcon, ORDER_STATUS_ICONS } from './OrderIcon';
import { primaryNextStatus, secondaryStatuses, statusLabel } from './orderStatus';

interface StatusAdvanceButtonProps {
  status: OrderStatus;
  isBusy: boolean;
  isMenuOpen: boolean;
  onMenuOpenChange: (isOpen: boolean) => void;
  onSelect: (target: OrderStatus) => void;
}

export function StatusAdvanceButton({
  status,
  isBusy,
  isMenuOpen,
  onMenuOpenChange,
  onSelect,
}: StatusAdvanceButtonProps) {
  const primary = primaryNextStatus(status);
  const others = secondaryStatuses(status);
  const menuId = useId();
  const menuRef = useRef<HTMLUListElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isMenuOpen) return;
    menuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
    const handlePointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !toggleRef.current?.contains(target)) {
        onMenuOpenChange(false);
      }
    };
    document.addEventListener('pointerdown', handlePointer);
    return () => document.removeEventListener('pointerdown', handlePointer);
  }, [isMenuOpen, onMenuOpenChange]);

  if (primary === null && others.length === 0) return null;

  const choose = (target: OrderStatus) => {
    // Focus the toggle first so a following dialog returns focus there.
    toggleRef.current?.focus();
    onMenuOpenChange(false);
    onSelect(target);
  };

  const handleMenuKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? []
    );
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === 'Escape') {
      event.preventDefault();
      onMenuOpenChange(false);
      toggleRef.current?.focus();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      items[(index + 1) % items.length]?.focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      items[(index - 1 + items.length) % items.length]?.focus();
    }
  };

  return (
    <div className="order-advance">
      {primary !== null && (
        <button
          type="button"
          className="btn btn-primary order-advance-primary"
          onClick={() => onSelect(primary)}
          disabled={isBusy}
          aria-busy={isBusy || undefined}
        >
          <OrderIcon name={ORDER_STATUS_ICONS[primary]} />
          {`Weiter: ${statusLabel(primary)}`}
        </button>
      )}
      {others.length > 0 && (
        <div className="order-advance-more">
          <button
            ref={toggleRef}
            type="button"
            className="btn btn-secondary order-advance-toggle"
            aria-haspopup="menu"
            aria-expanded={isMenuOpen}
            aria-controls={isMenuOpen ? menuId : undefined}
            onClick={() => onMenuOpenChange(!isMenuOpen)}
            disabled={isBusy}
          >
            {/* Visually hidden below 600px, so the name stays the visible text. */}
            <span className="order-advance-toggle-text">Weitere Statuswechsel</span>
            <OrderIcon name="chevron-down" />
          </button>
          {isMenuOpen && (
            <ul
              ref={menuRef}
              id={menuId}
              className="order-advance-menu"
              role="menu"
              aria-label="Weitere Statuswechsel"
              onKeyDown={handleMenuKeyDown}
            >
              {others.map((target) => (
                <li
                  key={target}
                  role="none"
                  className={target === 'cancelled' ? 'order-advance-menu-danger' : undefined}
                >
                  <button type="button" role="menuitem" onClick={() => choose(target)}>
                    <OrderIcon name={ORDER_STATUS_ICONS[target]} />
                    {statusLabel(target)}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default StatusAdvanceButton;
