import { useCallback, useEffect, useRef } from 'react';
import type { ParameterChanges } from '../../application/ports/city-instance-gateway';

export const AUTOSAVE_DELAY_MS = 500;

export interface Autosave<C extends object = ParameterChanges> {
  /** Adds changes to the pending ones and restarts the 500 ms wait. */
  schedule: (changes: C) => void;
  /**
   * Sends what is pending now and resolves when every send so far has answered; rejects when
   * the last send failed again, whose changes stay pending.
   */
  flush: () => Promise<void>;
  /** Forgets what is pending, for a draft that is about to go. */
  cancel: () => void;
  /** Runs another write of the draft after every send so far and before any later one. */
  after: <T>(write: () => Promise<T>) => Promise<T>;
}

/**
 * Debounced saving of a draft. One send follows a burst of changes; sends never overlap, so
 * the answers arrive in the order of the changes. A change still pending when the form closes
 * is sent then.
 */
export function useAutosave<C extends object = ParameterChanges>(
  send: (changes: C) => Promise<unknown>,
  delayMs: number = AUTOSAVE_DELAY_MS,
): Autosave<C> {
  const pending = useRef<C>({} as C);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const settled = useRef<Promise<void>>(Promise.resolve());
  const sendRef = useRef(send);
  // Raised by `cancel`: a send that fails after it does not bring its changes back.
  const generation = useRef(0);

  useEffect(() => {
    sendRef.current = send;
  });

  const stop = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const sendPending = useCallback((): Promise<void> => {
    const changes = pending.current;
    pending.current = {} as C;
    const at = generation.current;
    const sent = settled.current
      .then(() => sendRef.current(changes))
      .then(
        () => undefined,
        (error: unknown) => {
          // A failed change is not lost: the next send carries it, unless a newer value or a
          // cancel replaced it.
          if (generation.current === at) pending.current = { ...changes, ...pending.current };
          throw error;
        },
      );
    // A failed send does not block the next one; the caller of `flush` sees the failure.
    settled.current = sent.catch(() => undefined);
    return sent;
  }, []);

  const flush = useCallback(async (): Promise<void> => {
    stop();
    if (Object.keys(pending.current).length === 0) {
      await settled.current;
      // A send that failed meanwhile put its changes back: they are sent once more now.
      if (Object.keys(pending.current).length === 0) return;
      stop();
    }
    return sendPending();
  }, [stop, sendPending]);

  const schedule = useCallback(
    (changes: C) => {
      pending.current = { ...pending.current, ...changes };
      stop();
      timer.current = setTimeout(() => {
        flush().catch(() => undefined);
      }, delayMs);
    },
    [delayMs, flush, stop],
  );

  const cancel = useCallback(() => {
    stop();
    pending.current = {} as C;
    generation.current += 1;
  }, [stop]);

  const after = useCallback(<T>(write: () => Promise<T>): Promise<T> => {
    const done = settled.current.then(write);
    settled.current = done.then(
      () => undefined,
      () => undefined,
    );
    return done;
  }, []);

  useEffect(
    () => () => {
      flush().catch(() => undefined);
    },
    [flush],
  );

  return { schedule, flush, cancel, after };
}
