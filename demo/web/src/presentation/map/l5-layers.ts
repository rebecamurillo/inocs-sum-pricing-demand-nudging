import { circlePolygon, type GeoPoint, type MapHub, type MapStation } from '../../domain/map';
import { MAP_COLOURS } from './basemap-style';
import type { GeoJsonFeature, MapDeclaration } from './map-factory';

export const L5_IDS = {
  studyCircle: 'l5-study-circle',
  hubOutlines: 'l5-hub-outlines',
  bikeStations: 'l5-bike-stations',
} as const;

interface L5Input {
  readonly centre: GeoPoint;
  readonly radiusM: number;
  readonly stations: readonly MapStation[];
  readonly hubs: readonly MapHub[];
}

const collection = (features: readonly GeoJsonFeature[]) =>
  ({ type: 'FeatureCollection', features }) as const;

/**
 * The layers of the traveller view L-5: the study circle, the hubs' outlines and the bike
 * stations of the chosen version's instance version. The click that sets a point is not a layer.
 */
export function l5Layers({ centre, radiusM, stations, hubs }: L5Input): MapDeclaration {
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
  const bikes: GeoJsonFeature[] = stations
    .filter((station) => station.kind === 'bs')
    .map((station) => ({
      type: 'Feature',
      properties: { id: station.id },
      geometry: { type: 'Point', coordinates: [station.lon, station.lat] },
    }));
  return {
    sources: {
      [L5_IDS.studyCircle]: {
        type: 'geojson',
        data: collection([
          {
            type: 'Feature',
            properties: {},
            geometry: { type: 'Polygon', coordinates: [circlePolygon(centre, radiusM)] },
          },
        ]),
      },
      [L5_IDS.hubOutlines]: { type: 'geojson', data: collection(outlines) },
      [L5_IDS.bikeStations]: { type: 'geojson', data: collection(bikes) },
    },
    layers: [
      {
        id: L5_IDS.studyCircle,
        type: 'fill',
        source: L5_IDS.studyCircle,
        paint: {
          'fill-color': MAP_COLOURS.ring,
          'fill-opacity': 0.18,
          'fill-outline-color': MAP_COLOURS.ring,
        },
      },
      {
        id: L5_IDS.hubOutlines,
        type: 'line',
        source: L5_IDS.hubOutlines,
        paint: { 'line-color': MAP_COLOURS.ref, 'line-width': 1.5, 'line-dasharray': [2, 2] },
      },
      {
        id: L5_IDS.bikeStations,
        type: 'circle',
        source: L5_IDS.bikeStations,
        paint: {
          'circle-color': MAP_COLOURS.bike,
          'circle-radius': 4,
          'circle-stroke-color': MAP_COLOURS.bikeRing,
          'circle-stroke-width': 1.5,
        },
      },
    ],
  };
}
