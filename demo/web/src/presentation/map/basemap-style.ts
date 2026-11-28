import type { MapStyleSpec } from './map-factory';

/** The map tokens of knowledge/visual-identity.md, as in presentation/styles/tokens.css. */
export const MAP_COLOURS = {
  ground: '#e4e5e2',
  street: '#fafaf9',
  water: '#d4dbdc',
  ref: '#949c93',
  ring: '#b7bcb5',
  stop: '#004494',
  bike: '#98c33a',
  bikeRing: '#54740f',
} as const;

export const BASEMAP_SOURCE = 'basemap';

interface BasemapStyleInput {
  /** The page-relative address of the PMTiles file, or null when none is served. */
  readonly pmtilesUrl: string | null;
}

/**
 * The grey city map: ground, water, land cover and streets from the OpenMapTiles layers.
 * No text, no symbols, no glyphs or sprite, no remote address. Without a file it is the
 * ground colour alone.
 */
export function basemapStyle({ pmtilesUrl }: BasemapStyleInput): MapStyleSpec {
  const background = {
    id: 'background',
    type: 'background',
    paint: { 'background-color': MAP_COLOURS.ground },
  } as const;
  if (pmtilesUrl === null) return { version: 8, sources: {}, layers: [background] };
  return {
    version: 8,
    sources: { [BASEMAP_SOURCE]: { type: 'vector', url: `pmtiles://${pmtilesUrl}` } },
    layers: [
      background,
      {
        id: 'landcover',
        type: 'fill',
        source: BASEMAP_SOURCE,
        'source-layer': 'landcover',
        paint: { 'fill-color': MAP_COLOURS.ground },
      },
      {
        id: 'water',
        type: 'fill',
        source: BASEMAP_SOURCE,
        'source-layer': 'water',
        paint: { 'fill-color': MAP_COLOURS.water },
      },
      {
        id: 'transportation',
        type: 'line',
        source: BASEMAP_SOURCE,
        'source-layer': 'transportation',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': MAP_COLOURS.street,
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.4, 14, 1.5, 18, 6],
        },
      },
    ],
  };
}
