import { useState } from 'react';
import type { InstanceVersion } from '../../domain/city-instance';
import { oneDraftMessage, versionNumberOf } from '../../domain/draft-text';
import { useDraftActions } from './useCityInstances';

/** Where "Edit as a new version" leads: the draft, and the sentence to show when it already existed. */
export interface OpenedDraft {
  readonly instanceId: string;
  readonly number: number;
  readonly message: string | null;
}

/** "Edit as a new version" of a saved version: opens the draft based on it, or the one the instance has. */
export function useEditAsNewVersion(
  version: InstanceVersion,
  onOpenDraft?: (draft: OpenedDraft) => void,
) {
  const actions = useDraftActions();
  const [error, setError] = useState<string | null>(null);

  const edit = () => {
    setError(null);
    actions.draft.mutateAsync({ instanceId: version.instanceId, basedOnId: version.id }).then(
      (opened) => {
        const based =
          opened.version.basedOnId === null ? null : versionNumberOf(opened.version.basedOnId);
        onOpenDraft?.({
          instanceId: version.instanceId,
          number: opened.version.number,
          message:
            opened.existed && based !== null
              ? oneDraftMessage(based, opened.version.createdAt)
              : null,
        });
      },
      (reason: unknown) => {
        setError(reason instanceof Error ? reason.message : String(reason));
      },
    );
  };

  return { edit, pending: actions.draft.isPending, error };
}
