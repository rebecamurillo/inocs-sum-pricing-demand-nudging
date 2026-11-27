import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { Gateways } from '../../application/ports/gateways';
import { fakePricingGateway } from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import { emptyCityInstances } from '../../application/ports/fake-city-instance-gateway';
import type { CityDataset } from '../../domain/map';
import { GatewaysProvider } from '../hooks/gateways';
import { fakeMapFactory, installBrowserStubs } from './fake-map';
import {
  MapFactoryProvider,
  MapProvider,
  useMapLayers,
  useMapLegend,
  useMapPanel,
} from './MapContext';
import type { MapDeclaration } from './map-factory';
import { MapPane } from './MapPane';

const dataset: CityDataset = {
  id: 'd1',
  centre: { lat: 46.2, lon: 6.14 },
  radiusM: 3000,
  availableArea: [6, 46, 6.3, 46.4],
};

function gatewaysFor(datasets: CityDataset[], served: boolean): Gateways {
  return {
    systemStatus: { load: () => Promise.reject(new Error('not called')) },
    layoutPreferences: {
      load: () => {
        throw new Error('not called');
      },
      save: () => undefined,
    },
    cityDatasets: { list: () => Promise.resolve(datasets) },
    basemap: {
      exists: () => Promise.resolve(served),
      url: (id) => `/basemap/${id}.pmtiles`,
    },
    cityInstances: emptyCityInstances,
    runs: fakeRunGateway(),
    pricing: fakePricingGateway(),
  };
}

let stubs: ReturnType<typeof installBrowserStubs>;
afterEach(() => {
  stubs.restore();
});
beforeEach(() => {
  stubs = installBrowserStubs(false);
});

function mount(gateways: Gateways, shown = true) {
  const { factory, maps } = fakeMapFactory();
  const client = new QueryClient();
  const tree = (visible: boolean) => (
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={factory}>
          <MapProvider>
            <MapPane shown={visible} datasetId={null} />
          </MapProvider>
        </MapFactoryProvider>
      </GatewaysProvider>
    </QueryClientProvider>
  );
  const view = render(tree(shown));
  return {
    maps,
    rerenderShown: (visible: boolean) => {
      view.rerender(tree(visible));
    },
    view,
  };
}

