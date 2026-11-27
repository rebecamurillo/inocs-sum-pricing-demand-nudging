import { serialiseRoute } from '../../domain/route';
import { versionDeleteAction, versionDeleteQuestion } from '../../domain/delete-text';
import { useDeleteActions } from '../hooks/useCityInstances';
import { DeleteConfirm } from './DeleteConfirm';

/** "Delete…" of L-1: this version only; on 204 the visitor is on `#/lab`. */
export function VersionDelete({
  versionId,
  instanceName,
  number,
}: {
  versionId: string;
  instanceName: string;
  number: number;
}) {
  const actions = useDeleteActions();
  return (
    <DeleteConfirm
      question={versionDeleteQuestion(instanceName, number)}
      action={versionDeleteAction(number)}
      remove={() => actions.deleteVersion(versionId)}
      onDeleted={() => {
        window.location.hash = serialiseRoute({ kind: 'lab', period: null });
        actions.forget([versionId]);
      }}
    />
  );
}
