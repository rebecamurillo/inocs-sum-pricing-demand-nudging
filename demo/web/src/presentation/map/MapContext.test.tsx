import { act, render, renderHook } from '@testing-library/react';
import { useMemo, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { distanceM } from '../../domain/map';
import { FakeMap, fakeMapFactory } from './fake-map';
import {
  MapFactoryProvider,
  MapProvider,
  useMapFactory,
  useMapClick,
  useMapFit,
  useMapHandles,
  useMapLayers,
  useMapPaneContext,
} from './MapContext';
import type { MapDeclaration } from './map-factory';

const declaration = (id: string): MapDeclaration => ({
  sources: { [id]: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } },
  layers: [{ id: `${id}-layer`, type: 'circle', source: id, paint: {} }],
});

function rig() {
  const map = new FakeMap(document.createElement('div'), {
    style: { version: 8, sources: {}, layers: [] },
    fadeDuration: 0,
  });
  const wrapper = ({ children }: { children: ReactNode }) => <MapProvider>{children}</MapProvider>;
  return { map, wrapper };
}

const orNone = (decl: MapDeclaration | null) => decl;

function useBoth(next: MapDeclaration | null, map: FakeMap) {
  const { attach } = useMapPaneContext();
  useMapLayers(next);
  return {
    attach: () => {
      attach(map);
    },
  };
}

describe('the map factory context', () => {
  it('hands the factory over', () => {
    const { factory } = fakeMapFactory();
    const { result } = renderHook(() => useMapFactory(), {
      wrapper: ({ children }) => (
        <MapFactoryProvider factory={factory}>{children}</MapFactoryProvider>
      ),
    });

    expect(result.current).toBe(factory);
  });

  it('fails with an explanation below no provider', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    expect(() => renderHook(() => useMapFactory())).toThrow('MapFactoryProvider');
    error.mockRestore();
  });
});

describe('useMapLayers', () => {
  it('adds nothing before the map is ready, then adds the sources and layers', () => {
    const { map, wrapper } = rig();
    const decl = declaration('a');
    const { result } = renderHook(() => useBoth(decl, map), { wrapper });

    act(() => {
      result.current.attach();
    });
    expect(map.calls).toEqual([]);
    act(() => {
      map.emitStyleReady();
    });

    expect(map.calls).toEqual(['addSource:a', 'addLayer:a-layer']);
  });

  it('swaps the layers of another declaration on the same map', () => {
    const { map, wrapper } = rig();
    const { result, rerender } = renderHook(({ decl }) => useBoth(decl, map), {
      wrapper,
      initialProps: { decl: orNone(declaration('a')) },
    });
    act(() => {
      result.current.attach();
    });
    act(() => {
      map.emitStyleReady();
    });

    rerender({ decl: declaration('b') });
    expect(map.layers.map((layer) => layer.id)).toEqual(['b-layer']);
    expect([...map.sources.keys()]).toEqual(['b']);

    rerender({ decl: null });
    expect(map.layers).toEqual([]);
    expect(map.sources.size).toBe(0);
  });

  it('removes its layers when the view unmounts', () => {
    const { map, wrapper } = rig();
    const decl = declaration('a');
    function View() {
      useMapLayers(useMemo(() => decl, []));
      return null;
    }
    function Pane() {
      const { attach } = useMapPaneContext();
      return (
        <button
          onClick={() => {
            attach(map);
          }}
        >
          attach
        </button>
      );
    }
    const { getByText, rerender } = render(
      <>
        <Pane />
        <View />
      </>,
      { wrapper },
    );
    act(() => {
      getByText('attach').click();
    });
    act(() => {
      map.emitStyleReady();
    });
    expect(map.layers).toHaveLength(1);

    rerender(<Pane />);

    expect(map.layers).toEqual([]);
    expect(map.sources.size).toBe(0);
  });

  it('declares its layers again after a new style wiped them', () => {
    const { map, wrapper } = rig();
    const decl = declaration('a');
    const { result } = renderHook(() => useBoth(decl, map), { wrapper });
    act(() => {
      result.current.attach();
    });
    act(() => {
      map.emitStyleReady();
    });

    act(() => {
      map.setStyle({ version: 8, sources: {}, layers: [] });
      map.emitStyleReady();
    });

    expect(map.layers.map((layer) => layer.id)).toEqual(['a-layer']);
    expect(map.sources.has('a')).toBe(true);
  });

  it('is forgotten when the map is detached', () => {
    const { map, wrapper } = rig();
    const { result } = renderHook(() => ({ both: useBoth(null, map), ctx: useMapPaneContext() }), {
      wrapper,
    });
    act(() => {
      result.current.ctx.attach(map);
    });
    act(() => {
      map.emitStyleReady();
    });
    expect(result.current.ctx.ready?.revision).toBe(1);

    act(() => {
      result.current.ctx.attach(null);
    });

    expect(result.current.ctx.ready).toBeNull();
  });
});

