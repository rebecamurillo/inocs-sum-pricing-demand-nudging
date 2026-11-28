import { useMemo } from 'react';
import { MAP_MEASURES, mapLegend, periodSpan, type MapMeasure } from '../../domain/hub-pair-table';
import { circleBounds, type GeoPoint, type MapHubPair } from '../../domain/map';
import type { HubResult } from '../../domain/pricing-result';
import { useMapFit, useMapLayers, useMapPanel } from '../map/MapContext';
import { RAMP, l3Layers, pairLineLayer } from '../map/l3-layers';
import type { MapDeclaration } from '../map/map-factory';
import styles from './ResultMap.module.css';

interface ResultMapProps {
  readonly centre: GeoPoint;
  readonly radiusM: number;
  /** The model's results per hub; null until they are read. */
  readonly hubs: readonly HubResult[] | null;
  readonly measure: MapMeasure;
  readonly onMeasure: (measure: MapMeasure) => void;
  /** The pair "Show on map" draws, or null. */
  readonly shownPair: MapHubPair | null;
  readonly periodLabel: string;
}

/**
 * What L-3 puts on the shared map: the study circle and one disc per hub, one line for the pair
 * shown, and, over the map, the measure selector and the legend. It draws nothing in the card.
 */
export function ResultMap({
  centre: centreProp,
  radiusM,
  hubs,
  measure,
  onMeasure,
  shownPair,
  periodLabel,
}: ResultMapProps) {
  // Keyed on the values: a new centre object each render would refit the camera and re-add
  // every layer whenever the card renders again (a sort, a click, a measure).
  const { lat, lon } = centreProp;
  const centre = useMemo(() => ({ lat, lon }), [lat, lon]);
  const line = useMemo(
    () => (shownPair === null || hubs === null ? null : pairLineLayer(shownPair, hubs)),
    [shownPair, hubs],
  );
  const declaration = useMemo<MapDeclaration | null>(() => {
    if (hubs === null) return null;
    const discs = l3Layers({ centre, radiusM, hubs, measure, dimmed: line !== null });
    if (line === null) return discs;
    return {
      sources: { ...discs.sources, ...line.sources },
      layers: [...discs.layers, ...line.layers],
    };
  }, [hubs, centre, radiusM, measure, line]);
  const bounds = useMemo(() => circleBounds(centre, radiusM), [centre, radiusM]);

  useMapLayers(declaration);
  useMapFit(bounds);

  const legend = mapLegend(measure, periodSpan(periodLabel));
  const panel = useMemo(
    () => (
      <div className={styles.panel}>
        <label className={styles.selector}>
          <span>Map shows</span>
          <select
            value={measure}
            onChange={(event) => {
              onMeasure(event.target.value as MapMeasure);
            }}
          >
            {MAP_MEASURES.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <div aria-label="Map legend" role="group" className={styles.legend}>
          <p>{legend}</p>
          <div className={styles.ramp} aria-hidden="true">
            <span>few</span>
            <span
              className={styles.bar}
              style={{ background: `linear-gradient(90deg, ${RAMP.low}, ${RAMP.high})` }}
            />
            <span>many</span>
          </div>
        </div>
      </div>
    ),
    [measure, onMeasure, legend],
  );
  useMapPanel(panel);

  return null;
}
