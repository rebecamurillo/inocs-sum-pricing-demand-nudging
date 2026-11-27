import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { StartFrom } from '../../application/ports/city-instance-gateway';
import {
  createInstance,
  discardDraft,
  openDraft,
  restoreDefaults,
  saveAndBuild,
  saveDraft,
  startFrom as startFromSource,
} from '../../application/use-cases/edit-draft';
import { deleteInstance, deleteVersion } from '../../application/use-cases/delete-instance';
import {
  loadInstanceGeometry,
  loadInstanceMenu,
  loadInstanceView,
  loadNewInstanceBasis,
  loadRouteFailures,
  type InstanceView,
} from '../../application/use-cases/load-instance-view';
import type { InstanceVersion, ParameterName, RoutesSummary } from '../../domain/city-instance';
import { useGateways } from './gateways';

export const INSTANCE_MENU_KEY = ['instance-menu'] as const;
export const instanceViewKey = (versionId: string | null) => ['instance-view', versionId] as const;

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
    queryKey: instanceViewKey(versionId),
    queryFn: () => loadInstanceView({ cityInstances }, versionId ?? ''),
    enabled: versionId !== null,
    retry: false,
  });
}

/**
 * The stations, hubs and hub pairs the map draws for a version. A build in progress passes the
 * states of its steps as `signature`: the data are read again when one changes.
 */
export function useInstanceGeometry(versionId: string | null, signature = '') {
  const { cityInstances } = useGateways();
  return useQuery({
    queryKey: ['instance-geometry', versionId, signature],
    queryFn: () => loadInstanceGeometry({ cityInstances }, versionId ?? ''),
    enabled: versionId !== null,
    staleTime: Infinity,
    // The map keeps what it draws until the new answer is there.
    placeholderData: keepPreviousData,
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

/** The latest city data set and the versions a new instance can start from. */
export function useNewInstanceBasis() {
  const { cityInstances, cityDatasets } = useGateways();
  return useQuery({
    queryKey: ['new-instance-basis'],
    queryFn: () => loadNewInstanceBasis({ cityInstances, cityDatasets }),
    retry: false,
  });
}

/**
 * The writes of the draft forms. Each one refreshes what it changed: a created or discarded
 * draft and a queued build refetch the menu, a `PATCH` answer replaces the version it was for.
 */
export function useDraftActions() {
  const { cityInstances } = useGateways();
  const gateways = { cityInstances };
  const client = useQueryClient();

  const refetchMenu = () => client.invalidateQueries({ queryKey: INSTANCE_MENU_KEY });
  const refetchVersion = (id: string) =>
    client.invalidateQueries({ queryKey: instanceViewKey(id) });
  const keepAnswer = async (answer: InstanceVersion) => {
    // A read still in flight (a refetch on focus) may predate this answer: it must not land after it.
    await client.cancelQueries({ queryKey: instanceViewKey(answer.id) });
    client.setQueryData<InstanceView | null>(instanceViewKey(answer.id), (old) =>
      old === undefined || old === null ? old : { ...old, version: answer },
    );
  };

  const create = useMutation({
    mutationFn: (input: { name: string; datasetId: string; startFrom: StartFrom }) =>
      createInstance(gateways, input.name, input.datasetId, input.startFrom),
    onSuccess: (result) => (result.kind === 'created' ? refetchMenu() : undefined),
  });
  const draft = useMutation({
    mutationFn: (input: { instanceId: string; basedOnId: string }) =>
      openDraft(gateways, input.instanceId, input.basedOnId),
    onSuccess: (result) => (result.existed ? undefined : refetchMenu()),
  });
  const discard = useMutation({
    mutationFn: (id: string) => discardDraft(gateways, id),
    onSuccess: (_none, id) => {
      client.removeQueries({ queryKey: instanceViewKey(id) });
      return refetchMenu();
    },
  });
  const build = useMutation({
    mutationFn: (input: { id: string; flush: () => Promise<void> }) =>
      saveAndBuild(gateways, input.id, input.flush),
    onSuccess: (result, input) => {
      if (result.kind !== 'queued') return undefined;
      return Promise.all([refetchMenu(), refetchVersion(input.id)]);
    },
  });

  return {
    create,
    draft,
    discard,
    build,
    /** One `PATCH`; the answer replaces the cached version. */
    patch: async (id: string, changes: Partial<Record<ParameterName, number>>) => {
      const answer = await saveDraft(gateways, id, changes);
      await keepAnswer(answer);
      return answer;
    },
    restoreDefaults: async (version: InstanceVersion) => {
      const answer = await restoreDefaults(gateways, version);
      await keepAnswer(answer);
      return answer;
    },
    startFrom: async (version: InstanceVersion, source: StartFrom) => {
      const answer = await startFromSource(gateways, version, source);
      await keepAnswer(answer);
      return answer;
    },
  };
}

/**
 * The deletions of a version and of an instance. A deletion that went through refetches the
 * menu; the caller leaves the deleted view, then `forget`s what was cached for it.
 */
export function useDeleteActions() {
  const { cityInstances } = useGateways();
  const gateways = { cityInstances };
  const client = useQueryClient();
  const refetchMenu = () => client.invalidateQueries({ queryKey: INSTANCE_MENU_KEY });

  const version = useMutation({
    mutationFn: (call: { id: string; includingPricingVersions: boolean }) =>
      deleteVersion(gateways, call.id, call.includingPricingVersions),
    onSuccess: (answer) => (answer.kind === 'deleted' ? refetchMenu() : undefined),
  });
  const instance = useMutation({
    mutationFn: (call: { id: string; includingPricingVersions: boolean }) =>
      deleteInstance(gateways, call.id, call.includingPricingVersions),
    onSuccess: (answer) => (answer.kind === 'deleted' ? refetchMenu() : undefined),
  });

  return {
    deleteVersion: version.mutateAsync,
    deleteInstance: instance.mutateAsync,
    /** Drops what was cached for the deleted versions. */
    forget: (versionIds: readonly string[]) => {
      for (const id of versionIds) client.removeQueries({ queryKey: instanceViewKey(id) });
    },
  };
}
