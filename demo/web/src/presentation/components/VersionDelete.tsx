import { serialiseRoute } from '../../domain/route';
import { versionDeleteAction, versionDeleteQuestion } from '../../domain/delete-text';
import { useDeleteActions } from '../hooks/useCityInstances';
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
  return (
    <DeleteConfirm
      question={versionDeleteQuestion(instanceName, number, pricingVersionLetters)}
      action={versionDeleteAction(number, pricingVersionLetters.length)}
      remove={() =>
        actions.deleteVersion({
          id: versionId,
          includingPricingVersions: pricingVersionLetters.length > 0,
        })
      }
      onDeleted={() => {
        window.location.hash = serialiseRoute({ kind: 'lab', period: null });
        actions.forget([versionId]);
      }}
    />
  );
}
