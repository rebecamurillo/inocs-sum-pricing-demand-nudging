import { useQuery } from '@tanstack/react-query';
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
