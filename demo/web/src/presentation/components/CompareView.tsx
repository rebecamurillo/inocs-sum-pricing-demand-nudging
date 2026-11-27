import { useEffect, useMemo, useState } from 'react';
import {
  comparisonColumns,
  initialLetters,
  olderRuleOf,
  packageCommits,
  topPairDifferences,
  type ComparedVersion,
  type Comparison,
  type ComparisonColumn,
} from '../../domain/comparison';
import {
  BARS_TITLE,
  COMPARE_BRIEF,
  COMPARE_OFF,
  SAME_BASIS_NOTE,
  SIMULATION_SOURCE,
  TABLE_CAPTION,
  buildsNotice,
  columnLabel,
  columnShares,
  compareScopeLine,
  flatColumnHeader,
  flatPill,
  insightTitle,
  olderRuleNotice,
  olderRuleSuffix,
  pillLabel,
  sharesSummary,
  simulateLetterAgain,
  tableGroups,
  type CompareMeasure,
  type TableCell,
} from '../../domain/comparison-text';
import type { GeoPoint } from '../../domain/map';
import { versionTag } from '../../domain/l1-text';
import {
  simulatingLine,
  simulationOffReason,
  STORED_RESULTS_STAY,
} from '../../domain/older-rule-text';
import { NEW_PRICING_VERSION, pricingVersionName } from '../../domain/pricing-goals-text';
import { compareRoute, type LabRoute } from '../../domain/route';
import { elapsedSeconds, queuedSentence, subjectName } from '../../domain/run-text';
import { PLACEHOLDER_SENTENCE, THREE_MODES_SENTENCE } from '../../domain/result-text';
import { missingPricingVersionLabel, nothingAtThisLink } from '../../domain/unknown-link';
import type { InstanceHub } from '../../application/ports/city-instance-gateway';
import { useInstanceGeometry, useInstanceMenu, useInstanceView } from '../hooks/useCityInstances';
import { useNewPricingVersion } from '../hooks/useNewPricingVersion';
import {
  useComparison,
  usePricingActions,
  usePricingList,
  useSimulationEnd,
} from '../hooks/usePricingVersions';
import { useActiveRuns, useNow } from '../hooks/useRuns';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { CompareDifferences } from './CompareDifferences';
import { CompareMap } from './CompareMap';
import { LoadingCard } from './LoadingCard';
import { Legend, BarList, StackedBar } from './StackedBars';
import { SourceTag } from './SourceTag';
import styles from './CompareView.module.css';

const NO_HUBS: readonly InstanceHub[] = [];

interface CompareViewProps {
  readonly instanceVersionId: string;
  readonly instanceId: string;
  readonly number: number;
  /** The letters of the route; null when L-4 is opened without any (the menu's "Compare versions"). */
  readonly letters: readonly string[] | null;
  readonly period: string | null;
  readonly advancedView: boolean;
  readonly onAdvancedView: (on: boolean) => void;
  readonly onNavigate: (route: LabRoute) => void;
  /** Rewrites the hash in place: no history entry, no reload. */
  readonly onReplace: (route: LabRoute) => void;
}

/** "Simulate {x} again" of a version simulated with an older rule, and the run it starts. */
function OlderRuleNotice({ version, rule }: { version: ComparedVersion; rule: number }) {
  const { runs, answeredAt } = useActiveRuns();
  const menu = useInstanceMenu().data ?? [];
  const status = useSystemStatus().data;
  const pricing = usePricingActions();
  const [refused, setRefused] = useState<string | null>(null);
  const simulation = runs.find((run) => run.kind === 'simulation' && run.subject.id === version.id);
  const ended = useSimulationEnd(version.id, simulation?.id ?? null);
  const now = useNow(simulation?.state === 'running' && simulation.runner.alive, answeredAt);
  const off = status?.canSimulate.allowed === false ? status.canSimulate : null;
  const offReason = off === null ? null : simulationOffReason(off);
  const ahead =
    runs.find((run) => run.state === 'running') ??
    runs.find((run) => run.state === 'queued' && run.id !== simulation?.id);

  let line = null;
  if (simulation?.state === 'running') {
    line = (
      <p className={styles.simulating} role="status">
        {simulatingLine(elapsedSeconds(simulation, answeredAt, now))}
      </p>
    );
  } else if (simulation !== undefined) {
    line = (
      <p className={styles.simulating} role="status">
        {ahead !== undefined && simulation.queuePosition !== null
          ? queuedSentence(simulation.queuePosition + 1, subjectName(ahead, menu), ahead.kind)
          : null}
      </p>
    );
  }

  return (
    <section
      className={styles.notice}
      data-testid="older-rule"
      aria-label={`Version ${version.letter} simulated with an older rule`}
    >
      <p>{olderRuleNotice(version.letter, rule)}</p>
      {line ?? (
        <>
          {offReason !== null && (
            <p className={styles.banner} role="status">
              {offReason} {STORED_RESULTS_STAY}
            </p>
          )}
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.primary}
              disabled={offReason !== null || pricing.simulate.isPending}
              onClick={() => {
                setRefused(null);
                pricing.simulate.mutate(version.id, {
                  onSuccess: (answer) => {
                    if (answer.kind === 'refused') setRefused(answer.detail);
                    else ended.watch(answer.runId);
                  },
                });
              }}
            >
              {simulateLetterAgain(version.letter)}
            </button>
          </div>
          {refused !== null && <p className={styles.error}>{refused}</p>}
          {pricing.simulate.isError && (
            <p className={styles.error}>{pricing.simulate.error.message}</p>
          )}
        </>
      )}
    </section>
  );
}