describe('useMapFit', () => {
  it('sets the fit target while mounted and clears it after', () => {
    const { wrapper } = rig();
    const bounds = [6, 46, 6.3, 46.4] as const;
    const { result, rerender } = renderHook(
      ({ on }) => {
        const ctx = useMapPaneContext();
        useMapFit(on ? bounds : null);
        return { ctx, fitted: null };
      },
      { wrapper, initialProps: { on: true } },
    );
    expect(result.current.ctx.fitTarget).toEqual(bounds);

    rerender({ on: false });

    expect(result.current.ctx.fitTarget).toBeNull();
  });
});

describe('useMapHandles', () => {
  const circle = { centre: { lat: 46.2, lon: 6.14 }, radiusM: 3000 };

  function mounted(initial: typeof circle | null) {
    const { map, wrapper } = rig();
    const onCentre = vi.fn();
    const onRadius = vi.fn();
    const hook = renderHook(
      ({ at }) => {
        const ctx = useMapPaneContext();
        useMapHandles(at, onCentre, onRadius);
        return ctx;
      },
      { wrapper, initialProps: { at: initial } },
    );
    act(() => {
      hook.result.current.attach(map);
    });
    act(() => {
      map.emitStyleReady();
    });
    return { map, onCentre, onRadius, ...hook };
  }

  it('adds no marker before the map is ready or without a circle', () => {
    const { wrapper, map } = rig();
    renderHook(
      () => {
        useMapHandles(circle, vi.fn(), vi.fn());
      },
      { wrapper },
    );
    expect(map.markers).toEqual([]);

    const none = mounted(null);
    expect(none.map.markers).toEqual([]);
  });

  it('adds a draggable centre marker and a radius marker on the circle edge', () => {
    const { map } = mounted(circle);

    expect(map.markers.map((marker) => marker.options.label)).toEqual([
      'Study circle centre: drag to move it',
      'Study circle edge: drag to change the radius',
    ]);
    expect(map.markers.every((marker) => marker.options.draggable)).toBe(true);
    const [centre, edge] = map.markers;
    expect(centre?.position).toEqual(circle.centre);
    expect(distanceM(circle.centre, edge?.position ?? circle.centre)).toBeCloseTo(3000, 0);
  });

  it('reports the centre of a drag, to five decimals', () => {
    const { map, onCentre } = mounted(circle);

    act(() => {
      map.markers[0]?.drag({ lat: 46.2123456789, lon: 6.1512345678 });
    });
    act(() => {
      map.markers[0]?.dragEnd({ lat: 46.21235, lon: 6.15123 });
    });

    expect(onCentre).toHaveBeenNthCalledWith(1, { lat: 46.21235, lon: 6.15123 });
    expect(onCentre).toHaveBeenNthCalledWith(2, { lat: 46.21235, lon: 6.15123 });
  });

  it('reports the radius of a drag as the distance to the centre in steps of 100 m', () => {
    const { map, onRadius } = mounted(circle);
    const [, edge] = map.markers;

    act(() => {
      // About 4 060 m east of the centre.
      edge?.drag({ lat: 46.2, lon: 6.14 + 4060 / (111_195 * Math.cos((46.2 * Math.PI) / 180)) });
    });

    expect(onRadius).toHaveBeenCalledWith(4100);
  });

  it('moves the markers with the values and removes them with the circle', () => {
    const { map, rerender } = mounted(circle);
    const [centre, edge] = map.markers;

    rerender({ at: { centre: { lat: 46.25, lon: 6.2 }, radiusM: 2000 } });
    expect(centre?.position).toEqual({ lat: 46.25, lon: 6.2 });
    expect(distanceM({ lat: 46.25, lon: 6.2 }, edge?.position ?? circle.centre)).toBeCloseTo(
      2000,
      0,
    );
    expect(map.markers).toHaveLength(2);

    rerender({ at: null });
    expect(map.markers.every((marker) => marker.removed)).toBe(true);
  });

  it('adds fresh markers after a new style and removes the old ones', () => {
    const { map } = mounted(circle);

    act(() => {
      map.setStyle({ version: 8, sources: {}, layers: [] });
      map.emitStyleReady();
    });

    expect(map.markers).toHaveLength(4);
    expect(map.markers.slice(0, 2).every((marker) => marker.removed)).toBe(true);
    expect(map.markers.slice(2).every((marker) => !marker.removed)).toBe(true);
  });
});

describe('useMapClick', () => {
  it('hears the clicks of the ready map with the latest handler, and stops with the view', () => {
    const { map, wrapper } = rig();
    const first = vi.fn();
    const second = vi.fn();
    const { result, rerender, unmount } = renderHook(
      ({ handler }) => {
        const { attach } = useMapPaneContext();
        useMapClick(handler);
        return {
          attach: () => {
            attach(map);
          },
        };
      },
      { wrapper, initialProps: { handler: first } },
    );
    act(() => {
      result.current.attach();
    });
    expect(map.clickListenerCount).toBe(0);
    act(() => {
      map.emitStyleReady();
    });
    expect(map.clickListenerCount).toBe(1);

    rerender({ handler: second });
    map.click({ lat: 46.2, lon: 6.14 });

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledWith({ lat: 46.2, lon: 6.14 });
    unmount();
    expect(map.clickListenerCount).toBe(0);
  });
});
