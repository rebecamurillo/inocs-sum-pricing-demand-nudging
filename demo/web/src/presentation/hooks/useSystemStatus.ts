import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { SimulationRuleRef } from '../../domain/system-status';
import { loadSystemStatus } from '../../application/use-cases/load-system-status';
import { useGateways } from './gateways';

export const SYSTEM_STATUS_POLL_MS = 10_000;

/** The system status, read through the use case and refreshed every 10 s. */
export function useSystemStatus() {
  const { systemStatus } = useGateways();
  return useQuery({
    queryKey: ['system-status'],
    queryFn: () => loadSystemStatus(systemStatus),
    refetchInterval: SYSTEM_STATUS_POLL_MS,
  });
}

/**
 * The rule the Lab simulates with now: the last one `/system-status` named during the session.
 * The API names none while no runner is alive, which is exactly when the runner is off, so the
 * last one read stays the answer; null until one was read.
 */
export function useCurrentSimulationRule(): SimulationRuleRef | null {
  const named = useSystemStatus().data?.simulationRule ?? null;
  const [last, setLast] = useState<SimulationRuleRef | null>(null);
  if (named !== null && (named.id !== last?.id || named.version !== last.version)) setLast(named);
  return named ?? last;
}
