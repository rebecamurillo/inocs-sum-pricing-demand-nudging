import type { KeyboardEvent } from 'react';
import type { InstanceMenuEntry } from '../../domain/city-instance';
import { collapsedCount, latestVersion, menuVersionState, versionTag } from '../../domain/l1-text';
import styles from './InstanceMenu.module.css';

interface InstanceMenuProps {
  readonly entries: readonly InstanceMenuEntry[];
  /** The version the Lab shows, when it is one the menu lists. */
  readonly open: { readonly instanceId: string; readonly versionId: string } | null;
  /** True while the open version's set-up card (L-1) is the current view. */
  readonly setupCurrent: boolean;
  readonly onOpenVersion: (instanceId: string, number: number) => void;
  readonly onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
}

/** The instances under "City instances": the open one expanded, the others with a version count. */
export function InstanceMenu({
  entries,
  open,
  setupCurrent,
  onOpenVersion,
  onKeyDown,
}: InstanceMenuProps) {
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
            {entry.versions.map((version) => (
              <div key={version.id}>
                <button
                  type="button"
                  data-menu-item=""
                  className={styles.item}
                  onKeyDown={onKeyDown}
                  onClick={() => {
                    onOpenVersion(entry.id, version.number);
                  }}
                >
                  <span aria-hidden="true">▾</span>
                  <span>{entry.name}</span>{' '}
                  <span className={styles.tag}>{versionTag(version.number)}</span>{' '}
                  <span className={styles.state} data-state={version.state}>
                    {menuVersionState(version.state)}
                  </span>
                </button>
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
