import type { GeoBounds } from '../../domain/map';

/**
 * The narrow view of a map the components use. The real map (MapLibre GL JS) is built by a
 * factory that `composition/` injects; unit tests inject a fake that records these calls.
 */

export interface GeoJsonFeature {
  readonly type: 'Feature';
  readonly properties: Readonly<Record<string, unknown>>;
  readonly geometry:
    | { readonly type: 'Point'; readonly coordinates: readonly number[] }
    | { readonly type: 'LineString'; readonly coordinates: readonly (readonly number[])[] }
    | {
        readonly type: 'Polygon';
        readonly coordinates: readonly (readonly (readonly number[])[])[];
      };
}

export interface GeoJsonCollection {
  readonly type: 'FeatureCollection';
  readonly features: readonly GeoJsonFeature[];
}

export type MapSourceSpec =
  | { readonly type: 'vector'; readonly url: string }
  | { readonly type: 'geojson'; readonly data: GeoJsonCollection };

export interface MapLayerSpec {
  readonly id: string;
  readonly type: 'background' | 'fill' | 'line' | 'circle';
  readonly source?: string;
  readonly 'source-layer'?: string;
  readonly paint: Readonly<Record<string, unknown>>;
  readonly layout?: Readonly<Record<string, unknown>>;
}

export interface MapStyleSpec {
  readonly version: 8;
  readonly sources: Readonly<Record<string, MapSourceSpec>>;
  readonly layers: readonly MapLayerSpec[];
}

/** What a view puts on the map: its sources and the layers that read them. */
export interface MapDeclaration {
  readonly sources: Readonly<Record<string, MapSourceSpec>>;
  readonly layers: readonly MapLayerSpec[];
}

export interface CameraOptions {
  /** False makes the camera jump. */
  readonly animate: boolean;
}

export interface MapHandle {
  addSource(id: string, source: MapSourceSpec): void;
  removeSource(id: string): void;
  hasSource(id: string): boolean;
  addLayer(layer: MapLayerSpec): void;
  removeLayer(id: string): void;
  hasLayer(id: string): boolean;
  /** Replaces the whole style: the sources and layers views declared are gone afterwards. */
  setStyle(style: MapStyleSpec): void;
  resize(): void;
  fitBounds(bounds: GeoBounds, options: CameraOptions): void;
  jumpTo(center: readonly [number, number], zoom: number): void;
  /**
   * Calls back each time a style has finished loading (the first one, and after `setStyle`),
   * at once when one already has. Returns the way to stop listening.
   */
  onStyleReady(callback: () => void): () => void;
  remove(): void;
}

export interface MapOptions {
  readonly style: MapStyleSpec;
  /** 0 under prefers-reduced-motion. */
  readonly fadeDuration: number;
}

export type MapFactory = (container: HTMLElement, options: MapOptions) => MapHandle;
