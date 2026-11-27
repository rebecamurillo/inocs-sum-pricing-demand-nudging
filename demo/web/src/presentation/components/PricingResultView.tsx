import { useMemo, useState } from 'react';
import { HUB_PAIRS_LINK, hubPairCounts, type MapMeasure } from '../../domain/hub-pair-table';
import { groupThousands, versionTag } from '../../domain/l1-text';
import type { GeoPoint } from '../../domain/map';
import { pricingVersionName } from '../../domain/pricing-goals-text';
import { periodTravellers, sumModes, type PricingResult } from '../../domain/pricing-result';
import { initialLetters } from '../../domain/comparison';
import { COMPARE_VERSIONS } from '../../domain/comparison-text';
import { pricingVersionId, type PricingVersion } from '../../domain/pricing-version';
import { compareRoute, serialiseRoute, type LabRoute } from '../../domain/route';
import {
  GOALS_TITLE,
  MODEL_SPLIT_TITLE,
  NO_STORED_RESULT,
  PLACEHOLDER_SENTENCE,
  RESULT_BRIEF,
  RESULT_SENTENCE,
  SIMULATION_SOURCE,
  THREE_MODES_SENTENCE,
  WHY_IT_DIFFERS,
  captionParts,
  carShareChangePoints,
  flatBarLabel,
  goalTiles,
  insightTitle,
  modelBarLabel,
  scopeLine,
  versionBarLabel,
} from '../../domain/result-text';
import {
  STORED_RESULTS_STAY,
  olderRule,
  olderRuleBox,
  olderRuleSuffix,
  simulateAgainLabel,
  simulatingLine,
  simulationOffReason,
} from '../../domain/older-rule-text';
import { DUPLICATE } from '../../domain/pricing-run-text';
import { elapsedSeconds, queuedSentence, subjectName } from '../../domain/run-text';
import { missingPricingVersionLabel, nothingAtThisLink } from '../../domain/unknown-link';
import { useInstanceMenu, useInstanceView } from '../hooks/useCityInstances';
import {
  usePricingActions,
  usePricingList,
  useHubPairResults,
  useHubResults,
  usePricingResult,
  usePricingSimulations,
  usePricingVersion,
  useSimulationEnd,
} from '../hooks/usePricingVersions';
import { useActiveRuns, useNow } from '../hooks/useRuns';
import { useCurrentSimulationRule, useSystemStatus } from '../hooks/useSystemStatus';
import { HubPairTable } from './HubPairTable';
import { LoadingCard } from './LoadingCard';
import { ResultAdvanced } from './ResultAdvanced';
import { PricingVersionDelete } from './PricingVersionDelete';
import { ResultMap } from './ResultMap';
import { Legend, BarList, StackedBar } from './StackedBars';
import { SourceTag } from './SourceTag';
import styles from './PricingResultView.module.css';

interface PricingResultViewProps {
  readonly instanceVersionId: string;
  readonly instanceId: string;
  readonly number: number;
  readonly letter: string;
  readonly advancedView: boolean;
  readonly onNavigate: (route: LabRoute) => void;
  /** "Compare versions →" with fewer than two finished versions: the shell shows L-4's off state. */
  readonly onCompareOff?: () => void;
}

/**
 * "Simulated with an older rule": the box above the simulation group. It holds "Simulate again" (or
 * the reason it is off), and while a simulation run of the version is queued or running, its line.
 */
