import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import {
  deletePricingVersion,
  discardPricingDraft,
  duplicatePricingVersion,
  newPricingVersion,
  runPricingVersion,
  savePricingDraft,
  simulatePricingVersion,
} from '../../application/use-cases/edit-pricing-draft';
import type { PricingChanges, PricingVersion } from '../../domain/pricing-version';
import { useGateways } from './gateways';
import { INSTANCE_MENU_KEY } from './useCityInstances';
import type { Run } from '../../domain/run';
import { ACTIVE_RUNS_KEY, useActiveRuns } from './useRuns';

export const pricingListKey = (instanceVersionId: string | null) =>
  ['pricing-list', instanceVersionId] as const;
export const pricingResultKey = (id: string | null) => ['pricing-result', id] as const;
export const pricingVersionKey = (id: string | null) => ['pricing-version', id] as const;

/**
 * The pricing versions of an instance version, for the menu. Read again when a queued or running
 * run starts, ends or moves up the queue, so that a row leaves `draft` and later gains `✓ result`.
 */
export function usePricingList(instanceVersionId: string | null) {
  const { pricing } = useGateways();
  const client = useQueryClient();
  const { runs } = useActiveRuns();
  const query = useQuery({
    queryKey: pricingListKey(instanceVersionId),
    queryFn: () => pricing.list(instanceVersionId ?? ''),
    enabled: instanceVersionId !== null,
    retry: false,
  });
  const signature = runs
    .filter((run) => run.subject.type === 'pricing_version')
    .map((run) => `${run.id}:${run.state}`)
    .join(',');
  const seen = useRef(signature);
  useEffect(() => {
    if (seen.current === signature) return;
    seen.current = signature;
    void client.invalidateQueries({ queryKey: ['pricing-list'] });
    void client.invalidateQueries({ queryKey: ['pricing-version'] });
    void client.invalidateQueries({ queryKey: ['pricing-result'] });
    void client.invalidateQueries({ queryKey: ['pricing-hub-pairs'] });
    void client.invalidateQueries({ queryKey: ['pricing-hubs'] });
    void client.invalidateQueries({ queryKey: ['pricing-simulations'] });
  }, [signature, client]);
  return query;
}

/** One pricing version; data is null when the API has none by this id. */
export function usePricingVersion(id: string | null) {
  const { pricing } = useGateways();
  return useQuery({
    queryKey: pricingVersionKey(id),
    queryFn: () => pricing.get(id ?? ''),
    enabled: id !== null,
    retry: false,
  });
}

/**
 * The stored result of a pricing version; data is null when it has none. A re-read keeps the
 * previous result as placeholder data (`isPlaceholderData`) so the card can stay under its skeleton.
 */
