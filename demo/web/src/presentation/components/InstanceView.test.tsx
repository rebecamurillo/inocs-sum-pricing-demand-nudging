import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CityInstanceGateway } from '../../application/ports/city-instance-gateway';
import {
  fakeCityInstances,
  sampleFailedRoutes,
  sampleVersion,
} from '../../application/ports/fake-city-instance-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { RouteFailure } from '../../domain/city-instance';
import { GatewaysProvider } from '../hooks/gateways';
import { fakeMapFactory, installBrowserStubs, type FakeMap } from '../map/fake-map';
import { MapFactoryProvider, MapProvider } from '../map/MapContext';
import { MapPane } from '../map/MapPane';
import { InstanceView } from './InstanceView';

const failures: RouteFailure[] = [
  {
    originHub: 'H1',
    destinationHub: 'H2',
    query: 'pt_bike',
    kind: 'technical',
    message: 'timeout',
    attempts: 4,
  },
  {
    originHub: 'H2',
    destinationHub: 'H1',
    query: 'car',
    kind: 'no_route',
    message: 'none',
    attempts: 1,
  },
];

const failedVersion = { ...sampleVersion, routes: sampleFailedRoutes };

function mount(cityInstances: CityInstanceGateway, advancedView = false) {
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.reject(new Error('not called')) },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances,
  };
  const { factory, maps } = fakeMapFactory();
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={factory}>
          <MapProvider>
            <MapPane shown datasetId={null} />
            <InstanceView versionId="geneva-3km.v1" advancedView={advancedView} />
          </MapProvider>
        </MapFactoryProvider>
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  const map = (): FakeMap => {
    const found = maps[0];
    if (found === undefined) throw new Error('no map');
    return found;
  };
  return { map };
}

let stubs: ReturnType<typeof installBrowserStubs>;
beforeEach(() => {
  stubs = installBrowserStubs(false);
});
afterEach(() => {
  stubs.restore();
});

const found = (text: string | RegExp) => screen.findByText(text);

