import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { destinationPoint, distanceM, type GeoBounds, type GeoPoint } from '../../domain/map';
import type { MapDeclaration, MapFactory, MapHandle, MarkerHandle } from './map-factory';

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

/** One line of the legend a view shows over the map: a dotted line in its colour and a label. */
export interface LegendEntry {
  readonly label: string;
  readonly colour: string;
}

interface MapContextValue {
  readonly ready: ReadyMap | null;
  readonly fitTarget: GeoBounds | null;
  readonly legend: readonly LegendEntry[];
  readonly setLegend: (entries: readonly LegendEntry[]) => void;
  /** A view's own controls and legend over the map (L-3's "Map shows" and its legend). */
  readonly panel: ReactNode | null;
  readonly setPanel: (panel: ReactNode | null) => void;
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
  const [legend, setLegend] = useState<readonly LegendEntry[]>([]);
  const [panel, setPanel] = useState<ReactNode | null>(null);

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
    () => ({
      ready,
      fitTarget,
      legend,
      setLegend,
      panel,
      setPanel,
      attach,
      restyling,
      setFitTarget,
    }),
    [ready, fitTarget, legend, panel, attach, restyling],
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

/** The legend entries a view shows over the map. Pass a memoised array; they go with the view. */
export function useMapLegend(entries: readonly LegendEntry[]): void {
  const { setLegend } = useMapContext();
  useEffect(() => {
    setLegend(entries);
    return () => {
      setLegend([]);
    };
  }, [entries, setLegend]);
}

/** A panel of the view's own over the map. Pass a memoised node; it goes with the view. */
export function useMapPanel(node: ReactNode | null): void {
  const { setPanel } = useMapContext();
  useEffect(() => {
    setPanel(node);
    return () => {
      setPanel(null);
    };
  }, [node, setPanel]);
}

/** The study circle a draft form edits. */
export interface StudyCircle {
  readonly centre: GeoPoint;
  readonly radiusM: number;
}

const RADIUS_BEARING_DEG = 90;
const COORDINATE_DECIMALS = 1e5;
const RADIUS_STEP_M = 100;

/**
 * A draggable centre marker and a radius marker on the east edge of the study circle. Dragging
 * the centre reports the new centre; dragging the radius marker reports the distance to the
 * centre, to 0.1 km. The markers exist while `circle` is not null and the map is ready, follow
 * the circle's values and are removed when the circle goes away.
 */
export function useMapHandles(
  circle: StudyCircle | null,
  onCentre: (centre: GeoPoint) => void,
  onRadius: (radiusM: number) => void,
): void {
  const { ready } = useMapContext();
  const active = circle !== null;
  const latest = useRef({ circle, onCentre, onRadius });
  const markers = useRef<{ centre: MarkerHandle; radius: MarkerHandle } | null>(null);

  useEffect(() => {
    latest.current = { circle, onCentre, onRadius };
  });

  useEffect(() => {
    const current = latest.current.circle;
    if (ready === null || !active || current === null) return undefined;
    const centre = ready.handle.addMarker(current.centre, {
      draggable: true,
      label: 'Study circle centre: drag to move it',
      onDrag: (position) => {
        latest.current.onCentre(roundCentre(position));
      },
      onDragEnd: (position) => {
        latest.current.onCentre(roundCentre(position));
      },
    });
    const reportRadius = (position: GeoPoint) => {
      const at = latest.current.circle;
      if (at === null) return;
      const metres = distanceM(at.centre, position);
      latest.current.onRadius(Math.round(metres / RADIUS_STEP_M) * RADIUS_STEP_M);
    };
    const radius = ready.handle.addMarker(
      destinationPoint(current.centre, current.radiusM, RADIUS_BEARING_DEG),
      {
        draggable: true,
        label: 'Study circle edge: drag to change the radius',
        onDrag: reportRadius,
        onDragEnd: reportRadius,
      },
    );
    markers.current = { centre, radius };
    return () => {
      centre.remove();
      radius.remove();
      markers.current = null;
    };
  }, [ready, active]);

  const lat = circle?.centre.lat;
  const lon = circle?.centre.lon;
  const radiusM = circle?.radiusM;
  useEffect(() => {
    const held = markers.current;
    if (held === null || lat === undefined || lon === undefined || radiusM === undefined) return;
    held.centre.setPosition({ lat, lon });
    held.radius.setPosition(destinationPoint({ lat, lon }, radiusM, RADIUS_BEARING_DEG));
  }, [lat, lon, radiusM, ready]);
}

function roundCentre(position: GeoPoint): GeoPoint {
  return {
    lat: Math.round(position.lat * COORDINATE_DECIMALS) / COORDINATE_DECIMALS,
    lon: Math.round(position.lon * COORDINATE_DECIMALS) / COORDINATE_DECIMALS,
  };
}
