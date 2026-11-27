import { versionTag } from '../../domain/l1-text';
import { RUN_ACTIVE_NOTE } from '../../domain/delete-text';
import {
  isShowcaseNote,
  pricingDeleteAction,
  pricingDeleteQuestion,
} from '../../domain/older-rule-text';
import { pricingVersionName } from '../../domain/pricing-goals-text';
import type { PricingVersion } from '../../domain/pricing-version';
import type { LabRoute } from '../../domain/route';
import { usePricingActions } from '../hooks/usePricingVersions';
import { DeleteConfirm } from './DeleteConfirm';

/**
 * "Delete…" of a version with a result, a failure or a cancellation: asks, deletes, and on 204 opens
 * the instance version's L-1; a refusal shows its reason as the note of "Delete…".
 */
export function PricingVersionDelete({
  version,
  instanceName,
  instanceId,
  number,
  onNavigate,
}: {
  version: PricingVersion;
  instanceName: string;
  instanceId: string;
  number: number;
  onNavigate: (route: LabRoute) => void;
}) {
  const pricing = usePricingActions();
  return (
    <DeleteConfirm
      question={pricingDeleteQuestion(
        version.letter,
        pricingVersionName(version),
        `${instanceName} ${versionTag(number)}`,
      )}
      action={pricingDeleteAction(version.letter)}
      remove={() => pricing.remove.mutateAsync(version)}
      refusalNote={(kind) =>
        kind === 'is_showcase' ? isShowcaseNote(version.letter) : RUN_ACTIVE_NOTE
      }
      onDeleted={() => {
        onNavigate({
          kind: 'instance',
          instance: { instanceId, version: number },
          period: null,
        });
      }}
    />
  );
}
