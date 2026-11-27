import { useQuery } from '@tanstack/react-query';
import { loadShowcase } from '../../application/use-cases/load-showcase';
import { useGateways } from './gateways';

/** The home page's showcase, read once per visit: no polling, no previous data kept. */
export function useShowcase() {
  const { pricing } = useGateways();
  return useQuery({
    queryKey: ['showcase'],
    queryFn: () => loadShowcase(pricing),
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: Infinity,
    gcTime: 0,
  });
}
