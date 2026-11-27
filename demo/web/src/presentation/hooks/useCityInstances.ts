import { useQuery } from '@tanstack/react-query';
import {
  loadInstanceGeometry,
  loadInstanceMenu,
  loadInstanceView,
  loadRouteFailures,
} from '../../application/use-cases/load-instance-view';
import type { RoutesSummary } from '../../domain/city-instance';
import { useGateways } from './gateways';

export const INSTANCE_MENU_KEY = ['instance-menu'] as const;

/** The instances and their versions, for the menu. */
export function useInstanceMenu() {
  const { cityInstances } = useGateways();
  return useQuery({
    queryKey: INSTANCE_MENU_KEY,
    queryFn: () => loadInstanceMenu({ cityInstances }),
  });
}

/** One version with its instance's name and data set; data is null when there is no such version. */
export function useInstanceView(versionId: string | null) {
  const { cityInstances } = useGateways();
  return useQuery({
    queryKey: ['instance-view', versionId],
    queryFn: () => loadInstanceView({ cityInstances }, versionId ?? ''),
    enabled: versionId !== null,
    retry: false,
  });
}

/** The stations, hubs and hub pairs the map draws for a version. */
export function useInstanceGeometry(versionId: string | null) {
  const { cityInstances } = useGateways();
  return useQuery({
    queryKey: ['instance-geometry', versionId],
    queryFn: () => loadInstanceGeometry({ cityInstances }, versionId ?? ''),
    enabled: versionId !== null,
    staleTime: Infinity,
    retry: false,
  });
}

/** The failed queries of the run behind the routes; read only once `enabled`. */
export function useRouteFailures(routes: RoutesSummary | null, enabled: boolean) {
  const { cityInstances } = useGateways();
  return useQuery({
    queryKey: ['route-failures', routes?.runId ?? null],
    queryFn: () => loadRouteFailures({ cityInstances }, routes),
    enabled: enabled && routes?.runId !== null && routes !== null,
    staleTime: Infinity,
    retry: false,
  });
}
