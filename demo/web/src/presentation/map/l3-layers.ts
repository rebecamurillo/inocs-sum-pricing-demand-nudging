import { circlePolygon, type GeoPoint, type MapHubPair } from '../../domain/map';
import { measureValue, type MapMeasure } from '../../domain/hub-pair-table';
import type { HubResult } from '../../domain/pricing-result';
import { MAP_COLOURS } from './basemap-style';
import type { GeoJsonFeature, MapDeclaration } from './map-factory';

export const L3_IDS = {
  studyCircle: 'l3-study-circle',
  hubDiscs: 'l3-hub-discs',
  selectedPair: 'l3-selected-pair',
} as const;

/** The green ramp of the bike-ride discs (UX-SPEC § Mode colours and marks) and their ring. */
export const RAMP = { low: '#e3f1e1', high: '#005a00', ring: '#ffffff' } as const;
const PAIR_COLOUR = '#00336e';
const DIMMED_OPACITY = 0.35;

interface L3Input {
  readonly centre: GeoPoint;
  readonly radiusM: number;
  readonly hubs: readonly HubResult[];
  readonly measure: MapMeasure;
  /** True while one pair is drawn: the discs step back. */
  readonly dimmed: boolean;
}

const collection = (features: readonly GeoJsonFeature[]) =>
  ({ type: 'FeatureCollection', features }) as const;

/**
 * The layers of the result view L-3: the study circle and one disc per hub, its size and
 * colour on `t`, the hub's value over the largest value of the measure. A hub without a value
 * for the measure (no mean price) is left out. No hub outlines, no stops, no web of pairs.
 */
export function l3Layers({ centre, radiusM, hubs, measure, dimmed }: L3Input): MapDeclaration {
  const valued = hubs.flatMap((hub) => {
    const value = measureValue(hub, measure);
    return value === null ? [] : [{ hub, value }];
  });
  const max = Math.max(0, ...valued.map((item) => item.value));
  const points: GeoJsonFeature[] = valued.map(({ hub, value }) => ({
    type: 'Feature',
    properties: { id: hub.hubId, value, t: max === 0 ? 0 : value / max },
    geometry: { type: 'Point', coordinates: [hub.lon, hub.lat] },
  }));
  return {
    sources: {
      [L3_IDS.studyCircle]: {
        type: 'geojson',
        data: collection([
          {
            type: 'Feature',
            properties: {},
            geometry: { type: 'Polygon', coordinates: [circlePolygon(centre, radiusM)] },
          },
        ]),
      },
      [L3_IDS.hubDiscs]: { type: 'geojson', data: collection(points) },
    },
    layers: [
      {
        id: L3_IDS.studyCircle,
        type: 'fill',
        source: L3_IDS.studyCircle,
        paint: {
          'fill-color': MAP_COLOURS.ring,
          'fill-opacity': 0.18,
          'fill-outline-color': MAP_COLOURS.ring,
        },
      },
      {
        id: L3_IDS.hubDiscs,
        type: 'circle',
        source: L3_IDS.hubDiscs,
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['get', 't'], 0, 3, 1, 14],
          'circle-color': ['interpolate', ['linear'], ['get', 't'], 0, RAMP.low, 1, RAMP.high],
          'circle-stroke-color': RAMP.ring,
          'circle-stroke-width': 1.5,
          'circle-opacity': dimmed ? DIMMED_OPACITY : 1,
        },
      },
    ],
  };
}

/** One line between the two hubs' centres; null when a hub is not on the map. */
export function pairLineLayer(
  pair: MapHubPair,
  hubs: readonly { readonly hubId: string; readonly lat: number; readonly lon: number }[],
): MapDeclaration | null {
  const from = hubs.find((hub) => hub.hubId === pair.originHub);
  const to = hubs.find((hub) => hub.hubId === pair.destinationHub);
  if (from === undefined || to === undefined) return null;
  return {
    sources: {
      [L3_IDS.selectedPair]: {
        type: 'geojson',
        data: collection([
          {
            type: 'Feature',
            properties: { origin: pair.originHub, destination: pair.destinationHub },
            geometry: {
              type: 'LineString',
              coordinates: [
                [from.lon, from.lat],
                [to.lon, to.lat],
              ],
            },
          },
        ]),
      },
    },
    layers: [
      {
        id: L3_IDS.selectedPair,
        type: 'line',
        source: L3_IDS.selectedPair,
        paint: { 'line-color': PAIR_COLOUR, 'line-width': 3 },
        layout: { 'line-cap': 'round' },
      },
    ],
  };
}
