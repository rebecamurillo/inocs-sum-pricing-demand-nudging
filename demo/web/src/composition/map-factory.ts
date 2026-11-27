import {
  Map as MapLibreMap,
  Marker,
  addProtocol,
  type LayerSpecification,
  type SourceSpecification,
  type StyleSpecification,
} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Protocol } from 'pmtiles';
import type { GeoBounds, GeoPoint } from '../domain/map';
import type {
  MapFactory,
  MapHandle,
  MapLayerSpec,
  MapSourceSpec,
  MapStyleSpec,
  MarkerHandle,
  MarkerOptions,
} from '../presentation/map/map-factory';

// The `pmtiles://` protocol is global to MapLibre: register it once for the page.
let protocolRegistered = false;
function registerPmtilesProtocol(): void {
  if (protocolRegistered) return;
  const protocol = new Protocol();
  addProtocol('pmtiles', protocol.tile);
  protocolRegistered = true;
}

const asStyle = (style: MapStyleSpec) => style as unknown as StyleSpecification;
const asSource = (source: MapSourceSpec) => source as unknown as SourceSpecification;
const asLayer = (layer: MapLayerSpec) => layer as unknown as LayerSpecification;

class MapLibreHandle implements MapHandle {
  private readonly map: MapLibreMap;
  private readonly listeners = new Set<() => void>();
  private styleLoaded = false;

  constructor(map: MapLibreMap) {
    this.map = map;
    map.on('style.load', () => {
      this.styleLoaded = true;
      for (const listener of [...this.listeners]) listener();
    });
  }

  addSource(id: string, source: MapSourceSpec): void {
    this.map.addSource(id, asSource(source));
  }
  removeSource(id: string): void {
    this.map.removeSource(id);
  }
  hasSource(id: string): boolean {
    return this.map.getSource(id) !== undefined;
  }
  addLayer(layer: MapLayerSpec): void {
    this.map.addLayer(asLayer(layer));
  }
  removeLayer(id: string): void {
    this.map.removeLayer(id);
  }
  hasLayer(id: string): boolean {
    return this.map.getLayer(id) !== undefined;
  }
  setStyle(style: MapStyleSpec): void {
    this.styleLoaded = false;
    this.map.setStyle(asStyle(style), { diff: false });
  }
  addMarker(position: GeoPoint, options: MarkerOptions): MarkerHandle {
    const element = document.createElement('div');
    element.setAttribute('role', 'img');
    element.setAttribute('aria-label', options.label);
    element.title = options.label;
    // A white-ringed dot in the ink colour of the tokens; drawn here because a marker is a DOM
    // node MapLibre owns, outside React.
    Object.assign(element.style, {
      width: '18px',
      height: '18px',
      borderRadius: '50%',
      background: '#2e2d29',
      border: '3px solid #ffffff',
      boxShadow: '0 0 0 1px #2e2d29',
      cursor: options.draggable ? 'grab' : 'default',
    });
    const marker = new Marker({ element, draggable: options.draggable })
      .setLngLat([position.lon, position.lat])
      .addTo(this.map);
    const where = (): GeoPoint => {
      const at = marker.getLngLat();
      return { lat: at.lat, lon: at.lng };
    };
    marker.on('drag', () => {
      options.onDrag?.(where());
    });
    marker.on('dragend', () => {
      options.onDragEnd?.(where());
    });
    return {
      setPosition: (next) => {
        marker.setLngLat([next.lon, next.lat]);
      },
      remove: () => {
        marker.remove();
      },
    };
  }
  resize(): void {
    this.map.resize();
  }
  fitBounds(bounds: GeoBounds, options: { animate: boolean }): void {
    this.map.fitBounds([bounds[0], bounds[1], bounds[2], bounds[3]], {
      animate: options.animate,
      padding: 16,
    });
  }
  jumpTo(center: readonly [number, number], zoom: number): void {
    this.map.jumpTo({ center: [center[0], center[1]], zoom });
  }
  onStyleReady(callback: () => void): () => void {
    this.listeners.add(callback);
    if (this.styleLoaded) callback();
    return () => {
      this.listeners.delete(callback);
    };
  }
  remove(): void {
    this.map.remove();
  }
}

/** The real map: MapLibre GL JS with the PMTiles protocol; no remote style, glyph or sprite. */
export const createMapLibreMap: MapFactory = (container, options) => {
  registerPmtilesProtocol();
  const map = new MapLibreMap({
    container,
    style: asStyle(options.style),
    fadeDuration: options.fadeDuration,
    attributionControl: false,
    // The pane is the region named "Map"; the focusable canvas inside it has its own name.
    locale: { 'Map.Title': 'City view, pan with the arrow keys' },
    center: [6.14, 46.2],
    zoom: 11,
  });
  return new MapLibreHandle(map);
};
