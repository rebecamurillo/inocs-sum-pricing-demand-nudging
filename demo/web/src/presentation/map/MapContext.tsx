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
  /** The swatch's line style; dotted when absent. */
  readonly dash?: 'solid' | 'dashed' | 'dotted';
}

interface MapContextValue {
  readonly ready: ReadyMap | null;
  readonly fitTarget: GeoBounds | null;
  /** Pixels around the fit target; the map's default when undefined. */
  readonly fitPadding: number | undefined;
  readonly legend: readonly LegendEntry[];
  readonly legendNote: string | null;
  readonly setLegend: (entries: readonly LegendEntry[], note: string | null) => void;
  /** A view's own controls and legend over the map (L-3's "Map shows" and its legend). */
  readonly panel: ReactNode | null;
  readonly setPanel: (panel: ReactNode | null) => void;
  readonly attach: (handle: MapHandle | null) => void;
  /** Call before `setStyle`: until the new style loads, views must not add to the map. */
  readonly restyling: () => void;
  readonly setFitTarget: (bounds: GeoBounds | null, padding?: number) => void;
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
  const [fit, setFit] = useState<{ bounds: GeoBounds | null; padding: number | undefined }>({
    bounds: null,
    padding: undefined,
  });
  const [legendState, setLegendState] = useState<{
    entries: readonly LegendEntry[];
    note: string | null;
  }>({ entries: [], note: null });
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

  const setFitTarget = useCallback((bounds: GeoBounds | null, padding?: number) => {
    setFit({ bounds, padding });
  }, []);
  const setLegend = useCallback((entries: readonly LegendEntry[], note: string | null) => {
    setLegendState({ entries, note });
  }, []);

  const value = useMemo(
    () => ({
      ready,
      fitTarget: fit.bounds,
      fitPadding: fit.padding,
      legend: legendState.entries,
      legendNote: legendState.note,
      setLegend,
      panel,
      setPanel,
      attach,
      restyling,
      setFitTarget,
    }),
    [ready, fit, legendState, setLegend, setFitTarget, panel, attach, restyling],
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

/** Calls `handler` with the point of each click on the map while the view is shown. */
export function useMapClick(handler: (point: GeoPoint) => void): void {
  const { ready } = useMapContext();
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  useEffect(() => {
    if (ready === null) return undefined;
    return ready.handle.onClick((point) => {
      latest.current(point);
    });
  }, [ready]);
}

/** Where the map looks (a study circle's bounds); null leaves the default. */
export function useMapFit(bounds: GeoBounds | null, padding?: number): void {
  const { setFitTarget } = useMapContext();
  useEffect(() => {
    setFitTarget(bounds, padding);
    return () => {
      setFitTarget(null);
    };
  }, [bounds, padding, setFitTarget]);
}

/** The legend entries a view shows over the map. Pass a memoised array; they go with the view. */
export function useMapLegend(entries: readonly LegendEntry[], note: string | null = null): void {
  const { setLegend } = useMapContext();
  useEffect(() => {
    setLegend(entries, note);
    return () => {
      setLegend([], null);
    };
  }, [entries, note, setLegend]);
}

/** A pin the view stands on the map: a lettered disc named `label`. */
export interface MapPin {
  readonly point: GeoPoint;
  readonly label: string;
  readonly text: string;
  readonly colour: string;
}

/**
 * Non-draggable lettered markers while the map is ready. Pass a memoised array; the markers are
 * replaced when it changes and removed with the view.
 */
export function useMapPins(pins: readonly MapPin[]): void {
  const { ready } = useMapContext();
  useEffect(() => {
    if (ready === null) return undefined;
    const markers = pins.map((pin) =>
      ready.handle.addMarker(pin.point, {
        draggable: false,
        label: pin.label,
        text: pin.text,
        colour: pin.colour,
      }),
    );
    return () => {
      for (const marker of markers) marker.remove();
    };
  }, [ready, pins]);
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
