import { useMemo, useState } from 'react';
import { HUB_PAIRS_LINK, hubPairCounts, type MapMeasure } from '../../domain/hub-pair-table';
import { groupThousands, versionTag } from '../../domain/l1-text';
import type { GeoPoint } from '../../domain/map';
import { pricingVersionName } from '../../domain/pricing-goals-text';
import {
  MODES,
  periodTravellers,
  sumModes,
  type ModeCounts,
  type PricingResult,
} from '../../domain/pricing-result';
import { pricingVersionId, type PricingVersion } from '../../domain/pricing-version';
import { serialiseRoute, type LabRoute } from '../../domain/route';
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
  modeSummary,
  modelBarLabel,
  scopeLine,
  segmentShare,
  versionBarLabel,
} from '../../domain/result-text';
import { missingPricingVersionLabel, nothingAtThisLink } from '../../domain/unknown-link';
import { useInstanceView } from '../hooks/useCityInstances';
import {
  useHubPairResults,
  useHubResults,
  usePricingResult,
  usePricingSimulations,
  usePricingVersion,
} from '../hooks/usePricingVersions';
import { HubPairTable } from './HubPairTable';
import { LoadingCard } from './LoadingCard';
import { ResultAdvanced } from './ResultAdvanced';
import { ResultMap } from './ResultMap';
import { SourceTag } from './SourceTag';
import styles from './PricingResultView.module.css';

/** Segments narrower than this share of the scale carry no inner label (the legend still names them). */
const MIN_LABELLED_SHARE = 8;

interface PricingResultViewProps {
  readonly instanceVersionId: string;
  readonly instanceId: string;
  readonly number: number;
  readonly letter: string;
  readonly advancedView: boolean;
  readonly onNavigate: (route: LabRoute) => void;
}

/** One stacked bar on the scale `total`: three modes, each with its icon and share, never colour alone. */
function StackedBar({
  label,
  counts,
  total,
}: {
  readonly label: string;
  readonly counts: ModeCounts;
  readonly total: number;
}) {
  return (
    <li>
      <span className={styles.barLabel}>{label}</span>
      <div className={styles.track} role="img" aria-label={`${label}: ${modeSummary(counts)}`}>
        {MODES.map((mode) => {
          const count = counts[mode.key];
          const share = segmentShare(count, total);
          return (
            <span
              key={mode.key}
              className={styles.segment}
              data-mode={mode.key}
              style={{
                width: `${String(total <= 0 ? 0 : (100 * count) / total)}%`,
                background: mode.colour,
              }}
            >
              {share >= MIN_LABELLED_SHARE && (
                <span aria-hidden="true">
                  {mode.icon} {String(share)} %
                </span>
              )}
            </span>
          );
        })}
      </div>
    </li>
  );
}

function Legend() {
  return (
    <ul className={styles.legend} aria-label="Modes">
      {MODES.map((mode) => (
        <li key={mode.key} className={styles.key}>
          <span className={styles.swatch} style={{ background: mode.colour }} aria-hidden="true" />
          <span aria-hidden="true">{mode.icon}</span>
          <span>{mode.label}</span>
        </li>
      ))}
    </ul>
  );
}

interface CardProps extends PricingResultViewProps {
  readonly version: PricingVersion;
  readonly result: PricingResult;
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
  instanceLabel,
  periodLabel,
  bikeStations,
  hubPairsWithRoutes,
  centre,
  radiusM,
  advancedView,
  onNavigate,
}: CardProps) {
  const id = pricingVersionId(version.instanceVersionId, version.letter);
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

      <section className={styles.group} data-testid="simulation-group">
        <div className={styles.tagRow}>
          <SourceTag kind="simulation" />
          <p className={styles.source}>{SIMULATION_SOURCE}</p>
        </div>
        <h2 className={styles.insight}>{insightTitle(version.letter, points)}</h2>
        <ul className={styles.bars} aria-label="Simulated split of the travellers">
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
        </ul>
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
          <ul className={styles.bars} aria-label="The pricing model's own split">
            <StackedBar
              label={modelBarLabel(version.letter)}
              counts={result.modelSplit}
              total={Math.max(total, sumModes(result.modelSplit))}
            />
          </ul>
        )}
        <p className={styles.why}>{WHY_IT_DIFFERS}</p>
      </section>

      <section className={styles.goals} aria-labelledby="goals-title">
        <h3 id="goals-title" className={styles.title}>
          {GOALS_TITLE}
        </h3>
        <ul className={styles.tiles}>
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