function OlderRuleBox({
  version,
  old,
  current,
}: {
  readonly version: PricingVersion;
  readonly old: number;
  readonly current: number;
}) {
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
        <span className={styles.mark} aria-hidden="true">
          ●
        </span>{' '}
        {simulatingLine(elapsedSeconds(simulation, answeredAt, now))}
      </p>
    );
  } else if (simulation !== undefined) {
    // As the pricing run's card: the queued sentence only with a run ahead; no other wording.
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
      className={styles.older}
      data-testid="older-rule"
      aria-label="Simulated with an older rule"
    >
      <p className={styles.olderText}>{olderRuleBox(old, current)}</p>
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
              {simulateAgainLabel(current)}
            </button>
            {offReason !== null && <span className={styles.note}>{offReason}</span>}
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

interface CardProps extends PricingResultViewProps {
  readonly version: PricingVersion;
  readonly result: PricingResult;
  readonly instanceName: string;
  readonly instanceLabel: string;
  readonly periodLabel: string;
  readonly bikeStations: number;
  readonly hubPairsWithRoutes: number | null;
  readonly centre: GeoPoint;
  readonly radiusM: number;
}

function ResultCard({
  version,
  result,
  instanceId,
  number,
  instanceName,
  instanceLabel,
  periodLabel,
  bikeStations,
  hubPairsWithRoutes,
  centre,
  radiusM,
  advancedView,
  onNavigate,
  onCompareOff,
}: CardProps) {
  const id = pricingVersionId(version.instanceVersionId, version.letter);
  const pricing = usePricingActions();
  const list = usePricingList(version.instanceVersionId);
  const hubPairs = useHubPairResults(id).data ?? null;
  const hubs = useHubResults(id).data ?? null;
  const stored = usePricingSimulations(advancedView ? id : null).data ?? null;
  const [tableOpen, setTableOpen] = useState(false);
  const [measure, setMeasure] = useState<MapMeasure>('ridesStarting');
  const [shownPair, setShownPair] = useState<string | null>(null);
  const hubLabels = useMemo(
    () => new Map((hubs ?? []).map((hub) => [hub.hubId, hub.label])),
    [hubs],
  );
  const shown = useMemo(() => {
    const found = hubPairs?.find(
      (item) => `${item.originHub}>${item.destinationHub}` === shownPair,
    );
    return found === undefined
      ? null
      : { originHub: found.originHub, destinationHub: found.destinationHub };
  }, [hubPairs, shownPair]);
  const { modelPrices, flat } = result.simulations;
  const total = periodTravellers(modelPrices);
  const points = carShareChangePoints(flat.travellers.car, modelPrices.travellers.car, total);
  const tiles = goalTiles(result, version, bikeStations);
  const older = olderRule(result, useCurrentSimulationRule());
  const listRoute: LabRoute = {
    kind: 'instance',
    instance: { instanceId, version: number },
    period: null,
  };

  return (
    <div className={styles.view}>
      <p className={styles.brief}>
        <span className={styles.rhythm}>{RESULT_BRIEF}</span>
        <span>{RESULT_SENTENCE}</span>
      </p>
      <p className={styles.scope}>
        {scopeLine(version.letter, pricingVersionName(version), instanceLabel, periodLabel)}
      </p>

      {older !== null && <OlderRuleBox version={version} old={older.old} current={older.new} />}

      <section className={styles.group} data-testid="simulation-group">
        <div className={styles.tagRow}>
          <SourceTag kind="simulation" />
          <p className={styles.source}>
            {SIMULATION_SOURCE}
            {older !== null && olderRuleSuffix(older.old)}
          </p>
        </div>
        <h2 className={styles.insight}>{insightTitle(version.letter, points)}</h2>
        <BarList label="Simulated split of the travellers" stale={older !== null}>
          <StackedBar
            label={versionBarLabel(version.letter)}
            counts={modelPrices.travellers}
            total={total}
          />
          <StackedBar
            label={flatBarLabel(version.goals.flat_price_per_ride_chf)}
            counts={flat.travellers}
            total={total}
          />
        </BarList>
        <Legend />
        <p className={styles.caption}>
          {captionParts(modelPrices, flat).map((part, at) => {
            if (typeof part === 'string') return part;
            const text = groupThousands(part.unserved);
            return part.unserved > 0 ? (
              <a
                key={at}
                className={styles.link}
                href={serialiseRoute(listRoute)}
                onClick={(event) => {
                  event.preventDefault();
                  onNavigate(listRoute);
                }}
              >
                {text}
              </a>
            ) : (
              text
            );
          })}{' '}
          {PLACEHOLDER_SENTENCE} {THREE_MODES_SENTENCE}
        </p>
      </section>

      <section className={styles.group} data-testid="model-group">
        <div className={styles.tagRow}>
          <SourceTag kind="model" />
          <h3 className={styles.title}>{MODEL_SPLIT_TITLE}</h3>
        </div>
        {result.modelSplit === null ? (
          <p className={styles.caption}>The pricing model's split is not stored.</p>
        ) : (
          <BarList label="The pricing model's own split">
            <StackedBar
              label={modelBarLabel(version.letter)}
              counts={result.modelSplit}
              total={Math.max(total, sumModes(result.modelSplit))}
            />
          </BarList>
        )}
        <p className={styles.why}>{WHY_IT_DIFFERS}</p>
      </section>

      <section className={styles.goals} aria-labelledby="goals-title">
        <h3 id="goals-title" className={styles.title}>
          {GOALS_TITLE}
        </h3>
        <ul className={styles.tiles} data-older-rule={older === null ? undefined : ''}>
          {tiles.map((tile) => (
            <li
              key={tile.key}
              className={styles.tile}
              data-tile={tile.key}
              data-testid={`tile-${tile.key}`}
            >
              <p className={styles.tileHead}>
                <b>{tile.heading}</b>
                {tile.weight !== null && <span className={styles.weight}>{tile.weight}</span>}
              </p>
              <p className={styles.figure}>
                {tile.figure}
                {tile.unit !== null && tile.units !== null && (
                  <span className={styles.unit}> {tile.unit}</span>
                )}
              </p>
              {tile.note !== null && <p className={styles.small}>{tile.note}</p>}
              {tile.line !== null ? (
                <p className={styles.small}>{tile.line}</p>
              ) : (
                tile.change !== null &&
                tile.flat !== null && (
                  <p className={styles.small}>
                    {tile.change} against {tile.flat} with the flat price
                  </p>
                )
              )}
              {tile.line !== null && tile.change !== null && (
                <p className={styles.small}>{tile.change} against the flat price</p>
              )}
              <p className={styles.small}>{tile.simulatedLabel}</p>
              {tile.model !== null && (
                <p className={styles.model}>
                  {tile.model.before}
                  {tile.model.tagged && (
                    <>
                      {' '}
                      <SourceTag kind="model" />
                    </>
                  )}
                  {tile.model.after}
                </p>
              )}
            </li>
          ))}
        </ul>
      </section>

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.primary}
          disabled={list.data === undefined}
          onClick={() => {
            const finished = (list.data ?? [])
              .filter((item) => item.state === 'result')
              .map((item) => item.letter);
            if (finished.length < 2) {
              onCompareOff?.();
              return;
            }
            onNavigate(
              compareRoute(
                { instanceId, version: number },
                initialLetters(finished, version.letter),
                null,
              ),
            );
          }}
        >
          {COMPARE_VERSIONS}
        </button>
        <button
          type="button"
          className={styles.secondary}
          disabled={pricing.duplicate.isPending}
          onClick={() => {
            pricing.duplicate.mutate(version, {
              onSuccess: (draft) => {
                onNavigate({
                  kind: 'pricing',
                  instance: { instanceId, version: number },
                  letter: draft.letter,
                  period: null,
                });
              },
            });
          }}
        >
          {DUPLICATE}
        </button>
        <PricingVersionDelete
          version={version}
          instanceName={instanceName}
          instanceId={instanceId}
          number={number}
          onNavigate={onNavigate}
        />
        {pricing.duplicate.isError && (
          <p className={styles.error}>{pricing.duplicate.error.message}</p>
        )}
      </div>

      {hubPairs !== null && (
        <section className={styles.pairs} aria-labelledby="hub-pairs-title">
          <h2 id="hub-pairs-title" className={styles.pairsTitle}>
            <button
              type="button"
              className={styles.disclosure}
              aria-expanded={tableOpen}
              aria-controls="hub-pairs-table"
              onClick={() => {
                setTableOpen((open) => !open);
              }}
            >
              <span aria-hidden="true">{tableOpen ? '▾' : '▸'}</span>{' '}
              {HUB_PAIRS_LINK(hubPairCounts(hubPairs, hubPairsWithRoutes ?? hubPairs.length))}
            </button>
          </h2>
          {tableOpen && (
            <div id="hub-pairs-table">
              <HubPairTable
                results={hubPairs}
                hubLabels={hubLabels}
                shownPair={shownPair}
                onShowOnMap={setShownPair}
              />
            </div>
          )}
        </section>
      )}
      {advancedView && (
        <ResultAdvanced
          result={result}
          flatPrice={version.goals.flat_price_per_ride_chf}
          hubPairs={hubPairsWithRoutes}
          hubPairResults={hubPairs}
          stored={stored}
        />
      )}
      <ResultMap
        centre={centre}
        radiusM={radiusM}
        hubs={hubs}
        measure={measure}
        onMeasure={setMeasure}
        shownPair={shown}
        periodLabel={periodLabel}
      />
    </div>
  );
}