export function usePricingResult(id: string | null) {
  const { pricing } = useGateways();
  return useQuery({
    queryKey: pricingResultKey(id),
    queryFn: () => pricing.result(id ?? ''),
    enabled: id !== null,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export const hubPairResultsKey = (id: string | null) => ['pricing-hub-pairs', id] as const;
export const hubResultsKey = (id: string | null) => ['pricing-hubs', id] as const;

/** The model's price and flow per hub pair; `id` null reads nothing. */
export function useHubPairResults(id: string | null) {
  const { pricing } = useGateways();
  return useQuery({
    queryKey: hubPairResultsKey(id),
    queryFn: () => pricing.hubPairResults(id ?? ''),
    enabled: id !== null,
    retry: false,
  });
}

export const pricingSimulationsKey = (id: string | null) => ['pricing-simulations', id] as const;

/** Every stored simulation of a version (the Advanced view's earlier simulations); `id` null reads nothing. */
export function usePricingSimulations(id: string | null) {
  const { pricing } = useGateways();
  return useQuery({
    queryKey: pricingSimulationsKey(id),
    queryFn: () => pricing.simulations(id ?? ''),
    enabled: id !== null,
    retry: false,
  });
}

/** The model's bike rides and mean price per hub; `id` null reads nothing. */
export function useHubResults(id: string | null) {
  const { pricing } = useGateways();
  return useQuery({
    queryKey: hubResultsKey(id),
    queryFn: () => pricing.hubResults(id ?? ''),
    enabled: id !== null,
    retry: false,
  });
}

/**
 * Reads a version's result and simulations again once its simulation run has left the active
 * runs. `usePricingList` does so too, but only while the menu lists the version; and a run that
 * ends before the run list shows it is never seen there: `watch` takes the queued run's id.
 */
export function useSimulationEnd(id: string, simulationRunId: string | null) {
  const client = useQueryClient();
  const { runs } = useActiveRuns();
  const watched = useRef<string | null>(null);
  // A new watch must look at the run list even when that list did not change.
  const [watches, setWatches] = useState(0);
  useEffect(() => {
    if (simulationRunId !== null) {
      watched.current = simulationRunId;
      return;
    }
    const runId = watched.current;
    if (runId === null || runs.some((run) => run.id === runId)) return;
    watched.current = null;
    void client.invalidateQueries({ queryKey: pricingResultKey(id) });
    void client.invalidateQueries({ queryKey: pricingSimulationsKey(id) });
  }, [simulationRunId, runs, watches, client, id]);
  return {
    watch: (runId: string) => {
      watched.current = runId;
      setWatches((count) => count + 1);
    },
  };
}

/** Reads the version, the lists and the run list again when the followed run changes state. */
export function usePricingRunSync(run: Run | null) {
  const client = useQueryClient();
  const previous = useRef<string | null>(null);
  const signature =
    run === null ? null : `${run.id}:${run.state}:${run.steps.map((step) => step.state).join(',')}`;
  useEffect(() => {
    if (signature === null) return;
    const before = previous.current;
    previous.current = signature;
    if (before === null || before === signature) return;
    void client.invalidateQueries({ queryKey: ['pricing-list'] });
    void client.invalidateQueries({ queryKey: ['pricing-version'] });
    void client.invalidateQueries({ queryKey: ['pricing-result'] });
    void client.invalidateQueries({ queryKey: ['pricing-hub-pairs'] });
    void client.invalidateQueries({ queryKey: ['pricing-hubs'] });
    void client.invalidateQueries({ queryKey: ['pricing-simulations'] });
    void client.invalidateQueries({ queryKey: INSTANCE_MENU_KEY });
    void client.invalidateQueries({ queryKey: ACTIVE_RUNS_KEY });
  }, [signature, client]);
}

/** The writes of the pricing form and of "+ New pricing version"; each refreshes what it changed. */
export function usePricingActions() {
  const { pricing } = useGateways();
  const gateways = { pricing };
  const client = useQueryClient();
  const refetchList = (instanceVersionId: string) =>
    client.invalidateQueries({ queryKey: pricingListKey(instanceVersionId) });
  const keepAnswer = async (answer: PricingVersion) => {
    // A read still in flight may predate this answer: it must not land after it.
    await client.cancelQueries({ queryKey: pricingVersionKey(answer.id) });
    client.setQueryData<PricingVersion | null>(pricingVersionKey(answer.id), answer);
    client.setQueryData<PricingVersion[] | undefined>(
      pricingListKey(answer.instanceVersionId),
      (old) => old?.map((version) => (version.id === answer.id ? answer : version)),
    );
  };

  const create = useMutation({
    mutationFn: (instanceVersionId: string) => newPricingVersion(gateways, instanceVersionId),
    onSuccess: async (version) => {
      client.setQueryData<PricingVersion | null>(pricingVersionKey(version.id), version);
      await Promise.all([
        refetchList(version.instanceVersionId),
        client.invalidateQueries({ queryKey: INSTANCE_MENU_KEY }),
      ]);
    },
  });
  const duplicate = useMutation({
    mutationFn: (version: PricingVersion) => duplicatePricingVersion(gateways, version),
    onSuccess: async (version) => {
      client.setQueryData<PricingVersion | null>(pricingVersionKey(version.id), version);
      await Promise.all([
        refetchList(version.instanceVersionId),
        client.invalidateQueries({ queryKey: INSTANCE_MENU_KEY }),
      ]);
    },
  });
  const discard = useMutation({
    mutationFn: (version: PricingVersion) => discardPricingDraft(gateways, version.id),
    onSuccess: async (_none, version) => {
      client.removeQueries({ queryKey: pricingVersionKey(version.id) });
      await Promise.all([
        refetchList(version.instanceVersionId),
        client.invalidateQueries({ queryKey: INSTANCE_MENU_KEY }),
      ]);
    },
  });
  const run = useMutation({
    mutationFn: (input: { id: string; flush: () => Promise<void> }) =>
      runPricingVersion(gateways, input.id, input.flush),
    onSuccess: async (result, input) => {
      if (result.kind !== 'queued') return;
      await Promise.all([
        client.invalidateQueries({ queryKey: pricingVersionKey(input.id) }),
        client.invalidateQueries({ queryKey: ['pricing-list'] }),
        client.invalidateQueries({ queryKey: ACTIVE_RUNS_KEY }),
      ]);
    },
  });

  const simulate = useMutation({
    mutationFn: (id: string) => simulatePricingVersion(gateways, id),
    onSuccess: async (result) => {
      if (result.kind !== 'queued') return;
      await client.invalidateQueries({ queryKey: ACTIVE_RUNS_KEY });
    },
  });
  const remove = useMutation({
    mutationFn: (version: PricingVersion) => deletePricingVersion(gateways, version.id),
    onSuccess: async (answer, version) => {
      if (answer.kind !== 'deleted') return;
      for (const prefix of [
        'pricing-version',
        'pricing-result',
        'pricing-hub-pairs',
        'pricing-hubs',
        'pricing-simulations',
      ]) {
        client.removeQueries({ queryKey: [prefix, version.id] });
      }
      await Promise.all([
        refetchList(version.instanceVersionId),
        client.invalidateQueries({ queryKey: INSTANCE_MENU_KEY }),
      ]);
    },
  });

  return {
    create,
    duplicate,
    discard,
    run,
    simulate,
    remove,
    /** One `PATCH`; the answer replaces the cached version. */
    patch: async (id: string, changes: PricingChanges) => {
      const answer = await savePricingDraft(gateways, id, changes);
      await keepAnswer(answer);
      return answer;
    },
  };
}
