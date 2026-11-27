import { act, render, renderHook } from '@testing-library/react';
import { useMemo, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { FakeMap, fakeMapFactory } from './fake-map';
import {
  MapFactoryProvider,
  MapProvider,
  useMapFactory,
  useMapFit,
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
