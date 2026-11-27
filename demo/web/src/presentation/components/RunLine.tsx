import type { InstanceMenuEntry } from '../../domain/city-instance';
import {
  elapsedSeconds,
  NO_RUN,
  runLineBuilding,
  runLineReady,
  runLineSilent,
  subjectName,
} from '../../domain/run-text';
import styles from './RunLine.module.css';
import { type EndedBuildTracker, useActiveRuns, useEndedBuild, useNow } from '../hooks/useRuns';

/**
 * The menu's run line: the run in progress with its clock and the runs queued behind it, the
 * runner not answering, or the build that ended while another view was open. No pop-up.
 */
export function RunLine({
  entries,
  openVersionId,
  onOpen,
  className,
  tracker,
}: {
  entries: readonly InstanceMenuEntry[];
  /** The version whose L-1 is the open view; null for any other view. */
  openVersionId: string | null;
  onOpen: (instanceId: string, number: number) => void;
  className?: string;
  /** The ended build, remembered by a component that stays mounted while the menu is closed. */
  tracker?: EndedBuildTracker;
}) {
  const { runs, answeredAt } = useActiveRuns();
  // Without a tracker from a component that stays mounted, the line remembers on its own.
  const own = useEndedBuild(openVersionId, tracker === undefined);
  const { ended, clear } = tracker ?? own;

  const running = runs.find((run) => run.state === 'running');
  const queued = runs.filter((run) => run.state === 'queued');
  const head = running ?? queued[0] ?? null;
  const ticking = head?.runner.alive === true;
  const now = useNow(ticking, answeredAt);

  let text = NO_RUN;
  let open: { readonly instanceId: string; readonly number: number } | null = null;
  if (head !== null) {
    const name = subjectName(head, entries);
    text = !head.runner.alive
      ? runLineSilent(name)
      : running === undefined
        ? NO_RUN
        : runLineBuilding(
            name,
            elapsedSeconds(head, answeredAt, Math.max(now, answeredAt)),
            queued.length,
            head.kind,
          );
  } else if (ended !== null && openVersionId !== ended.versionId) {
    const name = subjectName(
      { subject: { type: 'instance_version', id: ended.versionId } },
      entries,
    );
    text = runLineReady(name);
    for (const entry of entries) {
      const version = entry.versions.find((candidate) => candidate.id === ended.versionId);
      if (version !== undefined) open = { instanceId: entry.id, number: version.number };
    }
  }

  return (
    <p className={className}>
      {open === null ? (
        text
      ) : (
        <>
          {text} ·{' '}
          <button
            type="button"
            className={styles.open}
            onClick={() => {
              clear();
              onOpen(open.instanceId, open.number);
            }}
          >
            Open
          </button>
        </>
      )}
    </p>
  );
}
