import { divergingScale } from '../../domain/diverging-scale';
import { circlePolygon, type GeoPoint, type MapHub } from '../../domain/map';
import { MAP_COLOURS } from './basemap-style';
import type { GeoJsonFeature, MapDeclaration } from './map-factory';

export const L4_IDS = {
  studyCircle: 'l4-study-circle',
  hubOutlines: 'l4-hub-outlines',
  hubDiscs: 'l4-hub-discs',
} as const;

/** The ring of a disc and the step back of the discs while one pair is drawn, as L-3 has them. */
const RING = '#ffffff';
const DIMMED_OPACITY = 0.35;

interface L4Input {
  readonly centre: GeoPoint;
  readonly radiusM: number;
  /** The instance version's hubs: their outlines are drawn and their centres place the discs. */
  readonly hubs: readonly MapHub[];
  /** The selected measure's difference per hub id; a hub without an entry has no disc. */
  readonly values: ReadonlyMap<string, number>;
  /** True while one pair is drawn: the discs step back. */
  readonly dimmed: boolean;
}

const collection = (features: readonly GeoJsonFeature[]) =>
  ({ type: 'FeatureCollection', features }) as const;

/**
 * The layers of the compare view L-4: the study circle, the hubs' outlines and one disc per hub
 * that has a value, coloured and sized by the diverging scale of the hubs' values.
 */
export function l4Layers({ centre, radiusM, hubs, values, dimmed }: L4Input): MapDeclaration {
  const valued = hubs.flatMap((hub) => {
    const value = values.get(hub.id);
    return value === undefined ? [] : [{ hub, value }];
  });
  const scale = divergingScale(valued.map((item) => item.value));
  const discs: GeoJsonFeature[] = valued.map(({ hub, value }) => ({
    type: 'Feature',
    properties: { id: hub.id, value, colour: scale.colour(value), radius: scale.radius(value) },
    geometry: { type: 'Point', coordinates: [hub.lon, hub.lat] },
  }));
  const outlines: GeoJsonFeature[] = hubs.flatMap((hub) =>
    hub.outline === null
      ? []
      : [
          {
            type: 'Feature',
            properties: { id: hub.id },
            geometry: { type: 'Polygon', coordinates: [hub.outline] },
          } satisfies GeoJsonFeature,
        ],
  );
  return {
    sources: {
      [L4_IDS.studyCircle]: {
        type: 'geojson',
        data: collection([
          {
            type: 'Feature',
            properties: {},
            geometry: { type: 'Polygon', coordinates: [circlePolygon(centre, radiusM)] },
          },
        ]),
      },
      [L4_IDS.hubOutlines]: { type: 'geojson', data: collection(outlines) },
      [L4_IDS.hubDiscs]: { type: 'geojson', data: collection(discs) },
    },
    layers: [
      {
        id: L4_IDS.studyCircle,
        type: 'fill',
        source: L4_IDS.studyCircle,
        paint: {
          'fill-color': MAP_COLOURS.ring,
          'fill-opacity': 0.18,
          'fill-outline-color': MAP_COLOURS.ring,
        },
      },
      {
        id: L4_IDS.hubOutlines,
        type: 'line',
        source: L4_IDS.hubOutlines,
        paint: { 'line-color': MAP_COLOURS.ref, 'line-width': 1.5, 'line-dasharray': [2, 2] },
      },
      {
        id: L4_IDS.hubDiscs,
        type: 'circle',
        source: L4_IDS.hubDiscs,
        paint: {
          'circle-radius': ['get', 'radius'],
          'circle-color': ['get', 'colour'],
          'circle-stroke-color': RING,
          'circle-stroke-width': 1.5,
          'circle-opacity': dimmed ? DIMMED_OPACITY : 1,
        },
      },
    ],
  };
}
