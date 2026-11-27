import { useMemo, useState } from 'react';
import type { InstanceView as InstanceViewValue } from '../../application/use-cases/load-instance-view';
import type { InstanceCounts, RoutesSummary } from '../../domain/city-instance';
import {
  COUNT_LABELS,
  L1_BRIEF,
  L1_SENTENCE,
  NEVER_CHANGED,
  NEVER_REUSED,
  failureRowTexts,
  groupThousands,
  l1Groups,
  readyLine,
  routesLine,
  showPairsLink,
  versionTag,
} from '../../domain/l1-text';
import { oneDraftMessage, versionNumberOf } from '../../domain/draft-text';
import { circleBounds } from '../../domain/map';
import {
  useDraftActions,
  useInstanceGeometry,
  useInstanceView,
  useRouteFailures,
} from '../hooks/useCityInstances';
import { UNROUTED_COLOUR, l1Layers, unroutedPairLayer } from '../map/l1-layers';
import { useMapFit, useMapLayers, useMapLegend, type LegendEntry } from '../map/MapContext';
import { LoadingCard } from './LoadingCard';
import styles from './InstanceView.module.css';

const UNROUTED_LEGEND: readonly LegendEntry[] = [
  { label: 'Hub pair without a route', colour: UNROUTED_COLOUR },
];
const NO_LEGEND: readonly LegendEntry[] = [];

function Counts({ counts }: { counts: InstanceCounts }) {
  return (
    <dl className={styles.counts}>
      {COUNT_LABELS.map(([key, label]) => (
        <div key={key} className={styles.count}>
          <dt>{label}</dt>
          <dd>{groupThousands(counts[key])}</dd>
        </div>
      ))}
    </dl>
  );
}

