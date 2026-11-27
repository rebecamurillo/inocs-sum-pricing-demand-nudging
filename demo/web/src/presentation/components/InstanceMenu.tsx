import type { KeyboardEvent } from 'react';
import type { InstanceMenuEntry } from '../../domain/city-instance';
import { collapsedCount, latestVersion, menuVersionState, versionTag } from '../../domain/l1-text';
import { instanceDeleteAction, instanceDeleteQuestion } from '../../domain/delete-text';
import {
  NEW_PRICING_VERSION,
  pricingMenuState,
  pricingRowLetter,
  pricingVersionName,
} from '../../domain/pricing-goals-text';
import type { LabRoute } from '../../domain/route';
import { PRICING_VERSIONS_OFF } from '../../domain/run-text';
import { useDeleteActions } from '../hooks/useCityInstances';
import { useNewPricingVersion } from '../hooks/useNewPricingVersion';
import { usePricingList } from '../hooks/usePricingVersions';
import { DeleteConfirm } from './DeleteConfirm';
import styles from './InstanceMenu.module.css';

interface InstanceMenuProps {
  readonly entries: readonly InstanceMenuEntry[];
  /** The version the Lab shows, when it is one the menu lists. */
  readonly open: { readonly instanceId: string; readonly versionId: string } | null;
  /** True while the open version's set-up card (L-1) is the current view. */
  readonly setupCurrent: boolean;
  /** The letter of the pricing version the Lab shows (L-2 or L-3), when it shows one. */
  readonly currentLetter?: string | null;
  /** The place in line of each queued run, by subject id: 2 is "2nd", the running run being 1st. */
  readonly queued?: ReadonlyMap<string, number>;
  readonly onOpenVersion: (instanceId: string, number: number) => void;
  /** Any link of the Lab: a pricing row opens its L-2 or L-3 route. */
  readonly onNavigate: (route: LabRoute) => void;
  /** The whole instance was deleted: leave it. */
  readonly onInstanceDeleted?: (instanceId: string, versionIds: readonly string[]) => void;
  readonly onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
}

/** The pricing versions of every version of the instance: they go with it. */
function pricingTotal(entry: InstanceMenuEntry): number {
  return entry.versions.reduce((sum, version) => sum + version.pricingVersionCount, 0);
}

/** The pricing versions of the open instance version, and "+ New pricing version". */
function PricingRows({
  instance,
  currentLetter,
  queued,
  onNavigate,
  onKeyDown,
}: {
  instance: { readonly id: string; readonly instanceId: string; readonly number: number };
  currentLetter: string | null;
  queued: ReadonlyMap<string, number> | undefined;
  onNavigate: (route: LabRoute) => void;
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
}) {
  const list = usePricingList(instance.id);
  const creating = useNewPricingVersion(instance, onNavigate);
  const ref = { instanceId: instance.instanceId, version: instance.number };
  return (
    <>
      {(list.data ?? []).map((version) => {
        const letter = pricingRowLetter(version);
        return (
          <button
            key={version.id}
            type="button"
            data-menu-item=""
            className={styles.item}
            aria-current={currentLetter === version.letter ? 'page' : undefined}
            onKeyDown={onKeyDown}
            onClick={() => {
              onNavigate({
                kind: version.state === 'result' ? 'result' : 'pricing',
                instance: ref,
                letter: version.letter,
                period: null,
              });
            }}
          >
            <span>{pricingVersionName(version)}</span>{' '}
            {letter !== null && <span className={styles.tag}>{letter}</span>}{' '}
            <span className={styles.state} data-state={version.state}>
              {pricingMenuState(version.state, queued?.get(version.id) ?? null)}
            </span>
          </button>
        );
      })}
      <button
        type="button"
        data-menu-item=""
        className={styles.item}
        disabled={creating.pending}
        onKeyDown={onKeyDown}
        onClick={creating.start}
      >
        {NEW_PRICING_VERSION}
      </button>
      {creating.error !== null && <p className={styles.caption}>{creating.error}</p>}
    </>
  );
}

/** The instances under "City instances": the open one expanded, the others with a version count. */
export function InstanceMenu({
  entries,
  open,
  setupCurrent,
  currentLetter = null,
  queued,
  onOpenVersion,
  onNavigate,
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
                        pricingTotal(entry),
                      )}
                      action={instanceDeleteAction(entry.name)}
                      remove={() =>
                        deletions.deleteInstance({
                          id: entry.id,
                          includingPricingVersions: pricingTotal(entry) > 0,
                        })
                      }
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
                    {version.state === 'ready' ? (
                      <PricingRows
                        instance={{ id: version.id, instanceId: entry.id, number: version.number }}
                        currentLetter={currentLetter}
                        queued={queued}
                        onNavigate={onNavigate}
                        onKeyDown={onKeyDown}
                      />
                    ) : (
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
