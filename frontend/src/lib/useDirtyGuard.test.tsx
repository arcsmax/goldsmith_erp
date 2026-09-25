import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useDirtyGuard } from './useDirtyGuard';

describe('useDirtyGuard', () => {
  it('closes immediately when clean', () => {
    const onClose = vi.fn();
    const { result } = renderHook(() => useDirtyGuard(false, onClose));
    act(() => result.current.requestClose());
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(result.current.isConfirming).toBe(false);
  });

  it('asks first when dirty, then discards or keeps editing', () => {
    const onClose = vi.fn();
    const { result } = renderHook(() => useDirtyGuard(true, onClose));
    act(() => result.current.requestClose());
    expect(onClose).not.toHaveBeenCalled();
    expect(result.current.isConfirming).toBe(true);
    act(() => result.current.keepEditing());
    expect(result.current.isConfirming).toBe(false);
    act(() => result.current.requestClose());
    act(() => result.current.discard());
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(result.current.isConfirming).toBe(false);
  });

  it('warns on page unload only while dirty', () => {
    const { rerender, unmount } = renderHook(({ dirty }) => useDirtyGuard(dirty, vi.fn()), {
      initialProps: { dirty: true },
    });
    const dirtyEvent = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(dirtyEvent);
    expect(dirtyEvent.defaultPrevented).toBe(true);

    rerender({ dirty: false });
    const cleanEvent = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(cleanEvent);
    expect(cleanEvent.defaultPrevented).toBe(false);
    unmount();
  });
});
