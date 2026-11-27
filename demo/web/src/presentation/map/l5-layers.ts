import { circlePolygon, type GeoPoint, type MapHub, type MapStation } from '../../domain/map';
import type { RouteOptionLeg } from '../../domain/traveller';
import { legKind } from '../../domain/trip-options';
import { ROUTE_KIND_ORDER, ROUTE_STYLES } from '../../domain/trip-route';
import { MAP_COLOURS } from './basemap-style';
import type { GeoJsonFeature, MapDeclaration } from './map-factory';

export const L5_IDS = {
  studyCircle: 'l5-study-circle',
  hubOutlines: 'l5-hub-outlines',
  matchedOutlines: 'l5-matched-outlines',
  bikeStations: 'l5-bike-stations',
  routeWalk: 'l5-route-walk',
  routePt: 'l5-route-pt',
  routeBike: 'l5-route-bike',
  routeCar: 'l5-route-car',
} as const;

interface L5Input {
  readonly centre: GeoPoint;
  readonly radiusM: number;
  readonly stations: readonly MapStation[];
  readonly hubs: readonly MapHub[];
  /** The hubs the two points matched; their outlines are drawn solid over the dashed ones. */
  readonly matchedHubIds?: readonly string[];
  /** The legs of the selected option; null draws no route. */
  readonly route?: { readonly legs: readonly RouteOptionLeg[] } | null;
}

const ROUTE_LAYER_IDS = {
  walk: L5_IDS.routeWalk,
  pt: L5_IDS.routePt,
  bike: L5_IDS.routeBike,
  car: L5_IDS.routeCar,
} as const;

/**
 * MapLibre's `line-dasharray` counts in line widths, not pixels: 6/3 px at 3 px is [2, 1] and
 * 2/3 px at 2 px is [1, 1.5].
 */
const DASH_PIXELS = { bike: [6, 3], walk: [2, 3] } as const;

function routePaint(kind: keyof typeof ROUTE_LAYER_IDS): Record<string, unknown> {
  const style = ROUTE_STYLES[kind];
  const paint: Record<string, unknown> = {
    'line-color': style.colour,
    'line-width': style.width,
  };
  if (kind === 'bike' || kind === 'walk') {
    paint['line-dasharray'] = DASH_PIXELS[kind].map((pixels) => pixels / style.width);
  }
  return paint;
}

const collection = (features: readonly GeoJsonFeature[]) =>
  ({ type: 'FeatureCollection', features }) as const;

/**
 * The layers of the traveller view L-5: the study circle, the hubs' outlines and the bike
 * stations of the chosen version's instance version. The click that sets a point is not a layer.
 */
export function l5Layers({
  centre,
  radiusM,
  stations,
  hubs,
  matchedHubIds = [],
  route = null,
}: L5Input): MapDeclaration {
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
  const matched: GeoJsonFeature[] = outlines.filter((feature) =>
    matchedHubIds.includes(String(feature.properties.id)),
  );
  const bikes: GeoJsonFeature[] = stations
    .filter((station) => station.kind === 'bs')
    .map((station) => ({
      type: 'Feature',
      properties: { id: station.id },
      geometry: { type: 'Point', coordinates: [station.lon, station.lat] },
    }));
  const routeKinds =
    route === null
      ? []
      : ROUTE_KIND_ORDER.filter((kind) =>
          route.legs.some((leg) => legKind(leg) === kind && leg.coordinates !== null),
        );
  const routeSources = Object.fromEntries(
    routeKinds.map((kind) => [
      ROUTE_LAYER_IDS[kind],
      {
        type: 'geojson',
        data: collection(
          (route?.legs ?? []).flatMap((leg) =>
            legKind(leg) === kind && leg.coordinates !== null
              ? [
                  {
                    type: 'Feature',
                    properties: { lineKind: leg.lineKind },
                    geometry: { type: 'LineString', coordinates: leg.coordinates },
                  } satisfies GeoJsonFeature,
                ]
              : [],
          ),
        ),
      } as const,
    ]),
  );
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
      ...(matched.length > 0
        ? { [L5_IDS.matchedOutlines]: { type: 'geojson', data: collection(matched) } as const }
        : {}),
      [L5_IDS.bikeStations]: { type: 'geojson', data: collection(bikes) },
      ...routeSources,
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
      ...(matched.length > 0
        ? [
            {
              id: L5_IDS.matchedOutlines,
              type: 'line',
              source: L5_IDS.matchedOutlines,
              paint: { 'line-color': '#2e2d29', 'line-width': 2 },
            } as const,
          ]
        : []),
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
      ...routeKinds.map(
        (kind) =>
          ({
            id: ROUTE_LAYER_IDS[kind],
            type: 'line',
            source: ROUTE_LAYER_IDS[kind],
            paint: routePaint(kind),
            ...(kind === 'walk' ? { layout: { 'line-cap': 'round', 'line-join': 'round' } } : {}),
          }) as const,
      ),
    ],
  };
}
