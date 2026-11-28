import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';
import { loadShowcase } from '../../application/use-cases/load-showcase';
import { setShowcase } from '../../application/use-cases/set-showcase';
import type { Showcase } from '../../domain/showcase';
import { RUN_ACTIVE_NOTE } from '../../domain/delete-text';
import { SHOWCASE_HELD_FALLBACK, showcaseHeldNote } from '../../domain/showcase-text';
import { useGateways } from './gateways';

const SHOWCASE_KEY = ['showcase'] as const;

/**
 * The home page's showcase, read once per visit: no polling, no previous data kept. Home and the
 * Lab read it with the same options, so they share one query while both are mounted.
 */
export function useShowcase() {
  const { pricing } = useGateways();
  return useQuery({
    queryKey: SHOWCASE_KEY,
    queryFn: () => loadShowcase(pricing),
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: Infinity,
    gcTime: 0,
  });
}

/** Makes a finished version's result the showcase, then refetches it. */
export function useSetShowcase() {
  const { pricing } = useGateways();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (call: { pricingVersionId: string; periodId: string }) =>
      setShowcase(pricing, call.pricingVersionId, call.periodId),
    onSuccess: () => client.invalidateQueries({ queryKey: SHOWCASE_KEY }),
  });
}

/**
 * What stops "Delete…" of an instance version or an instance that holds the showcase: the note to
 * show instead of the confirmation, and the wording of a late `409 is_showcase`.
 */
export function useShowcaseHold(holds: (showcase: Showcase) => boolean) {
  const query = useShowcase();
  const showcase = query.data ?? null;
  const refused = useRef<Showcase | null>(null);
  const noteOf = (held: Showcase | null) =>
    held === null
      ? SHOWCASE_HELD_FALLBACK
      : showcaseHeldNote(held.letter, held.instanceVersionName);
  return {
    /** Set while the target is or holds the showcase. */
    blockedNote: showcase !== null && holds(showcase) ? noteOf(showcase) : null,
    /** After a DELETE answered `is_showcase`, reads the showcase again to name its version. */
    afterAnswer: async <T extends { readonly kind: string }>(answer: T): Promise<T> => {
      if (answer.kind === 'is_showcase') refused.current = (await query.refetch()).data ?? null;
      return answer;
    },
    refusalNote: (kind: string) =>
      kind === 'is_showcase' ? noteOf(refused.current ?? showcase) : RUN_ACTIVE_NOTE,
  };
}