function isStale(column: ComparisonColumn): boolean {
  return column.kind === 'flat'
    ? !column.reference.ruleCurrent
    : olderRuleOf(column.version) !== null;
}

function staleRule(column: ComparisonColumn): number | null {
  if (column.kind === 'version') return olderRuleOf(column.version);
  return column.reference.ruleCurrent ? null : column.reference.ruleVersion;
}

function Cell({ cell }: { cell: TableCell }) {
  return (
    <td data-best={cell.best ? '' : undefined} data-stale={cell.stale ? '' : undefined}>
      <span className={cell.bold ? styles.bold : undefined}>{cell.text}</span>
      {cell.change !== null && <small className={styles.change}>{cell.change}</small>}
    </td>
  );
}

interface CardProps {
  readonly comparison: Comparison;
  readonly versions: readonly { letter: string; name: string }[];
  readonly ticked: readonly string[];
  readonly advancedView: boolean;
  readonly onAdvancedView: (on: boolean) => void;
  readonly onToggle: (letter: string) => void;
  /** The instance version's study circle and hubs, which the map and the difference table read. */
  /** Null when the instance version could not be read: the map then draws nothing. */
  readonly circle: { readonly centre: GeoPoint; readonly radiusM: number } | null;
  readonly hubs: readonly InstanceHub[];
  /** Held by the view, not the card: a re-read remounts the card under the loading skeleton. */
  readonly measure: CompareMeasure;
  readonly onMeasure: (measure: CompareMeasure) => void;
  readonly shownPair: string | null;
  readonly onShowOnMap: (key: string | null) => void;
}

