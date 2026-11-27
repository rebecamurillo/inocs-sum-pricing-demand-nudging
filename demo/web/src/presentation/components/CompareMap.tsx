import { useMemo } from 'react';
import type { HubDifference } from '../../domain/comparison';
import {
  COMPARE_MAP_MEASURES,
  compareLegendAnchors,
  compareMeasureLabel,
  compareMeasureValue,
  type CompareMeasure,
} from '../../domain/comparison-text';
import { DIVERGING, divergingScale } from '../../domain/diverging-scale';
import { circleBounds, type GeoPoint, type MapHub, type MapHubPair } from '../../domain/map';
import { COMPUTED_LABEL } from '../../domain/result-text';
import { useMapFit, useMapLayers, useMapPanel } from '../map/MapContext';
import { l4Layers } from '../map/l4-layers';
import { pairLineLayer } from '../map/l3-layers';
import type { MapDeclaration } from '../map/map-factory';
import styles from './CompareMap.module.css';

interface CompareMapProps {
  readonly centre: GeoPoint;
  readonly radiusM: number;
  /** The instance version's hubs: where the discs go. */
  readonly hubs: readonly MapHub[];
  readonly differences: readonly HubDifference[];
  /** The letters of the two compared versions: `b` minus `a`. */
  readonly a: string;
  readonly b: string;
  readonly measure: CompareMeasure;
  readonly onMeasure: (measure: CompareMeasure) => void;
  /** The pair "Show on map" draws, or null. */
  readonly shownPair: MapHubPair | null;
}

/**
 * What L-4 puts on the shared map: the study circle, the hubs' outlines and one disc per hub on the
 * diverging scale, one line for the pair shown, and, over the map, the measure selector and the
 * legend. It draws nothing in the card and moves no camera of its own.
 */
export function CompareMap({
  centre: centreProp,
  radiusM,
  hubs,
  differences,
  a,
  b,
  measure,
  onMeasure,
  shownPair,
}: CompareMapProps) {
  // Keyed on the values: a new centre object each render would refit the camera.
  const { lat, lon } = centreProp;
  const centre = useMemo(() => ({ lat, lon }), [lat, lon]);
  const values = useMemo(
    () =>
      new Map(
        differences.flatMap((hub) => {
          const value = compareMeasureValue(hub, measure);
          return value === null ? [] : [[hub.hubId, value] as const];
        }),
      ),
    [differences, measure],
  );
  // The legend's ends are those of the discs drawn: the hubs that have a value and a position.
  const m = useMemo(
    () => divergingScale(hubs.flatMap((hub) => values.get(hub.id) ?? [])).m,
    [hubs, values],
  );
  const line = useMemo(
    () =>
      shownPair === null
        ? null
        : pairLineLayer(
            shownPair,
            hubs.map((hub) => ({ hubId: hub.id, lat: hub.lat, lon: hub.lon })),
          ),
    [shownPair, hubs],
  );
  const declaration = useMemo<MapDeclaration>(() => {
    const discs = l4Layers({ centre, radiusM, hubs, values, dimmed: line !== null });
    if (line === null) return discs;
    return {
      sources: { ...discs.sources, ...line.sources },
      layers: [...discs.layers, ...line.layers],
    };
  }, [centre, radiusM, hubs, values, line]);
  const bounds = useMemo(() => circleBounds(centre, radiusM), [centre, radiusM]);

  useMapLayers(declaration);
  useMapFit(bounds);

  const anchors = compareLegendAnchors(measure, m);
  const panel = useMemo(
    () => (
      <div className={styles.panel}>
        <label className={styles.selector}>
          <span>Map shows</span>
          <select
            value={measure}
            onChange={(event) => {
              onMeasure(event.target.value as CompareMeasure);
            }}
          >
            {COMPARE_MAP_MEASURES.map((key) => (
              <option key={key} value={key}>
                {compareMeasureLabel(key, a, b)}
              </option>
            ))}
          </select>
        </label>
        <div aria-label="Map legend" role="group" className={styles.legend}>
          <p>{compareMeasureLabel(measure, a, b)}</p>
          <div
            className={styles.bar}
            aria-hidden="true"
            style={{
              background: `linear-gradient(90deg, ${DIVERGING.lower}, ${DIVERGING.none}, ${DIVERGING.higher})`,
            }}
          />
          <p className={styles.anchors}>
            <span>{anchors.lower}</span>
            <span>{anchors.none}</span>
            <span>{anchors.higher}</span>
          </p>
          <p>{COMPUTED_LABEL}</p>
        </div>
      </div>
    ),
    [measure, onMeasure, a, b, anchors.lower, anchors.none, anchors.higher],
  );
  useMapPanel(panel);

  return null;
}
