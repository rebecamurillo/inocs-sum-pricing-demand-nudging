import { useState } from 'react';
import type { InstanceView as InstanceViewValue } from '../../application/use-cases/load-instance-view';
import { L1_BRIEF, L1_SENTENCE, versionTag } from '../../domain/l1-text';
import { RUN_AGAIN, STEP_NAMES, cancelledCard } from '../../domain/run-text';
import { useEditAsNewVersion, type OpenedDraft } from '../hooks/useEditAsNewVersion';
import { useRun, useRunActions } from '../hooks/useRuns';
import { LoadingCard } from './LoadingCard';
import { VersionDelete } from './VersionDelete';
import styles from './BuildingView.module.css';

/** A cancelled build (L-1): where it stopped, and the two ways on. */
export function CancelledCard({
  view,
  onOpenDraft,
}: {
  view: InstanceViewValue;
  onOpenDraft?: (draft: OpenedDraft) => void;
}) {
  const { version, instanceName } = view;
  const { run, isError, error } = useRun(version.buildRunId);
  const actions = useRunActions(version.id);
  const editing = useEditAsNewVersion(version, onOpenDraft);
  const [refused, setRefused] = useState<string | null>(null);

  if (isError) return <p className={styles.error}>The run could not be read: {error?.message}</p>;
  if (run === null) return <LoadingCard />;

  // A run removed from the queue has no step in the `cancelled` state: it stopped before its first.
  const stopped = run.steps.find((step) => step.state === 'cancelled')?.step ?? 'area';
  return (
    <div className={styles.view}>
      <p className={styles.brief}>
        <span className={styles.rhythm}>{L1_BRIEF}</span>
        <span>{L1_SENTENCE}</span>
      </p>
      <div className={styles.head}>
        <h2 className={styles.name}>{instanceName}</h2>
        <span className={styles.tag}>{versionTag(version.number)}</span>
      </div>
      <p className={styles.sentence}>
        {cancelledCard(STEP_NAMES[stopped], run.finishedAt ?? run.serverTime)}
      </p>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.primary}
          disabled={actions.again.isPending}
          onClick={() => {
            setRefused(null);
            actions.again.mutate(undefined, {
              onSuccess: (answer) => {
                if (answer.kind === 'refused') setRefused(answer.detail);
              },
            });
          }}
        >
          {RUN_AGAIN}
        </button>
        <button
          type="button"
          className={styles.secondary}
          disabled={editing.pending}
          onClick={editing.edit}
        >
          Edit as a new version
        </button>
        <VersionDelete versionId={version.id} instanceName={instanceName} number={version.number} />
      </div>
      {refused !== null && <p className={styles.error}>{refused}</p>}
      {actions.again.isError && <p className={styles.error}>{actions.again.error.message}</p>}
      {editing.error !== null && <p className={styles.error}>{editing.error}</p>}
    </div>
  );
}
