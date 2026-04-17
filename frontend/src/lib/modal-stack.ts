// Modal-stack — Slice 11 promise-based helper for stacked modals.
//
// Purpose:
//   ActionHandlers (Slice 11) need to suspend execution until the user
//   confirms/cancels a nested modal (AlloyMismatchModal, PunzierungsCheckModal,
//   stale-timer Mittagspause modal). A handler must be able to `await` the
//   user decision without wiring up ad-hoc callbacks through the React tree.
//
// Design:
//   * Singleton module-level store (`fireModal`, `onModalChange`, `closeModal`).
//   * `fireModal(Component, props)` returns a Promise that resolves when the
//     caller calls the `resolve` prop injected by the helper. It rejects if
//     the modal is cancelled via Esc / overlay-click / `reject` prop.
//   * A <ModalStackHost /> component subscribes to the store and renders the
//     top-most modal with the injected `resolve` / `reject` props.
//
// This is deliberately minimal — no z-index stacking beyond "one on top of
// the overlay at a time", no queue. The overlay (Slice 10) is already
// rendered above app chrome via its own stacking context; stacked modals
// land on top of that with `--modal-stack-z: 1600` from brand-tokens.
//
// Accessibility: the host component renders `role="presentation"`; individual
// modals own their own dialog semantics (role="dialog", aria-modal, focus
// trap). Esc / overlay-click cancellation is a convention each modal must
// honour by calling the `reject` prop — the host does NOT globally listen
// for Esc to keep the rule that each modal controls its own close logic.

import React, {
  useEffect,
  useState,
  type ComponentType,
} from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Extra props injected into every modal component when fired through
 * `fireModal`. The modal MUST call either `resolve(value)` or `reject(reason)`
 * exactly once — the helper cleans up on the first call.
 */
export interface ModalStackInjectedProps<TResult> {
  resolve: (value: TResult) => void;
  reject: (reason?: unknown) => void;
}

interface ModalStackEntry<TResult> {
  id: number;
  Component: ComponentType<ModalStackInjectedProps<TResult> & Record<string, unknown>>;
  props: Record<string, unknown>;
  resolve: (value: TResult) => void;
  reject: (reason?: unknown) => void;
}

type Listener = () => void;

// ---------------------------------------------------------------------------
// Store (module-level singleton)
// ---------------------------------------------------------------------------

let nextId = 1;
const stack: ModalStackEntry<unknown>[] = [];
const listeners: Set<Listener> = new Set();

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

/**
 * Fire a modal and get a Promise back. The modal's Component receives its
 * own props plus an injected `{resolve, reject}` pair that the modal must
 * use to signal its outcome.
 *
 * Example:
 * ```typescript
 * const payload = await fireModal(AlloyMismatchModal, {
 *   expected: { code: '750', label: 'Gelbgold' },
 *   actual:   { code: '585', label: 'Rotgold' },
 *   orderTitle: 'Trauring Mueller',
 * });
 * // payload: { category: '...', reason: '...' } — or throws on cancel
 * ```
 */
export function fireModal<TResult, TProps extends Record<string, unknown>>(
  Component: ComponentType<ModalStackInjectedProps<TResult> & TProps>,
  props: TProps,
): Promise<TResult> {
  return new Promise<TResult>((resolve, reject) => {
    const id = nextId++;

    const cleanup = (): void => {
      const idx = stack.findIndex((e) => e.id === id);
      if (idx !== -1) {
        stack.splice(idx, 1);
        notify();
      }
    };

    const wrappedResolve = (value: TResult): void => {
      cleanup();
      resolve(value);
    };

    const wrappedReject = (reason?: unknown): void => {
      cleanup();
      reject(reason);
    };

    stack.push({
      id,
      Component: Component as ComponentType<
        ModalStackInjectedProps<unknown> & Record<string, unknown>
      >,
      props: props as Record<string, unknown>,
      resolve: wrappedResolve as (v: unknown) => void,
      reject: wrappedReject,
    });
    notify();
  });
}

/** Test-only: clear every open modal. */
export function __resetModalStackForTests(): void {
  while (stack.length > 0) {
    const entry = stack.pop();
    if (entry) {
      entry.reject(new Error('modal-stack reset'));
    }
  }
  notify();
}

// ---------------------------------------------------------------------------
// React host component
// ---------------------------------------------------------------------------

export const ModalStackHost: React.FC = () => {
  const [version, setVersion] = useState<number>(0);

  useEffect(() => {
    const listener: Listener = () => setVersion((v) => v + 1);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  if (stack.length === 0) return null;

  // Render every modal in the stack. Most of the time there will be exactly
  // one. The top-most modal is the newest entry.
  return (
    <>
      {stack.map((entry) => {
        const Component = entry.Component;
        return (
          <Component
            key={entry.id}
            {...entry.props}
            resolve={entry.resolve}
            reject={entry.reject}
          />
        );
      })}
      {/* `version` keeps the host in sync with the store */}
      <span
        data-testid="modal-stack-version"
        aria-hidden="true"
        style={{ display: 'none' }}
      >
        {version}
      </span>
    </>
  );
};

export default ModalStackHost;
