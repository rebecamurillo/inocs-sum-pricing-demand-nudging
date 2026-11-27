import type { GeoPoint } from '../../domain/map';
import type {
  MapFactory,
  MapHandle,
  MapLayerSpec,
  MapOptions,
  MapSourceSpec,
  MarkerHandle,
  MarkerOptions,
} from './map-factory';

/** A marker the fake map holds; tests move it with `drag` and `dragEnd`. */
export class FakeMarker implements MarkerHandle {
  removed = false;
  readonly positions: GeoPoint[];

  constructor(
    position: GeoPoint,
    readonly options: MarkerOptions,
  ) {
    this.positions = [position];
  }

  get position(): GeoPoint {
    return this.positions[this.positions.length - 1] ?? { lat: 0, lon: 0 };
  }
  setPosition(position: GeoPoint): void {
    this.positions.push(position);
  }
  remove(): void {
    this.removed = true;
  }
  /** The visitor drags the marker to `position`. */
  drag(position: GeoPoint): void {
    this.positions.push(position);
    this.options.onDrag?.(position);
  }
  /** The visitor drops the marker at `position`. */
  dragEnd(position: GeoPoint): void {
    this.positions.push(position);
    this.options.onDragEnd?.(position);
  }
}

/** A map that records the calls the components make; the factory of the unit tests. */
export class FakeMap implements MapHandle {
  readonly calls: string[] = [];
  readonly sources = new Map<string, MapSourceSpec>();
  readonly layers: MapLayerSpec[] = [];
  readonly fits: { bounds: readonly number[]; animate: boolean }[] = [];
  readonly styles: MapOptions['style'][] = [];
  readonly markers: FakeMarker[] = [];
  removed = false;
  private readonly listeners = new Set<() => void>();
  private readonly clickListeners = new Set<(point: GeoPoint) => void>();
  private styleLoaded = false;

  constructor(
    readonly container: HTMLElement,
    readonly options: MapOptions,
  ) {}

  /** The map finished loading a style, as the real one does after creation and `setStyle`. */
  emitStyleReady(): void {
    // A new style drops what views added.
    this.sources.clear();
    this.layers.length = 0;
    this.styleLoaded = true;
    for (const listener of [...this.listeners]) listener();
  }

  addSource(id: string, source: MapSourceSpec): void {
    this.calls.push(`addSource:${id}`);
    this.sources.set(id, source);
  }
  removeSource(id: string): void {
    this.calls.push(`removeSource:${id}`);
    this.sources.delete(id);
  }
  hasSource(id: string): boolean {
    return this.sources.has(id);
  }
  addLayer(layer: MapLayerSpec): void {
    this.calls.push(`addLayer:${layer.id}`);
    this.layers.push(layer);
  }
  removeLayer(id: string): void {
    this.calls.push(`removeLayer:${id}`);
    this.layers.splice(
      this.layers.findIndex((layer) => layer.id === id),
      1,
    );
  }
  hasLayer(id: string): boolean {
    return this.layers.some((layer) => layer.id === id);
  }
  setStyle(style: MapOptions['style']): void {
    this.calls.push('setStyle');
    this.styles.push(style);
    this.styleLoaded = false;
  }
  addMarker(position: GeoPoint, options: MarkerOptions): FakeMarker {
    this.calls.push(`addMarker:${options.label}`);
    const marker = new FakeMarker(position, options);
    this.markers.push(marker);
    return marker;
  }
  resize(): void {
    this.calls.push('resize');
  }
  fitBounds(bounds: readonly number[], options: { animate: boolean }): void {
    this.calls.push('fitBounds');
    this.fits.push({ bounds, animate: options.animate });
  }
  jumpTo(): void {
    this.calls.push('jumpTo');
  }
  onStyleReady(callback: () => void): () => void {
    this.listeners.add(callback);
    if (this.styleLoaded) callback();
    return () => {
      this.listeners.delete(callback);
    };
  }
  onClick(callback: (point: GeoPoint) => void): () => void {
    this.clickListeners.add(callback);
    return () => {
      this.clickListeners.delete(callback);
    };
  }
  /** The visitor clicks the map at `point`. */
  click(point: GeoPoint): void {
    for (const listener of [...this.clickListeners]) listener(point);
  }
  /** How many views listen to clicks. */
  get clickListenerCount(): number {
    return this.clickListeners.size;
  }
  remove(): void {
    this.calls.push('remove');
    this.removed = true;
  }
}

/** A factory that keeps every map it made. */
export function fakeMapFactory(): { factory: MapFactory; maps: FakeMap[] } {
  const maps: FakeMap[] = [];
  return {
    maps,
    factory: (container, options) => {
      const map = new FakeMap(container, options);
      maps.push(map);
      return map;
    },
  };
}

/** `ResizeObserver` and `matchMedia` for jsdom, which has neither. Call `restore` after. */
export function installBrowserStubs(reducedMotion: boolean): {
  observers: { callback: () => void; target: Element | null }[];
  restore: () => void;
} {
  const observers: { callback: () => void; target: Element | null }[] = [];
  class FakeResizeObserver {
    private readonly entry: { callback: () => void; target: Element | null };
    constructor(callback: () => void) {
      this.entry = { callback, target: null };
      observers.push(this.entry);
    }
    observe(target: Element) {
      this.entry.target = target;
    }
    disconnect() {
      this.entry.target = null;
    }
    unobserve() {
      this.entry.target = null;
    }
  }
  const names = ['ResizeObserver', 'matchMedia'] as const;
  const originals = names.map((name) => Object.getOwnPropertyDescriptor(window, name));
  const matchMedia = (query: string) =>
    ({
      matches: reducedMotion && query.includes('prefers-reduced-motion'),
      media: query,
    }) as MediaQueryList;
  const values = [FakeResizeObserver, matchMedia];
  names.forEach((name, at) => {
    Object.defineProperty(window, name, {
      value: values[at],
      configurable: true,
      writable: true,
    });
  });
  return {
    observers,
    restore: () => {
      names.forEach((name, at) => {
        const original = originals[at];
        if (original === undefined) Reflect.deleteProperty(window, name);
        else Object.defineProperty(window, name, original);
      });
    },
  };
}