function RoutesBox({
  routes,
  hubLabel,
  shown,
  onToggleShown,
}: {
  routes: RoutesSummary;
  hubLabel: (hubId: string) => string;
  shown: ReadonlySet<number>;
  onToggleShown: (index: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const failures = useRouteFailures(routes, open);
  const rows = failures.data ?? [];

  return (
    <div className={styles.routes}>
      <p>
        {routesLine(routes)}
        {routes.queriesFailed > 0 && (
          <>
            {' '}
            <button
              type="button"
              className={styles.link}
              aria-expanded={open}
              onClick={() => {
                setOpen(!open);
              }}
            >
              {showPairsLink(routes.queriesFailed)}
            </button>
          </>
        )}
      </p>
      {open && failures.isPending && <p>Reading the failed queries.</p>}
      {open && failures.isError && (
        <p className={styles.error}>The failed queries could not be read.</p>
      )}
      {open && rows.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">From → to</th>
              <th scope="col">Query</th>
              <th scope="col">What happened</th>
              <th scope="col">Effect</th>
              <th scope="col">
                <span className={styles.srOnly}>Show on map</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((failure, index) => {
              const texts = failureRowTexts(failure, routes.retries, hubLabel);
              const onMap = shown.has(index);
              return (
                <tr key={`${failure.originHub}-${failure.destinationHub}-${failure.query}`}>
                  <td>{texts.fromTo}</td>
                  <td>{texts.query}</td>
                  <td>{texts.whatHappened}</td>
                  <td>{texts.effect}</td>
                  <td>
                    <button
                      type="button"
                      className={styles.button}
                      aria-pressed={onMap}
                      onClick={() => {
                        onToggleShown(index);
                      }}
                    >
                      {onMap ? 'Hide from map' : 'Show on map'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** Where "Edit as a new version" leads: the draft, and the sentence to show when it already existed. */
export interface OpenedDraft {
  readonly instanceId: string;
  readonly number: number;
  readonly message: string | null;
}

function SavedInstance({
  view,
  advancedView,
  onOpenDraft,
}: {
  view: InstanceViewValue;
  advancedView: boolean;
  onOpenDraft?: (draft: OpenedDraft) => void;
}) {
  const { version, instanceName, dataset, pricingVersionCount } = view;
  const geometry = useInstanceGeometry(version.id).data ?? null;
  const [shown, setShown] = useState<ReadonlySet<number>>(new Set());
  const actions = useDraftActions();
  const [editError, setEditError] = useState<string | null>(null);
  const failures = useRouteFailures(version.routes, false).data;

  const declaration = useMemo(
    () =>
      geometry === null
        ? null
        : l1Layers({
            centre: { lat: version.parameters.centerLat, lon: version.parameters.centerLon },
            radiusM: version.parameters.radiusM,
            stations: geometry.stations,
            hubs: geometry.hubs,
            hubPairs: geometry.hubPairs,
          }),
    [geometry, version.parameters],
  );
  const bounds = useMemo(
    () =>
      circleBounds(
        { lat: version.parameters.centerLat, lon: version.parameters.centerLon },
        version.parameters.radiusM,
      ),
    [version.parameters],
  );
  const unrouted = useMemo(() => {
    if (geometry === null || failures === undefined || shown.size === 0) return null;
    const pairs = failures.filter((_, index) => shown.has(index));
    return unroutedPairLayer(pairs, geometry.hubs);
  }, [geometry, failures, shown]);

  useMapLayers(declaration);
  useMapLayers(unrouted);
  useMapFit(bounds);
  useMapLegend(unrouted === null ? NO_LEGEND : UNROUTED_LEGEND);

  const hubLabels = useMemo(
    () => new Map((geometry?.hubs ?? []).map((hub) => [hub.id, hub.label])),
    [geometry],
  );
  const hubLabel = (hubId: string) => hubLabels.get(hubId) ?? hubId;
  const toggle = (index: number) => {
    const next = new Set(shown);
    if (!next.delete(index)) next.add(index);
    setShown(next);
  };

  const edit = () => {
    setEditError(null);
    actions.draft.mutateAsync({ instanceId: version.instanceId, basedOnId: version.id }).then(
      (opened) => {
        const based =
          opened.version.basedOnId === null ? null : versionNumberOf(opened.version.basedOnId);
        onOpenDraft?.({
          instanceId: version.instanceId,
          number: opened.version.number,
          message:
            opened.existed && based !== null
              ? oneDraftMessage(based, opened.version.createdAt)
              : null,
        });
      },
      (error: unknown) => {
        setEditError(error instanceof Error ? error.message : String(error));
      },
    );
  };

  return (
    <div className={styles.view}>
      <p className={styles.brief}>
        <span className={styles.rhythm}>{L1_BRIEF}</span>
        <span>{L1_SENTENCE}</span>
      </p>
      <div className={styles.head}>
        <h2 className={styles.name}>{instanceName}</h2>
        <span className={styles.tag}>{versionTag(version.number)}</span>
        {version.state === 'ready' && (
          <span className={styles.scope}>{readyLine(version.sealedAt, pricingVersionCount)}</span>
        )}
        {advancedView && <p className={styles.never}>{NEVER_REUSED}</p>}
      </div>
      {version.counts !== null && <Counts counts={version.counts} />}
      {version.routes !== null && (
        <RoutesBox
          routes={version.routes}
          hubLabel={hubLabel}
          shown={shown}
          onToggleShown={toggle}
        />
      )}
      {l1Groups(version, dataset).map((group) => (
        <section key={group.number} className={styles.group} aria-label={group.name}>
          <h3 className={styles.groupHead}>
            <span className={styles.groupNumber} aria-hidden="true">
              {group.number}
            </span>
            {group.name}
          </h3>
          <dl className={styles.fields}>
            {group.fields.map((field) => (
              <div key={field.name} className={styles.field}>
                <dt>
                  {field.name}
                  {advancedView && <code className={styles.package}>{field.packageNames}</code>}
                </dt>
                <dd className={styles.value}>{field.value}</dd>
                {field.sentence !== null && <dd className={styles.sentence}>{field.sentence}</dd>}
                {field.caption !== null && <dd className={styles.caption}>{field.caption}</dd>}
              </div>
            ))}
          </dl>
        </section>
      ))}
      <p className={styles.closing}>{NEVER_CHANGED}</p>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.button}
          disabled={actions.draft.isPending}
          onClick={edit}
        >
          Edit as a new version
        </button>
      </div>
      {editError !== null && <p className={styles.error}>{editError}</p>}
    </div>
  );
}

/** The saved city instance card (L-1): reads the version, then writes it and draws it on the map. */
export function InstanceView({
  versionId,
  advancedView,
  onOpenDraft,
}: {
  versionId: string;
  advancedView: boolean;
  onOpenDraft?: (draft: OpenedDraft) => void;
}) {
  const query = useInstanceView(versionId);
  if (query.isPending) return <LoadingCard />;
  if (query.isError) {
    return (
      <p className={styles.error}>The city instance could not be read: {query.error.message}</p>
    );
  }
  if (query.data === null) return <p>Nothing at this link.</p>;
  return <SavedInstance view={query.data} advancedView={advancedView} onOpenDraft={onOpenDraft} />;
}
