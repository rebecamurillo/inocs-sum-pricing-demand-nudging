import { useCallback, useEffect, useState } from 'react';
import { ApiProblemError } from '../../application/errors';
import { loadSystemStatus } from '../../application/use-cases/load-system-status';
import type { SystemStatus } from '../../domain/system-status';
import { useGateways } from './gateways';

export interface FailureReason {
  readonly code: string;
  readonly title: string;
  readonly detail: string;
}

export type SystemStatusState =
  | { readonly kind: 'loading' }
  | { readonly kind: 'loaded'; readonly status: SystemStatus }
  | { readonly kind: 'failed'; readonly reason: FailureReason };

const loading: SystemStatusState = { kind: 'loading' };

function toFailureReason(error: unknown): FailureReason {
  if (error instanceof ApiProblemError) return error;
  return {
    code: 'unexpected_error',
    title: 'The system status could not be read',
    detail: error instanceof Error ? error.message : String(error),
  };
}

export function useSystemStatus(): { state: SystemStatusState; retry: () => void } {
  const { systemStatus } = useGateways();
  const [state, setState] = useState<SystemStatusState>(loading);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    loadSystemStatus(systemStatus).then(
      (status) => {
        if (!cancelled) setState({ kind: 'loaded', status });
      },
      (error: unknown) => {
        if (!cancelled) setState({ kind: 'failed', reason: toFailureReason(error) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [systemStatus, attempt]);

  const retry = useCallback(() => {
    setState(loading);
    setAttempt((current) => current + 1);
  }, []);

  return { state, retry };
}