describe('MapPane', () => {
  it('creates one map with the ground colour style and fades by default', () => {
    const { maps } = mount(gatewaysFor([], false));

    expect(maps).toHaveLength(1);
    expect(maps[0]?.options.fadeDuration).toBe(300);
    expect(maps[0]?.options.style.layers.map((layer) => layer.id)).toEqual(['background']);
    expect(screen.getByRole('region', { name: 'Map' })).toContainElement(
      maps[0]?.container ?? null,
    );
  });

  it('asks for no fade under reduced motion and jumps to the study circle', async () => {
    stubs.restore();
    stubs = installBrowserStubs(true);
    const { maps } = mount(gatewaysFor([dataset], false));
    await act(async () => {
      await Promise.resolve();
    });
    const map = maps[0];
    act(() => {
      map?.emitStyleReady();
    });

    await waitFor(() => {
      expect(map?.fits.length).toBeGreaterThan(0);
    });
    expect(map?.options.fadeDuration).toBe(0);
    expect(map?.fits.every((move) => !move.animate)).toBe(true);
    expect(map?.calls.some((call) => /easeTo|flyTo/.test(call))).toBe(false);
  });

  it('keeps the ground colour only and adds no source when the file is not served', async () => {
    const { maps } = mount(gatewaysFor([dataset], false));
    await act(async () => {
      await Promise.resolve();
    });

    expect(maps[0]?.calls).not.toContain('setStyle');
  });

  it('sets the style with the PMTiles source when the file is served', async () => {
    const { maps } = mount(gatewaysFor([dataset], true));

    await waitFor(() => {
      expect(maps[0]?.styles).toHaveLength(1);
    });
    expect(maps[0]?.styles[0]?.sources).toEqual({
      basemap: { type: 'vector', url: 'pmtiles:///basemap/d1.pmtiles' },
    });
  });

  it('fits the preset circle once the style is ready, and animates when motion is allowed', async () => {
    const { maps } = mount(gatewaysFor([dataset], false));
    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      maps[0]?.emitStyleReady();
    });

    await waitFor(() => {
      expect(maps[0]?.fits).toHaveLength(1);
    });
    expect(maps[0]?.fits[0]?.animate).toBe(true);
    const [west, south, east, north] = maps[0]?.fits[0]?.bounds ?? [];
    expect(west).toBeLessThan(6.14);
    expect(east).toBeGreaterThan(6.14);
    expect(south).toBeLessThan(46.2);
    expect(north).toBeGreaterThan(46.2);
  });

  it('keeps the same map when the pane is hidden and shown again', () => {
    const { maps, rerenderShown } = mount(gatewaysFor([], false));

    rerenderShown(false);
    expect(screen.queryByRole('region', { name: 'Map' })).not.toBeInTheDocument();
    rerenderShown(true);

    expect(screen.getByRole('region', { name: 'Map' })).toBeInTheDocument();
    expect(maps).toHaveLength(1);
    expect(maps[0]?.removed).toBe(false);
  });

  it('resizes the map and refits the circle when the pane changes size', async () => {
    const { maps } = mount(gatewaysFor([dataset], false));
    await act(async () => {
      await Promise.resolve();
    });
    act(() => {
      maps[0]?.emitStyleReady();
    });
    await waitFor(() => {
      expect(maps[0]?.fits).toHaveLength(1);
    });
    const observer = stubs.observers[0];
    expect(observer?.target).toBe(screen.getByRole('region', { name: 'Map' }));

    act(() => {
      observer?.callback();
    });

    const calls = maps[0]?.calls ?? [];
    expect(calls.slice(-2)).toEqual(['resize', 'fitBounds']);
    expect(maps[0]?.fits).toHaveLength(2);
  });

  it('only resizes when there is no circle to fit', () => {
    const { maps } = mount(gatewaysFor([], false));

    act(() => {
      stubs.observers[0]?.callback();
    });

    expect(maps[0]?.calls).toEqual(['resize']);
  });

  it('keeps views off the map while the basemap style loads, then declares them again', async () => {
    const declaration: MapDeclaration = {
      sources: { a: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } },
      layers: [{ id: 'a-layer', type: 'circle', source: 'a', paint: {} }],
    };
    function View() {
      useMapLayers(declaration);
      return null;
    }
    const { factory, maps } = fakeMapFactory();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <GatewaysProvider gateways={gatewaysFor([dataset], true)}>
          <MapFactoryProvider factory={factory}>
            <MapProvider>
              <MapPane shown datasetId={null} />
              <View />
            </MapProvider>
          </MapFactoryProvider>
        </GatewaysProvider>
      </QueryClientProvider>,
    );
    const map = maps[0];
    act(() => {
      map?.emitStyleReady();
    });

    await waitFor(() => {
      expect(map?.styles).toHaveLength(1);
    });
    expect(map?.hasLayer('a-layer')).toBe(false);

    act(() => {
      map?.emitStyleReady();
    });
    expect(map?.hasLayer('a-layer')).toBe(true);
  });

  it('lists the legend entries a view declares over the map, and drops them with the view', () => {
    const entries = [{ label: 'Hub pair without a route', colour: '#be280b' }];
    function View() {
      useMapLegend(entries);
      return null;
    }
    const { factory } = fakeMapFactory();
    const tree = (withView: boolean) => (
      <QueryClientProvider client={new QueryClient()}>
        <GatewaysProvider gateways={gatewaysFor([], false)}>
          <MapFactoryProvider factory={factory}>
            <MapProvider>
              <MapPane shown datasetId={null} />
              {withView && <View />}
            </MapProvider>
          </MapFactoryProvider>
        </GatewaysProvider>
      </QueryClientProvider>
    );
    expect(screen.queryByRole('list', { name: 'Map legend' })).not.toBeInTheDocument();

    const view = render(tree(true));
    expect(screen.getByRole('list', { name: 'Map legend' })).toHaveTextContent(
      'Hub pair without a route',
    );

    view.rerender(tree(false));
    expect(screen.queryByRole('list', { name: 'Map legend' })).not.toBeInTheDocument();
  });

  it('removes the map and stops observing when it unmounts', () => {
    const { maps, view } = mount(gatewaysFor([], false));

    view.unmount();

    expect(maps[0]?.removed).toBe(true);
    expect(stubs.observers[0]?.target).toBeNull();
  });

  it('renders the panel a view declares over the map, and drops it with the view', () => {
    const panel = <p>Map shows</p>;
    function View() {
      useMapPanel(panel);
      return null;
    }
    const { factory } = fakeMapFactory();
    const tree = (withView: boolean) => (
      <QueryClientProvider client={new QueryClient()}>
        <GatewaysProvider gateways={gatewaysFor([], false)}>
          <MapFactoryProvider factory={factory}>
            <MapProvider>
              <MapPane shown datasetId={null} />
              {withView && <View />}
            </MapProvider>
          </MapFactoryProvider>
        </GatewaysProvider>
      </QueryClientProvider>
    );
    expect(screen.queryByText('Map shows')).not.toBeInTheDocument();

    const view = render(tree(true));
    expect(screen.getByText('Map shows')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Map legend' })).not.toBeInTheDocument();

    view.rerender(tree(false));
    expect(screen.queryByText('Map shows')).not.toBeInTheDocument();
  });
});
