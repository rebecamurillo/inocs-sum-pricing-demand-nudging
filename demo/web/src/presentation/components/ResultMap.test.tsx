import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { emptyCityInstances } from '../../application/ports/fake-city-instance-gateway';
import { fakePricingGateway, sampleHubResults } from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { MapMeasure } from '../../domain/hub-pair-table';
import type { MapHubPair } from '../../domain/map';
import { GatewaysProvider } from '../hooks/gateways';
import { fakeMapFactory, installBrowserStubs } from '../map/fake-map';
import { MapFactoryProvider, MapProvider } from '../map/MapContext';
import { MapPane } from '../map/MapPane';
import { ResultMap } from './ResultMap';

const gateways: Gateways = {
  systemStatus: { load: () => Promise.reject(new Error('not called')) },
  layoutPreferences: { load: () => ({}) as never, save: () => undefined },
  cityDatasets: { list: () => Promise.resolve([]) },
  basemap: { exists: () => Promise.resolve(false), url: () => '' },
  cityInstances: emptyCityInstances,
  runs: fakeRunGateway(),
  pricing: fakePricingGateway(),
};

let stubs: ReturnType<typeof installBrowserStubs>;
beforeEach(() => {
  stubs = installBrowserStubs(false);
});
afterEach(() => {
  stubs.restore();
});

// Stable as the query's data is; the centre is a new object each render, as the view passes it.
const HUBS = sampleHubResults();

function Harness({ pair, show }: { pair: MapHubPair | null; show: boolean }) {
  const [measure, setMeasure] = useState<MapMeasure>('ridesStarting');
  return show ? (
    <ResultMap
      centre={{ lat: 46.2, lon: 6.14 }}
      radiusM={3000}
      hubs={HUBS}
      measure={measure}
      onMeasure={setMeasure}
      shownPair={pair}
      periodLabel="Monday 08:00–09:00"
    />
  ) : null;
}

function mount(pair: MapHubPair | null = null, show = true) {
  const { factory, maps } = fakeMapFactory();
  const tree = (nextPair: MapHubPair | null, visible: boolean) => (
    <QueryClientProvider client={new QueryClient()}>
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={factory}>
          <MapProvider>
            <MapPane shown datasetId={null} />
            <Harness pair={nextPair} show={visible} />
          </MapProvider>
        </MapFactoryProvider>
      </GatewaysProvider>
    </QueryClientProvider>
  );
  const view = render(tree(pair, show));
  const map = maps[0];
  if (map === undefined) throw new Error('no map');
  act(() => {
    map.emitStyleReady();
  });
  return {
    map,
    maps,
    update: (nextPair: MapHubPair | null, visible = true) => {
      view.rerender(tree(nextPair, visible));
    },
  };
}

const layerIds = (map: { layers: readonly { id: string }[] }) => map.layers.map((l) => l.id);

describe('ResultMap', () => {
  it('draws the study circle and one disc layer on the one map, with no pair line', () => {
    const { map, maps } = mount();

    expect(maps).toHaveLength(1);
    expect(layerIds(map)).toEqual(['l3-study-circle', 'l3-hub-discs']);
    expect(map.fits.length).toBeGreaterThan(0);
  });

  it('offers the selector and the legend of the measure', async () => {
    const { map } = mount();
    const user = userEvent.setup();

    const select = screen.getByLabelText('Map shows');
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Bike rides starting at each hub',
      'Bike rides ending at each hub',
      'Mean bike price from each hub',
    ]);
    expect(screen.getByRole('group', { name: 'Map legend' })).toHaveTextContent(
      "Bike rides starting at each hub, 08:00–09:00 · One disc per hub; a bike ride is one bike leg. Computed from the model's flows.",
    );

    await user.selectOptions(select, 'ridesEnding');
    expect(screen.getByRole('group', { name: 'Map legend' })).toHaveTextContent(
      /^Bike rides ending at each hub, 08:00–09:00 · /,
    );
    await user.selectOptions(select, 'meanPrice');
    expect(screen.getByRole('group', { name: 'Map legend' })).toHaveTextContent(
      /^Mean bike price from each hub, 08:00–09:00 · /,
    );
    const source = map.sources.get('l3-hub-discs');
    expect(source?.type === 'geojson' && source.data.features).toHaveLength(1);
    expect(layerIds(map)).toEqual(['l3-study-circle', 'l3-hub-discs']);
  });

  it('draws one pair line over dimmed discs, replaces it and removes it', () => {
    const { map, update } = mount();

    update({ originHub: 'H4', destinationHub: 'H9' });
    expect(layerIds(map)).toEqual(['l3-study-circle', 'l3-hub-discs', 'l3-selected-pair']);
    expect(map.layers.find((l) => l.id === 'l3-hub-discs')?.paint['circle-opacity']).toBe(0.35);

    update({ originHub: 'H9', destinationHub: 'H12' });
    const line = map.sources.get('l3-selected-pair');
    expect(line?.type === 'geojson' && line.data.features[0]?.properties).toEqual({
      origin: 'H9',
      destination: 'H12',
    });
    expect(layerIds(map).filter((id) => id === 'l3-selected-pair')).toHaveLength(1);

    update(null);
    expect(layerIds(map)).toEqual(['l3-study-circle', 'l3-hub-discs']);
    expect(map.layers.find((l) => l.id === 'l3-hub-discs')?.paint['circle-opacity']).toBe(1);
  });

  it('keeps the camera and the layers when the view renders again with the same circle', () => {
    const { map, update } = mount();
    const fits = map.fits.length;
    const calls = map.calls.length;

    update(null);

    expect(map.fits).toHaveLength(fits);
    expect(map.calls).toHaveLength(calls);
  });

  it('removes every layer, the panel and the fit when it goes away', () => {
    const { map, update } = mount();

    update(null, false);

    expect(map.layers).toEqual([]);
    expect(map.sources.size).toBe(0);
    expect(screen.queryByLabelText('Map shows')).not.toBeInTheDocument();
  });
});
