import { serialiseRoute } from '../../domain/route';
import { versionDeleteAction, versionDeleteQuestion } from '../../domain/delete-text';
import { useDeleteActions } from '../hooks/useCityInstances';
import { useShowcaseHold } from '../hooks/useShowcase';
import { showcaseHolders } from '../../domain/showcase';
import { DeleteConfirm } from './DeleteConfirm';

/** "Delete…" of L-1: this version only; on 204 the visitor is on `#/lab`. */
export function VersionDelete({
  versionId,
  instanceName,
  number,
  pricingVersionLetters = [],
}: {
  versionId: string;
  instanceName: string;
  number: number;
  /** The pricing versions that go with it: an unbuilt version has none. */
  pricingVersionLetters?: readonly string[];
}) {
  const actions = useDeleteActions();
  const hold = useShowcaseHold(
    (showcase) => showcaseHolders(showcase.pricingVersionId).instanceVersionId === versionId,
  );
  return (
    <DeleteConfirm
      question={versionDeleteQuestion(instanceName, number, pricingVersionLetters)}
      action={versionDeleteAction(number, pricingVersionLetters.length)}
      blockedNote={hold.blockedNote}
      refusalNote={hold.refusalNote}
      remove={() =>
        actions
          .deleteVersion({
            id: versionId,
            includingPricingVersions: pricingVersionLetters.length > 0,
          })
          .then(hold.afterAnswer)
      }
      onDeleted={() => {
        window.location.hash = serialiseRoute({ kind: 'lab', period: null });
        actions.forget([versionId]);
      }}
    />
  );
}