describe('InstanceView · the saved card', () => {
  it('shows the skeleton while the reads are pending', () => {
    mount(fakeCityInstances({ version: () => new Promise(() => undefined) }));

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
  });

  it('writes the brief, the name and tag, the ready line and the five counts', async () => {
    mount(fakeCityInstances());

    expect(await found('City instance · pipeline steps 1 to 4')).toBeInTheDocument();
    expect(
      screen.getByText(
        'The study area prepared for the pricing model: stops and bike stations, hubs, routes between hubs, and the travellers and bikes of the period.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Geneva 3 km' })).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(
      screen.getByText('Ready · saved 12 Nov 2026 · used by 3 pricing versions'),
    ).toBeInTheDocument();
    const counts = screen.getAllByRole('term').slice(0, 5);
    expect(counts.map((term) => term.textContent)).toEqual([
      'Stops and platforms',
      'Bike stations',
      'Hubs',
      'Hub pairs with routes',
      'Travellers in the period',
    ]);
    const values = ['1 412', '118', '64', '1 806', '72 240'];
    values.forEach((value, at) => {
      expect(counts[at]?.nextElementSibling).toHaveTextContent(value);
    });
  });

  it('writes the four read-only groups with their sentences and the two captions', async () => {
    mount(fakeCityInstances());
    await found('City instance · pipeline steps 1 to 4');

    for (const name of ['Area', 'Hubs', 'Routes', 'Travellers and bikes']) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument();
    }
    const area = within(screen.getByRole('region', { name: 'Area' }));
    expect(area.getByText('Geneva · tpg + Donkey Republic')).toBeInTheDocument();
    expect(area.getByText('46.2057, 6.1489')).toBeInTheDocument();
    expect(area.getByText('3.0 km')).toBeInTheDocument();
    expect(
      area.getByText(
        'Public transport timetable (GTFS) and shared-bike stations (GBFS), preloaded for Geneva. Timetable valid 15 Dec 2024 to 13 Dec 2025 · bike stations fetched 10 Nov 2026.',
      ),
    ).toBeInTheDocument();
    const hubs = within(screen.getByRole('region', { name: 'Hubs' }));
    expect(
      hubs.getByText('package units, about 0.69 m on the ground at Geneva: 500 is about 346 m'),
    ).toBeInTheDocument();
    expect(
      hubs.getByText('package units, about 0.69 m on the ground at Geneva: 100 is about 69 m'),
    ).toBeInTheDocument();
    const routes = within(screen.getByRole('region', { name: 'Routes' }));
    expect(routes.getByText('Monday 08:00–09:00')).toBeInTheDocument();
    expect(
      routes.getByText(/Routes planned for Monday 10 March 2025, arrive by 08:30 · provisional\.$/),
    ).toBeInTheDocument();
    const people = within(screen.getByRole('region', { name: 'Travellers and bikes' }));
    expect(people.getByText('10 to 70')).toBeInTheDocument();
    expect(people.getByText('0 to 100 % of docks')).toBeInTheDocument();
    expect(people.getByText('1 to 5 min')).toBeInTheDocument();
    expect(people.getByText('42')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('ends with the closing sentence and "Edit as a new version", and nothing for deleting', async () => {
    mount(fakeCityInstances());
    await found('City instance · pipeline steps 1 to 4');

    expect(
      screen.getByText(
        'A saved instance is never changed: editing it saves a new version, so every pricing version keeps the instance it was run on.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Edit as a new version' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Delete/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /New pricing version/ })).not.toBeInTheDocument();
  });

  it('writes the singular for one pricing version', async () => {
    const menu = () =>
      Promise.resolve([
        {
          id: 'geneva-3km',
          name: 'Geneva 3 km',
          datasetId: 'geneva-2026-11-26',
          versions: [
            {
              id: 'geneva-3km.v1',
              number: 1,
              status: 'sealed' as const,
              state: 'ready',
              pricingVersionCount: 1,
            },
          ],
        },
      ]);
    mount(fakeCityInstances({ menu }));

    expect(
      await found('Ready · saved 12 Nov 2026 · used by 1 pricing version'),
    ).toBeInTheDocument();
  });

  it('adds the package names and "Version numbers are never reused." only in the Advanced view', async () => {
    mount(fakeCityInstances(), true);
    await found('City instance · pipeline steps 1 to 4');

    expect(screen.getByText('Version numbers are never reused.')).toBeInTheDocument();
    for (const names of [
      'gtfs_path · gbfs_path',
      'center_lat · center_lon',
      'radius_m',
      'otp_timestamp',
      'seed',
    ]) {
      expect(screen.getByText(names).tagName).toBe('CODE');
    }
  });

  it('has none of them with Advanced view off', async () => {
    mount(fakeCityInstances(), false);
    await found('City instance · pipeline steps 1 to 4');

    expect(screen.queryByText('Version numbers are never reused.')).not.toBeInTheDocument();
    expect(screen.queryByText('radius_m')).not.toBeInTheDocument();
    expect(document.querySelector('code')).toBeNull();
  });

  it('shows no ready line and no counts for a version that is not ready', async () => {
    const version = (id: string) =>
      Promise.resolve(
        id === sampleVersion.id
          ? {
              ...sampleVersion,
              status: 'draft' as const,
              state: 'draft',
              sealedAt: null,
              counts: null,
              routes: null,
            }
          : null,
      );
    mount(fakeCityInstances({ version }));
    await found('City instance · pipeline steps 1 to 4');

    expect(screen.queryByText(/^Ready/)).not.toBeInTheDocument();
    expect(screen.queryByText('Stops and platforms')).not.toBeInTheDocument();
    expect(screen.queryByText(/^Routes:/)).not.toBeInTheDocument();
  });

  it('says so when the version cannot be read', async () => {
    mount(fakeCityInstances({ version: () => Promise.reject(new Error('offline')) }));

    expect(await found('The city instance could not be read: offline')).toBeInTheDocument();
  });
});

