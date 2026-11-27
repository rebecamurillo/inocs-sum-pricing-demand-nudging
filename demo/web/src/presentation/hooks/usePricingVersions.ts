import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import {
  discardPricingDraft,
  newPricingVersion,
  runPricingVersion,
  savePricingDraft,
} from '../../application/use-cases/edit-pricing-draft';
import type { PricingChanges, PricingVersion } from '../../domain/pricing-version';
import { useGateways } from './gateways';
import { INSTANCE_MENU_KEY } from './useCityInstances';
import { ACTIVE_RUNS_KEY, useActiveRuns } from './useRuns';

export const pricingListKey = (instanceVersionId: string | null) =>
  ['pricing-list', instanceVersionId] as const;
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

  return {
    create,
    discard,
    run,
    /** One `PATCH`; the answer replaces the cached version. */
    patch: async (id: string, changes: PricingChanges) => {
      const answer = await savePricingDraft(gateways, id, changes);
      await keepAnswer(answer);
      return answer;
    },
  };
}
