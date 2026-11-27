import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { GeoBounds } from '../../domain/map';
import type { MapDeclaration, MapFactory, MapHandle } from './map-factory';

const MapFactoryContext = createContext<MapFactory | null>(null);

/** Hands the map factory to the map pane. The composition root builds the real one. */
export function MapFactoryProvider({
  factory,
  children,
}: {
  factory: MapFactory;
  children: ReactNode;
}) {
  return <MapFactoryContext.Provider value={factory}>{children}</MapFactoryContext.Provider>;
}

export function useMapFactory(): MapFactory {
  const factory = useContext(MapFactoryContext);
  if (factory === null) throw new Error('useMapFactory must be called below a MapFactoryProvider.');
  return factory;
}

/** The map once a style has loaded; `revision` grows with each style, which wipes view layers. */
interface ReadyMap {
  readonly handle: MapHandle;
  readonly revision: number;
}

interface MapContextValue {
  readonly ready: ReadyMap | null;
  readonly fitTarget: GeoBounds | null;
  readonly attach: (handle: MapHandle | null) => void;
  /** Call before `setStyle`: until the new style loads, views must not add to the map. */
  readonly restyling: () => void;
  readonly setFitTarget: (bounds: GeoBounds | null) => void;
}

const MapContext = createContext<MapContextValue | null>(null);

function useMapContext(): MapContextValue {
  const value = useContext(MapContext);
  if (value === null) throw new Error('The map context is used below a MapProvider.');
  return value;
}

/**
 * Holds the one map of the Lab. The map pane creates it and attaches it; views declare what
 * they draw through `useMapLayers` and where to look through `useMapFit`, never a new map.
 */
export function MapProvider({ children }: { children: ReactNode }) {
  const [handle, setHandle] = useState<MapHandle | null>(null);
  const [ready, setReady] = useState<ReadyMap | null>(null);
  const [fitTarget, setFitTarget] = useState<GeoBounds | null>(null);

  useEffect(() => {
    if (handle === null) return undefined;
    return handle.onStyleReady(() => {
      setReady((previous) => ({
        handle,
        revision: previous?.handle === handle ? previous.revision + 1 : 1,
      }));
    });
  }, [handle]);

  const attach = useCallback((next: MapHandle | null) => {
    setHandle(next);
    if (next === null) setReady(null);
  }, []);

  // A loading style refuses new sources and layers ("Style is not done loading").
  const restyling = useCallback(() => {
    setReady(null);
  }, []);

  const value = useMemo(
    () => ({ ready, fitTarget, attach, restyling, setFitTarget }),
    [ready, fitTarget, attach, restyling],
  );
  return <MapContext.Provider value={value}>{children}</MapContext.Provider>;
}

/** What the pane needs of the context: attach the map, read when it is ready and where to look. */
export function useMapPaneContext() {
  return useMapContext();
}

/**
 * The sources and layers a view puts on the map. They are added when the map is ready and
 * removed when the declaration changes, the view goes away or the style is replaced.
 * Pass a memoised declaration, or null for none.
 */
export function useMapLayers(declaration: MapDeclaration | null): void {
  const { ready } = useMapContext();
  useEffect(() => {
    if (ready === null || declaration === null) return undefined;
    const { handle } = ready;
    for (const [id, source] of Object.entries(declaration.sources)) {
      if (!handle.hasSource(id)) handle.addSource(id, source);
    }
    for (const layer of declaration.layers) handle.addLayer(layer);
    return () => {
      for (const layer of [...declaration.layers].reverse()) {
        if (handle.hasLayer(layer.id)) handle.removeLayer(layer.id);
      }
      for (const id of Object.keys(declaration.sources)) {
        if (handle.hasSource(id)) handle.removeSource(id);
      }
    };
  }, [ready, declaration]);
}

/** Where the map looks (a study circle's bounds); null leaves the default. */
export function useMapFit(bounds: GeoBounds | null): void {
  const { setFitTarget } = useMapContext();
  useEffect(() => {
    setFitTarget(bounds);
    return () => {
      setFitTarget(null);
    };
  }, [bounds, setFitTarget]);
}