/** L-3 of a finished pricing version: the simulated comparison, the model's own split and the goals. */
export function PricingResultView(props: PricingResultViewProps) {
  const id = pricingVersionId(props.instanceVersionId, props.letter);
  const version = usePricingVersion(id);
  const view = useInstanceView(props.instanceVersionId);
  const result = usePricingResult(version.data?.state === 'result' ? id : null);

  if (version.isPending || view.isPending || result.isPending) return <LoadingCard />;
  // A failed re-read keeps the result already shown; only a read with nothing to show is an error.
  if (version.data === undefined || view.data === undefined || result.data === undefined) {
    const message = version.error?.message ?? view.error?.message ?? result.error?.message ?? '';
    return <p className={styles.error}>The result could not be read: {message}</p>;
  }
  const instanceName = view.data?.instanceName ?? props.instanceId;
  const instanceLabel = `${instanceName} ${versionTag(props.number)}`;
  if (version.data === null) {
    return <p>{nothingAtThisLink(instanceLabel, missingPricingVersionLabel(props.letter))}</p>;
  }
  const stored = result.data;
  if (stored === null) {
    return <p className={styles.error}>{NO_STORED_RESULT}</p>;
  }
  const periods = view.data?.version.periods ?? [];
  const period = periods.find((item) => item.id === stored.periodId) ?? periods[0];
  const card = (
    <ResultCard
      {...props}
      version={version.data}
      result={stored}
      instanceName={instanceName}
      instanceLabel={instanceLabel}
      periodLabel={period?.label ?? ''}
      bikeStations={view.data?.version.counts?.bikeStations ?? 0}
      hubPairsWithRoutes={view.data?.version.counts?.hubPairsWithRoutes ?? null}
      centre={{
        lat: view.data?.version.parameters.centerLat ?? 0,
        lon: view.data?.version.parameters.centerLon ?? 0,
      }}
      radiusM={view.data?.version.parameters.radiusM ?? 0}
    />
  );
  // A read in flight keeps the earlier render at 50 % opacity under the skeleton.
  return result.isFetching ? <LoadingCard previous={card} /> : card;
}
