import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAutosave } from './useAutosave';

type Send = (changes: unknown) => Promise<void>;

describe('useAutosave', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends one merged patch 500 ms after the last change', async () => {
    const send = vi.fn(() => Promise.resolve());
    const { result } = renderHook(() => useAutosave(send));

    act(() => {
      result.current.schedule({ seed: 1 });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    act(() => {
      result.current.schedule({ seed: 2, radius_m: 3500 });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(499);
    });
    expect(send).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith({ seed: 2, radius_m: 3500 });
  });

  it('flush sends at once and resolves after the answer', async () => {
    let answer: () => void = () => undefined;
    const send = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          answer = resolve;
        }),
    );
    const { result } = renderHook(() => useAutosave(send));
    act(() => {
      result.current.schedule({ seed: 1 });
    });

    let done = false;
    let flushed: Promise<void> = Promise.resolve();
    await act(async () => {
      flushed = result.current.flush().then(() => {
        done = true;
      });
      await Promise.resolve();
    });
    expect(send).toHaveBeenCalledWith({ seed: 1 });
    expect(done).toBe(false);
    await act(async () => {
      answer();
      await flushed;
    });
    expect(done).toBe(true);
    // The timer was cleared: nothing is sent later.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('runs another write after the send in flight and before a later send', async () => {
    const answers: (() => void)[] = [];
    const order: string[] = [];
    const send = vi.fn((changes: unknown) => {
      order.push(`send ${JSON.stringify(changes)}`);
      return new Promise<void>((resolve) => {
        answers.push(resolve);
      });
    });
    const write = vi.fn(() => {
      order.push('write');
      return new Promise<string>((resolve) => {
        answers.push(() => {
          resolve('answer');
        });
      });
    });
    const { result } = renderHook(() => useAutosave(send));
    act(() => {
      result.current.schedule({ seed: 1 });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    let written: Promise<string> = Promise.resolve('');
    act(() => {
      written = result.current.after(write);
      result.current.schedule({ seed: 2 });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(order).toEqual(['send {"seed":1}']);

    await act(async () => {
      answers[0]?.();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(order).toEqual(['send {"seed":1}', 'write']);
    await act(async () => {
      answers[1]?.();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(await written).toBe('answer');
    expect(order).toEqual(['send {"seed":1}', 'write', 'send {"seed":2}']);
  });

  it('keeps the changes of a failed send for the next one, and flush rejects when it fails again', async () => {
    const send = vi.fn<Send>(() => Promise.reject(new Error('down')));
    const { result } = renderHook(() => useAutosave(send));
    act(() => {
      result.current.schedule({ seed: 1, radius_m: 3500 });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(send).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.schedule({ seed: 2 });
    });
    let failure: unknown = null;
    await act(async () => {
      await result.current.flush().catch((error: unknown) => {
        failure = error;
      });
    });

    expect(send).toHaveBeenLastCalledWith({ seed: 2, radius_m: 3500 });
    expect(failure).toEqual(new Error('down'));
  });

  it('a flush waits for a send in flight and sends its changes again when it failed', async () => {
    let fail: () => void = () => undefined;
    const send = vi
      .fn<Send>(() => Promise.resolve())
      .mockImplementationOnce(
        () =>
          new Promise<void>((_resolve, reject) => {
            fail = () => {
              reject(new Error('down'));
            };
          }),
      );
    const { result } = renderHook(() => useAutosave(send));
    act(() => {
      result.current.schedule({ seed: 1 });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    let flushed: Promise<void> = Promise.resolve();
    act(() => {
      flushed = result.current.flush();
    });
    await act(async () => {
      fail();
      await flushed;
    });

    expect(send).toHaveBeenCalledTimes(2);
    expect(send).toHaveBeenLastCalledWith({ seed: 1 });
  });

  it('does not bring back the changes of a send that fails after a cancel', async () => {
    let fail: () => void = () => undefined;
    const send = vi.fn<Send>(
      () =>
        new Promise<void>((_resolve, reject) => {
          fail = () => {
            reject(new Error('down'));
          };
        }),
    );
    const { result } = renderHook(() => useAutosave(send));
    act(() => {
      result.current.schedule({ seed: 1 });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    act(() => {
      result.current.cancel();
    });
    await act(async () => {
      fail();
      await result.current.flush();
    });

    expect(send).toHaveBeenCalledTimes(1);
  });

  it('waits for a send in flight and keeps the order of the sends', async () => {
    const answers: (() => void)[] = [];
    const calls: unknown[] = [];
    const send = vi.fn((changes: unknown) => {
      calls.push(changes);
      return new Promise<void>((resolve) => {
        answers.push(resolve);
      });
    });
    const { result } = renderHook(() => useAutosave(send));
    act(() => {
      result.current.schedule({ seed: 1 });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    act(() => {
      result.current.schedule({ seed: 2 });
    });
    let flushed = false;
    await act(async () => {
      void result.current.flush().then(() => {
        flushed = true;
      });
      await Promise.resolve();
    });
    // The second patch waits for the first answer.
    expect(calls).toEqual([{ seed: 1 }]);
    await act(async () => {
      answers[0]?.();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(calls).toEqual([{ seed: 1 }, { seed: 2 }]);
    expect(flushed).toBe(false);
    await act(async () => {
      answers[1]?.();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(flushed).toBe(true);
  });

  it('resolves a flush at once when nothing is pending', async () => {
    const send = vi.fn(() => Promise.resolve());
    const { result } = renderHook(() => useAutosave(send));

    await act(async () => {
      await result.current.flush();
    });

    expect(send).not.toHaveBeenCalled();
  });

  it('shows a failed send to the flush and still sends the next change', async () => {
    const send = vi
      .fn<(changes: unknown) => Promise<void>>()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValue(undefined);
    const { result } = renderHook(() => useAutosave(send));
    act(() => {
      result.current.schedule({ seed: 1 });
    });

    await act(async () => {
      await expect(result.current.flush()).rejects.toThrow('boom');
    });
    act(() => {
      result.current.schedule({ seed: 2 });
    });
    await act(async () => {
      await result.current.flush();
    });

    expect(send).toHaveBeenLastCalledWith({ seed: 2 });
  });

  it('forgets cancelled changes and sends a pending one when the form closes', async () => {
    const send = vi.fn(() => Promise.resolve());
    const first = renderHook(() => useAutosave(send));
    act(() => {
      first.result.current.schedule({ seed: 1 });
      first.result.current.cancel();
    });
    first.unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(send).not.toHaveBeenCalled();

    const second = renderHook(() => useAutosave(send));
    act(() => {
      second.result.current.schedule({ seed: 3 });
    });
    second.unmount();
    await act(async () => {
      await Promise.resolve();
    });

    expect(send).toHaveBeenCalledWith({ seed: 3 });
  });
});
