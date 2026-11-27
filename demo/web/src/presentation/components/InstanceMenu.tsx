import type { KeyboardEvent } from 'react';
import type { InstanceMenuEntry } from '../../domain/city-instance';
import { collapsedCount, latestVersion, menuVersionState, versionTag } from '../../domain/l1-text';
import { instanceDeleteAction, instanceDeleteQuestion } from '../../domain/delete-text';
import { PRICING_VERSIONS_OFF } from '../../domain/run-text';
import { useDeleteActions } from '../hooks/useCityInstances';
import { DeleteConfirm } from './DeleteConfirm';
import styles from './InstanceMenu.module.css';

interface InstanceMenuProps {
  readonly entries: readonly InstanceMenuEntry[];
  /** The version the Lab shows, when it is one the menu lists. */
  readonly open: { readonly instanceId: string; readonly versionId: string } | null;
  /** True while the open version's set-up card (L-1) is the current view. */
  readonly setupCurrent: boolean;
  /** The place in line of each queued build, by version id: 2 is "2nd", the running run being 1st. */
  readonly queued?: ReadonlyMap<string, number>;
  readonly onOpenVersion: (instanceId: string, number: number) => void;
  /** The whole instance was deleted: leave it. */
  readonly onInstanceDeleted?: (instanceId: string, versionIds: readonly string[]) => void;
  readonly onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
}

/** The instances under "City instances": the open one expanded, the others with a version count. */
export function InstanceMenu({
  entries,
  open,
  setupCurrent,
  queued,
  onOpenVersion,
  onInstanceDeleted,
  onKeyDown,
}: InstanceMenuProps) {
  const deletions = useDeleteActions();
  if (entries.length === 0) return <p className={styles.hint}>No instance yet</p>;

  return (
    <>
      {entries.map((entry) => {
        if (entry.id !== open?.instanceId) {
          const latest = latestVersion(entry);
          return (
            <button
              key={entry.id}
              type="button"
              data-menu-item=""
              className={styles.item}
              onKeyDown={onKeyDown}
              onClick={() => {
                if (latest !== null) onOpenVersion(entry.id, latest.number);
              }}
            >
              <span aria-hidden="true">▸</span>
              <span>{entry.name}</span>{' '}
              {latest !== null && <span className={styles.tag}>{versionTag(latest.number)}</span>}{' '}
              <span className={styles.state}>{collapsedCount(entry.versions.length)}</span>
            </button>
          );
        }
        return (
          <div key={entry.id}>
            {entry.versions.map((version, at) => (
              <div key={version.id}>
                <div className={styles.row}>
                  <button
                    type="button"
                    data-menu-item=""
                    className={[styles.item, styles.rowItem].join(' ')}
                    onKeyDown={onKeyDown}
                    onClick={() => {
                      onOpenVersion(entry.id, version.number);
                    }}
                  >
                    <span aria-hidden="true">▾</span>
                    <span>{entry.name}</span>{' '}
                    <span className={styles.tag}>{versionTag(version.number)}</span>{' '}
                    <span className={styles.state} data-state={version.state}>
                      {menuVersionState(version.state, queued?.get(version.id) ?? null)}
                    </span>
                  </button>
                  {at === 0 && (
                    <DeleteConfirm
                      question={instanceDeleteQuestion(
                        entry.name,
                        entry.versions.map((item) => item.number),
                      )}
                      action={instanceDeleteAction(entry.name)}
                      remove={() => deletions.deleteInstance(entry.id)}
                      onDeleted={() => {
                        const ids = entry.versions.map((item) => item.id);
                        onInstanceDeleted?.(entry.id, ids);
                        deletions.forget(ids);
                      }}
                      onMenuKeyDown={onKeyDown}
                    />
                  )}
                </div>
                {version.id === open.versionId && (
                  <div className={styles.sub}>
                    <button
                      type="button"
                      data-menu-item=""
                      className={styles.item}
                      aria-current={setupCurrent ? 'page' : undefined}
                      onKeyDown={onKeyDown}
                      onClick={() => {
                        onOpenVersion(entry.id, version.number);
                      }}
                    >
                      Instance set-up
                    </button>
                    <p className={styles.caption}>Pricing versions</p>
                    {version.state !== 'ready' && (
                      <p className={styles.caption}>{PRICING_VERSIONS_OFF}</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        );
      })}
    </>
  );
}
