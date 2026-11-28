import { emptyTrips } from '../../application/ports/fake-trip-gateway';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { emptyCityInstances } from '../../application/ports/fake-city-instance-gateway';
import { fakePricingGateway } from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { HubDifference } from '../../domain/comparison';
import type { CompareMeasure } from '../../domain/comparison-text';
import type { MapHub, MapHubPair } from '../../domain/map';
import type { ResultNumber } from '../../domain/pricing-result';
import { GatewaysProvider } from '../hooks/gateways';
import { fakeMapFactory, installBrowserStubs } from '../map/fake-map';
import { MapFactoryProvider, MapProvider } from '../map/MapContext';
import { MapPane } from '../map/MapPane';
import { CompareMap } from './CompareMap';

const gateways: Gateways = {
  systemStatus: { load: () => Promise.reject(new Error('not called')) },
  layoutPreferences: { load: () => ({}) as never, save: () => undefined },
  cityDatasets: { list: () => Promise.resolve([]) },
  basemap: { exists: () => Promise.resolve(false), url: () => '' },
  cityInstances: emptyCityInstances,
  runs: fakeRunGateway(),
  pricing: fakePricingGateway(),
  trips: emptyTrips,
};

let stubs: ReturnType<typeof installBrowserStubs>;
beforeEach(() => {
  stubs = installBrowserStubs(false);
});
afterEach(() => {
  stubs.restore();
});

const num = (value: number): ResultNumber => ({
  value,
  unit: 'chf',
  source: 'derived',
  group: 'headline',
});
const difference = (
  hubId: string,
  price: number | null,
  rides: number,
  flat: number | null = price,
): HubDifference => ({
  hubId,
  meanPriceA: null,
  meanPriceB: null,
  priceDifference: price === null ? null : num(price),
  priceBMinusFlat: flat === null ? null : num(flat),
  ridesStartingA: null,
  ridesStartingB: null,
  ridesStartingDifference: num(rides),
});

const HUBS: MapHub[] = [
  { id: 'H4', lat: 46.198, lon: 6.139, outline: null },
  { id: 'H9', lat: 46.2, lon: 6.16, outline: null },
  { id: 'H12', lat: 46.21, lon: 6.142, outline: null },
];
const MIXED = [
  difference('H4', -0.4, 1200),
  difference('H9', 0.2, -50),
  difference('H12', null, 0),
];
const ZERO = [difference('H4', 0, 0), difference('H9', 0, 0)];

function Harness({
  pair,
  differences,
  hubs = HUBS,
}: {
  pair: MapHubPair | null;
  differences: readonly HubDifference[];
  hubs?: readonly MapHub[];
}) {
  const [measure, setMeasure] = useState<CompareMeasure>('priceDifference');
  return (
    <CompareMap
      centre={{ lat: 46.2, lon: 6.14 }}
      radiusM={3000}
      hubs={hubs}
      differences={differences}
      a="B"
      b="C"
      measure={measure}
      onMeasure={setMeasure}
      shownPair={pair}
    />
  );
}

function mount(differences: readonly HubDifference[], pair: MapHubPair | null = null) {
  const { factory, maps } = fakeMapFactory();
  const tree = (nextPair: MapHubPair | null) => (
    <QueryClientProvider client={new QueryClient()}>
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={factory}>
          <MapProvider>
            <MapPane shown datasetId={null} />
            <Harness pair={nextPair} differences={differences} />
          </MapProvider>
        </MapFactoryProvider>
      </GatewaysProvider>
    </QueryClientProvider>
  );
  const view = render(tree(pair));
  const map = maps[0];
  if (map === undefined) throw new Error('no map');
  act(() => {
    map.emitStyleReady();
  });
  return {
    map,
    update: (nextPair: MapHubPair | null) => {
      view.rerender(tree(nextPair));
    },
  };
}

const layerIds = (map: { layers: readonly { id: string }[] }) => map.layers.map((l) => l.id);
const legend = () => screen.getByRole('group', { name: 'Map legend' });

describe('CompareMap', () => {
  it('draws the circle, the outlines and the discs on the one map and fits the circle', () => {
    const { map } = mount(MIXED);

    expect(layerIds(map)).toEqual(['l4-study-circle', 'l4-hub-outlines', 'l4-hub-discs']);
    const discs = map.sources.get('l4-hub-discs');
    expect(discs?.type === 'geojson' && discs.data.features).toHaveLength(2);
    expect(map.fits.length).toBeGreaterThan(0);
  });

  it('offers the three measures by letters and a legend with the anchors', async () => {
    const { map } = mount(MIXED);
    const user = userEvent.setup();

    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Mean bike price: C − B',
      'Mean bike price: C − flat price',
      'Bike rides starting: C − B',
    ]);
    expect(screen.getByLabelText('Map shows')).toHaveValue('priceDifference');
    expect(legend()).toHaveTextContent('Mean bike price: C − B');
    expect(legend()).toHaveTextContent(
      "−0.40 CHF per ride0 CHF per ride+0.40 CHF per ridecomputed from the model's flows",
    );

    await user.selectOptions(screen.getByLabelText('Map shows'), 'ridesStartingDifference');
    expect(legend()).toHaveTextContent('Bike rides starting: C − B');
    expect(legend()).toHaveTextContent('−1 200 rides0 rides+1 200 rides');
    const discs = map.sources.get('l4-hub-discs');
    expect(discs?.type === 'geojson' && discs.data.features).toHaveLength(3);
  });

  it('reads zero anchors and grey discs when every difference is 0', () => {
    const { map } = mount(ZERO);

    expect(legend()).toHaveTextContent('−0.00 CHF per ride0 CHF per ride+0.00 CHF per ride');
    const discs = map.sources.get('l4-hub-discs');
    expect(discs?.type === 'geojson' && discs.data.features.map((f) => f.properties)).toEqual([
      { id: 'H4', value: 0, colour: '#c9cdc8', radius: 10 },
      { id: 'H9', value: 0, colour: '#c9cdc8', radius: 10 },
    ]);
  });

  it('draws one pair line over dimmed discs and removes it', () => {
    const { map, update } = mount(MIXED);

    update({ originHub: 'H4', destinationHub: 'H9' });
    expect(layerIds(map)).toEqual([
      'l4-study-circle',
      'l4-hub-outlines',
      'l4-hub-discs',
      'l3-selected-pair',
    ]);
    expect(map.layers.find((l) => l.id === 'l4-hub-discs')?.paint['circle-opacity']).toBe(0.35);

    update(null);
    expect(layerIds(map)).toEqual(['l4-study-circle', 'l4-hub-outlines', 'l4-hub-discs']);
  });

  it('leaves the camera alone when it renders again with the same circle', () => {
    const { map, update } = mount(MIXED);
    const fits = map.fits.length;

    update(null);

    expect(map.fits).toHaveLength(fits);
  });
});
