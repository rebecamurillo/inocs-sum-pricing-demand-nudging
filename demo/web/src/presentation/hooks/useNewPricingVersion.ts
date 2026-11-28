import { useState } from 'react';
import type { LabRoute } from '../../domain/route';
import { usePricingActions } from './usePricingVersions';

/** "+ New pricing version": starts the draft on a built instance version and opens its L-2 route. */
export function useNewPricingVersion(
  instance: { readonly id: string; readonly instanceId: string; readonly number: number },
  onNavigate: (route: LabRoute) => void,
) {
  const actions = usePricingActions();
  const [error, setError] = useState<string | null>(null);

  const start = () => {
    setError(null);
    actions.create.mutateAsync(instance.id).then(
      (draft) => {
        onNavigate({
          kind: 'pricing',
          instance: { instanceId: instance.instanceId, version: instance.number },
          letter: draft.letter,
          period: null,
        });
      },
      (reason: unknown) => {
        setError(reason instanceof Error ? reason.message : String(reason));
      },
    );
  };

  return { start, pending: actions.create.isPending, error };
}