function CompareCard({
  comparison,
  versions,
  ticked,
  advancedView,
  onAdvancedView,
  onToggle,
  circle,
  hubs,
  measure,
  onMeasure: setMeasure,
  shownPair,
  onShowOnMap: setShownPair,
}: CardProps) {
  const hubLabels = useMemo(() => new Map(hubs.map((hub) => [hub.id, hub.label])), [hubs]);
  const shown = useMemo(() => {
    // Only a pair the table lists: no line stays on the map without its "Show on map" button.
    const found = topPairDifferences(comparison).find(
      (item) => `${item.originHub}>${item.destinationHub}` === shownPair,
    );
    return found === undefined
      ? null
      : { originHub: found.originHub, destinationHub: found.destinationHub };
  }, [comparison, shownPair]);
  const columns = comparisonColumns(comparison);
  const commits = packageCommits(comparison);
  const stale = columns.flatMap((column) => {
    const rule = staleRule(column);
    return rule === null ? [] : [rule];
  });
  const suffix = [...new Set(stale)].map(olderRuleSuffix).join('');
  const groups = tableGroups(comparison, columns, advancedView);
  const bars = columns.flatMap((column) => {
    const shares = columnShares(comparison, column);
    return shares === null ? [] : [{ column, shares }];
  });
  const full = ticked.length >= 4;
  const least = ticked.length <= 2;

  return (
    <div className={styles.view}>
      <p className={styles.brief}>{COMPARE_BRIEF}</p>

      <ul className={styles.picker} aria-label="Versions to compare">
        {versions.map((item) => {
          const on = ticked.includes(item.letter);
          return (
            <li key={item.letter}>
              <button
                type="button"
                className={styles.pill}
                aria-pressed={on}
                disabled={on ? least : full}
                onClick={() => {
                  onToggle(item.letter);
                }}
              >
                {pillLabel(item.letter, item.name, on)}
              </button>
            </li>
          );
        })}
        {comparison.flatReferences.map((reference) => (
          <li key={reference.id}>
            <span className={styles.flatPill}>{flatPill(reference)}</span>
          </li>
        ))}
      </ul>

      <div className={styles.scopeRow}>
        <p className={styles.scope}>
          {compareScopeLine(comparison.instanceVersion.name, comparison.period.name)}
        </p>
        <button
          type="button"
          role="switch"
          aria-checked={advancedView}
          className={styles.switch}
          onClick={() => {
            onAdvancedView(!advancedView);
          }}
        >
          <span className={styles.switchTrack} aria-hidden="true" />
          Advanced view
        </button>
      </div>

      {commits.length > 1 && (
        <section className={styles.notice} aria-label="Different builds of the pricing model">
          <p>{buildsNotice(commits)}</p>
        </section>
      )}
      {comparison.versions.map((version) => {
        const rule = olderRuleOf(version);
        return rule === null ? null : (
          <OlderRuleNotice key={version.id} version={version} rule={rule} />
        );
      })}

      <section className={styles.group} data-testid="simulation-bars">
        <div className={styles.tagRow}>
          <SourceTag kind="simulation" />
          <p className={styles.source}>
            {SIMULATION_SOURCE}
            {suffix}
          </p>
        </div>
        <h2 className={styles.insight}>{insightTitle(comparison)}</h2>
        <BarList label={BARS_TITLE} className={styles.bars}>
          {bars.map(({ column, shares }) => (
            <StackedBar
              key={column.kind === 'flat' ? `flat-${column.reference.id}` : column.version.letter}
              label={columnLabel(column, comparison.flatReferences)}
              counts={{
                car: 100 * shares.car,
                ptOnly: 100 * shares.ptOnly,
                ptBike: 100 * shares.ptBike,
              }}
              total={100}
              summary={sharesSummary(shares)}
              stale={isStale(column)}
            />
          ))}
        </BarList>
        <Legend />
        <p className={styles.caption}>
          {PLACEHOLDER_SENTENCE} {THREE_MODES_SENTENCE}
        </p>
      </section>

      <div
        className={styles.tableWrap}
        role="region"
        aria-label="Comparison of the versions"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region must be reachable by keyboard
        tabIndex={0}
        data-testid="compare-table"
      >
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.rowLabel} scope="col">
                <span className={styles.hidden}>Row</span>
              </th>
              {columns.map((column) => (
                <th
                  key={
                    column.kind === 'flat' ? `flat-${column.reference.id}` : column.version.letter
                  }
                  scope="col"
                  data-stale={isStale(column) ? '' : undefined}
                  data-column={column.kind}
                >
                  {column.kind === 'flat'
                    ? flatColumnHeader(column.reference, comparison.flatReferences)
                    : `Version ${column.version.letter} · ${column.version.name}`}
                </th>
              ))}
            </tr>
          </thead>
          {groups.map((group) => (
            <tbody key={group.name} data-group={group.name} data-testid={`group-${group.name}`}>
              <tr>
                <th
                  className={[styles.rowLabel, styles.groupHead].join(' ')}
                  scope="rowgroup"
                  data-testid={`group-head-${group.name}`}
                >
                  <span className={styles.tagRow}>
                    {group.tag !== null && <SourceTag kind={group.tag} />}
                    <span>{group.title}</span>
                  </span>
                  {group.source !== null && (
                    <span className={styles.rowNote}>
                      {group.source}
                      {suffix}
                    </span>
                  )}
                </th>
                <td className={styles.groupFill} colSpan={columns.length} />
              </tr>
              {group.rows.map((row) => (
                <tr key={row.key} data-row={row.key} data-testid={`row-${group.name}-${row.key}`}>
                  <th
                    className={styles.rowLabel}
                    scope="row"
                    data-testid={`row-label-${group.name}-${row.key}`}
                  >
                    {row.label}
                    {row.tag !== null && (
                      <>
                        {' '}
                        <SourceTag kind="model" />
                      </>
                    )}
                    {row.note !== null && <span className={styles.rowNote}>{row.note}</span>}
                  </th>
                  {row.cells.map((cell, at) => (
                    <Cell key={at} cell={cell} />
                  ))}
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
      <p className={styles.caption}>{TABLE_CAPTION}</p>
      <CompareDifferences
        comparison={comparison}
        hubLabels={hubLabels}
        shownPair={shownPair}
        onShowOnMap={setShownPair}
      />
      {circle !== null && (
        <CompareMap
          centre={circle.centre}
          radiusM={circle.radiusM}
          hubs={hubs}
          differences={comparison.hubDifferences}
          a={comparison.pairDifferences.a}
          b={comparison.pairDifferences.b}
          measure={measure}
          onMeasure={setMeasure}
          shownPair={shown}
        />
      )}
      <div className={styles.actions}>
        <span className={styles.note}>{SAME_BASIS_NOTE}</span>
      </div>
    </div>
  );
}

/** L-4: two to four finished versions of one instance version side by side, against their flat-price simulations. */
export function CompareView(props: CompareViewProps) {
  const { instanceVersionId, instanceId, number, letters, period, onNavigate, onReplace } = props;
  const list = usePricingList(instanceVersionId);
  const view = useInstanceView(instanceVersionId);
  const geometry = useInstanceGeometry(instanceVersionId);
  const [measure, setMeasure] = useState<CompareMeasure>('priceDifference');
  // The pair shown belongs to the two versions it was picked between: another pair of versions
  // shows none, so no line stays on the map without its "Show on map" button.
  const [picked, setPicked] = useState<{ readonly ab: string; readonly key: string } | null>(null);
  const creating = useNewPricingVersion({ id: instanceVersionId, instanceId, number }, onNavigate);
  const instance = { instanceId, version: number };

  const finished = (list.data ?? []).filter((item) => item.state === 'result');
  const finishedLetters = finished.map((item) => item.letter);
  const sorted = letters === null ? [] : [...new Set(letters)].sort();
  const unknown = sorted.find((letter) => !finishedLetters.includes(letter)) ?? null;
  const canRead =
    list.data !== undefined &&
    finishedLetters.length >= 2 &&
    sorted.length >= 2 &&
    unknown === null;
  const comparison = useComparison(canRead ? instanceVersionId : null, sorted, period);

  const canonical = letters !== null && letters.join(',') !== sorted.join(',');
  // Opened without letters (the menu, on another view's link): go to the compare route, a new
  // history entry as any other view. Letters out of order: write the route's one spelling in place.
  const open = letters === null && list.data !== undefined && finishedLetters.length >= 2;
  useEffect(() => {
    if (open) {
      onNavigate(compareRoute(instance, initialLetters(finishedLetters, null), period));
    } else if (canonical && canRead) {
      onReplace(compareRoute(instance, sorted, period));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the route is written once per link
  }, [open, canonical, canRead, sorted.join(','), finishedLetters.join(',')]);

  if (list.isPending || view.isPending) return <LoadingCard />;
  if (list.data === undefined) {
    return <p className={styles.error}>The versions could not be read: {list.error.message}</p>;
  }
  const instanceLabel = `${view.data?.instanceName ?? instanceId} ${versionTag(number)}`;

  if (finishedLetters.length < 2) {
    return (
      <div className={styles.view}>
        <p className={styles.brief}>{COMPARE_BRIEF}</p>
        <p className={styles.offText}>{COMPARE_OFF}</p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.primary}
            disabled={creating.pending}
            onClick={creating.start}
          >
            {NEW_PRICING_VERSION}
          </button>
        </div>
        {creating.error !== null && <p className={styles.error}>{creating.error}</p>}
      </div>
    );
  }
  if (unknown !== null) {
    return <p>{nothingAtThisLink(instanceLabel, missingPricingVersionLabel(unknown))}</p>;
  }
  if (letters === null || comparison.data === undefined) {
    if (comparison.isError) {
      return (
        <p className={styles.error}>The comparison could not be read: {comparison.error.message}</p>
      );
    }
    return <LoadingCard />;
  }

  const toggle = (letter: string) => {
    const next = sorted.includes(letter)
      ? sorted.filter((item) => item !== letter)
      : [...sorted, letter];
    onReplace(compareRoute(instance, next, period));
  };
  const ab = `${comparison.data.pairDifferences.a},${comparison.data.pairDifferences.b}`;
  const card = (
    <CompareCard
      measure={measure}
      onMeasure={setMeasure}
      shownPair={picked?.ab === ab ? picked.key : null}
      onShowOnMap={(key) => {
        setPicked(key === null ? null : { ab, key });
      }}
      comparison={comparison.data}
      versions={finished.map((item) => ({ letter: item.letter, name: pricingVersionName(item) }))}
      ticked={sorted}
      advancedView={props.advancedView}
      onAdvancedView={props.onAdvancedView}
      onToggle={toggle}
      circle={
        view.data === undefined || view.data === null
          ? null
          : {
              centre: {
                lat: view.data.version.parameters.centerLat,
                lon: view.data.version.parameters.centerLon,
              },
              radiusM: view.data.version.parameters.radiusM,
            }
      }
      hubs={geometry.data?.hubs ?? NO_HUBS}
    />
  );
  // A read in flight keeps the earlier render at 50 % opacity under the skeleton.
  return comparison.isFetching ? <LoadingCard previous={card} /> : card;
}