describe('InstanceView · the map', () => {
  it('draws the five layers of the version and fits its study circle', async () => {
    const { map } = mount(fakeCityInstances());
    await found('City instance · pipeline steps 1 to 4');
    act(() => {
      map().emitStyleReady();
    });

    await waitFor(() => {
      expect(map().layers.map((layer) => layer.id)).toEqual([
        'l1-study-circle',
        'l1-hub-pairs',
        'l1-hub-outlines',
        'l1-stops',
        'l1-bike-stations',
      ]);
    });
    const [west, south, east, north] = map().fits.at(-1)?.bounds ?? [];
    expect(west).toBeLessThan(6.1489);
    expect(east).toBeGreaterThan(6.1489);
    expect(south).toBeLessThan(46.2057);
    expect(north).toBeGreaterThan(46.2057);
  });
});

describe('InstanceView · the Routes line', () => {
  it('reads the form with no failure and offers no link', async () => {
    mount(fakeCityInstances());

    expect(await found('Routes: all 3 960 trip-planner queries gave a route.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Show the/ })).not.toBeInTheDocument();
  });

  it('reads the failed form, lists the pairs in a table and draws one on the map', async () => {
    const routeFailures = vi.fn(() => Promise.resolve(failures));
    const version = () => Promise.resolve(failedVersion);
    const { map } = mount(fakeCityInstances({ version, routeFailures }));
    const user = userEvent.setup();
    act(() => {
      map().emitStyleReady();
    });

    expect(
      await found(
        /^Routes: 2 of 48 trip-planner queries gave no route \(4\.2 %\)\. 1 hub pair has no public transport route and is not priced; 1 has no car option\. A technical error is tried 3 times before it counts\./,
      ),
    ).toBeInTheDocument();
    expect(routeFailures).not.toHaveBeenCalled();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Show the 2 hub pairs without a route' }));

    const table = await screen.findByRole('table');
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((cell) => cell.textContent),
    ).toEqual(['From → to', 'Query', 'What happened', 'Effect', 'Show on map']);
    const rows = within(table).getAllByRole('row').slice(1);
    expect(
      rows.map((row) =>
        within(row)
          .getAllByRole('cell')
          .slice(0, 4)
          .map((cell) => cell.textContent),
      ),
    ).toEqual([
      [
        'Hub H1 → Hub H2',
        'Public transport',
        'Trip planner error after 3 tries: timeout',
        'Not in the instance: not priced',
      ],
      ['Hub H2 → Hub H1', 'Car', 'No route found', 'No car option'],
    ]);
    expect(routeFailures).toHaveBeenCalledWith('run-1');
    expect(screen.queryByRole('list', { name: 'Map legend' })).not.toBeInTheDocument();
    expect(map().layers.map((layer) => layer.id)).not.toContain('l1-unrouted-pairs');

    const [first] = within(table).getAllByRole('button', { name: 'Show on map' });
    if (first === undefined) throw new Error('no button');
    await user.click(first);

    expect(screen.getByRole('list', { name: 'Map legend' })).toHaveTextContent(
      'Hub pair without a route',
    );
    await waitFor(() => {
      expect(map().layers.map((layer) => layer.id)).toContain('l1-unrouted-pairs');
    });
    expect(map().layers.find((layer) => layer.id === 'l1-unrouted-pairs')?.paint).toMatchObject({
      'line-color': '#be280b',
    });

    await user.click(within(table).getByRole('button', { name: 'Hide from map' }));

    expect(screen.queryByRole('list', { name: 'Map legend' })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(map().layers.map((layer) => layer.id)).not.toContain('l1-unrouted-pairs');
    });
  });

  it('closes the table with the same link', async () => {
    const version = () => Promise.resolve(failedVersion);
    mount(fakeCityInstances({ version, routeFailures: () => Promise.resolve(failures) }));
    const user = userEvent.setup();
    const link = await screen.findByRole('button', {
      name: 'Show the 2 hub pairs without a route',
    });

    await user.click(link);
    await screen.findByRole('table');
    await user.click(link);

    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('writes the singular for one failed query and says when the failures cannot be read', async () => {
    const version = () =>
      Promise.resolve({ ...sampleVersion, routes: { ...sampleFailedRoutes, queriesFailed: 1 } });
    mount(fakeCityInstances({ version, routeFailures: () => Promise.reject(new Error('x')) }));
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole('button', { name: 'Show the 1 hub pair without a route' }),
    );

    expect(await found('The failed queries could not be read.')).toBeInTheDocument();
  });
});
