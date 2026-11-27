import type { InstanceMenuEntry } from '../../domain/city-instance';
import { runLineResultReady } from '../../domain/pricing-run-text';
import {
  elapsedSeconds,
  NO_RUN,
  runLineBuilding,
  runLineReady,
  runLineSilent,
  subjectName,
} from '../../domain/run-text';
import styles from './RunLine.module.css';
import { type EndedRunTracker, useActiveRuns, useEndedRun, useNow } from '../hooks/useRuns';

/**
 * The menu's run line: the run in progress with its clock and the runs queued behind it, the
 * runner not answering, or the build that ended while another view was open. No pop-up.
 */
export function RunLine({
  entries,
  openVersionId,
  openPricingId = null,
  onOpen,
  onOpenResult,
  className,
  tracker,
}: {
  entries: readonly InstanceMenuEntry[];
  /** The version whose L-1 is the open view; null for any other view. */
  openVersionId: string | null;
  /** The id of the pricing version whose L-2 or result is the open view; null for any other view. */
  openPricingId?: string | null;
  onOpen: (instanceId: string, number: number) => void;
  /** "Open" on a pricing run that ended: the result route of the version. */
  onOpenResult?: (instanceId: string, number: number, letter: string) => void;
  className?: string;
  /** The ended run, remembered by a component that stays mounted while the menu is closed. */
  tracker?: EndedRunTracker;
}) {
  const { runs, answeredAt } = useActiveRuns();
  // Without a tracker from a component that stays mounted, the line remembers on its own.
  const own = useEndedRun([openVersionId, openPricingId], tracker === undefined);
  const { ended, clear } = tracker ?? own;

  const running = runs.find((run) => run.state === 'running');
  const queued = runs.filter((run) => run.state === 'queued');
  const head = running ?? queued[0] ?? null;
  const ticking = head?.runner.alive === true;
  const now = useNow(ticking, answeredAt);

  let text = NO_RUN;
  let open: {
    readonly instanceId: string;
    readonly number: number;
    readonly letter: string | null;
  } | null = null;
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
  } else if (ended !== null && ![openVersionId, openPricingId].includes(ended.subject.id)) {
    text =
      ended.subject.type === 'pricing_version'
        ? runLineResultReady(subjectName(ended, entries))
        : runLineReady(subjectName(ended, entries));
    for (const entry of entries) {
      for (const version of entry.versions) {
        if (ended.subject.type === 'instance_version' && version.id === ended.subject.id) {
          open = { instanceId: entry.id, number: version.number, letter: null };
        }
        const prefix = `${version.id}.`;
        if (ended.subject.type === 'pricing_version' && ended.subject.id.startsWith(prefix)) {
          open = {
            instanceId: entry.id,
            number: version.number,
            letter: ended.subject.id.slice(prefix.length),
          };
        }
      }
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
              if (open.letter === null) onOpen(open.instanceId, open.number);
              else onOpenResult?.(open.instanceId, open.number, open.letter);
            }}
          >
            Open
          </button>
        </>
      )}
    </p>
  );
}
