import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { fakeCityInstances } from '../../application/ports/fake-city-instance-gateway';
import { fakePricingGateway } from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import { fakeTrips, type FakeTrips } from '../../application/ports/fake-trip-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { LabRoute } from '../../domain/route';
import { finishedVersionChoices, type VersionChoice } from '../../domain/traveller';
import type { PricingVersion } from '../../domain/pricing-version';
import { GatewaysProvider } from '../hooks/gateways';
import { fakeMapFactory, installBrowserStubs } from '../map/fake-map';
import { MapFactoryProvider, MapProvider } from '../map/MapContext';
import { MapPane } from '../map/MapPane';
import { TravellerView } from './TravellerView';

const period = [{ id: 'monday-08', key: 'mon-08', label: 'Monday 08:00–09:00' }];
const sealed = (instanceVersionId: string, letter: string, name: string): PricingVersion =>
  ({
    id: `${instanceVersionId}.${letter}`,
    instanceVersionId,
    letter,
    name,
    state: 'result',
    periods: period,
  }) as unknown as PricingVersion;

const menu = [
  {
    id: 'geneva-3km',
    name: 'Geneva 3 km',
    datasetId: 'd',
    versions: [
      {
        id: 'geneva-3km.v1',
        number: 1,
        status: 'sealed' as const,
        state: 'ready',
        pricingVersionCount: 3,
        pricingVersionLetters: ['A', 'B', 'C'],
      },
    ],
  },
  {
    id: 'geneva-2km',
    name: 'Geneva 2 km',
    datasetId: 'd',
    versions: [
      {
        id: 'geneva-2km.v1',
        number: 1,
        status: 'sealed' as const,
        state: 'ready',
        pricingVersionCount: 1,
        pricingVersionLetters: ['A'],
      },
    ],
  },
];
const choices = finishedVersionChoices(menu, {
  'geneva-3km.v1': [
    sealed('geneva-3km.v1', 'A', 'Flat'),
    sealed('geneva-3km.v1', 'B', 'Incentive'),
    sealed('geneva-3km.v1', 'C', 'Steeper'),
  ],
  'geneva-2km.v1': [sealed('geneva-2km.v1', 'A', 'Small')],
});

const PLAINPALAIS = { lat: 46.199, lon: 6.14 };
const CORNAVIN = { lat: 46.2102, lon: 6.1424 };
const NOWHERE = { lat: 46.25, lon: 6.3 };

function Harness({
  initial,
  onRoute,
}: {
  initial: VersionChoice;
  onRoute: (route: LabRoute) => void;
}) {
  const [route, setRoute] = useState<{ id: string; period: string | null }>({
    id: initial.id,
    period: null,
  });
  const choice = choices.find((item) => item.id === route.id) ?? initial;
  return (
    <TravellerView
      choices={choices}
      choice={choice}
      period={route.period}
      onNavigate={(next) => {
        onRoute(next);
        if (next.kind !== 'traveller') return;
        const target = choices.find(
          (item) => item.instanceId === next.instance.instanceId && item.letter === next.letter,
        );
        if (target !== undefined) setRoute({ id: target.id, period: next.period });
      }}
    />
  );
}

let stubs: ReturnType<typeof installBrowserStubs>;
beforeEach(() => {
  stubs = installBrowserStubs(false);
});
afterEach(() => {
  cleanup();
  stubs.restore();
});

function mount(initialLetter = 'B') {
  const trips: FakeTrips = fakeTrips();
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.reject(new Error('not called')) },
    layoutPreferences: { load: () => ({}) as never, save: () => undefined },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: fakeCityInstances(),
    runs: fakeRunGateway(),
    pricing: fakePricingGateway(),
    trips: trips.gateway,
  };
  const { factory, maps } = fakeMapFactory();
  const routes: LabRoute[] = [];
  const initial = choices.find((item) => item.letter === initialLetter) ?? choices[0];
  if (initial === undefined) throw new Error('no choice');
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={factory}>
          <MapProvider>
            <MapPane shown datasetId={null} />
            <Harness
              initial={initial}
              onRoute={(route) => {
                routes.push(route);
              }}
            />
          </MapProvider>
        </MapFactoryProvider>
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  const map = maps[0];
  if (map === undefined) throw new Error('no map');
  act(() => {
    map.emitStyleReady();
  });
  return { map, trips, routes, user: userEvent.setup() };
}

const pointA = () => screen.getByRole('combobox', { name: 'Point A' });
const pointB = () => screen.getByRole('combobox', { name: 'Point B' });
const card = (label: string) => screen.getByText(label, { selector: 'span' }).closest('li');

describe('TravellerView · the three rows', () => {
  it('shows the brief, the three numbered rows and the version list with its sentence', async () => {
    mount();

    expect(screen.getByText('Traveller view')).toBeInTheDocument();
    expect(
      screen.getByText(
        'What a traveller is offered for one trip: the options, how long they take and what they cost. The bike price comes from the pricing version chosen first.',
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Pricing version',
      'Trip',
      'Time slot',
    ]);
    const select = screen.getByRole('combobox', { name: 'Pricing version' });
    expect(
      within(select)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual([
      'Geneva 3 km v1 · Version A · Flat',
      'Geneva 3 km v1 · Version B · Incentive',
      'Geneva 3 km v1 · Version C · Steeper',
      'Geneva 2 km v1 · Version A · Small',
    ]);
    expect(select).toHaveValue('geneva-3km.v1.B');
    expect(
      await screen.findByText(
        'Gives the city instance (its 64 hubs and 118 bike stations, on the map) and the time slots that have prices.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Click the map or type a stop or station name.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Swap A and B' })).toBeInTheDocument();
  });

  it('offers the day Monday and 17 hours, only the priced one selectable', () => {
    mount();

    expect(
      within(screen.getByRole('combobox', { name: 'Day' })).getAllByRole('option'),
    ).toHaveLength(1);
    const options = within(screen.getByRole('combobox', { name: 'Period' })).getAllByRole('option');
    expect(options).toHaveLength(17);
    expect(options[0]).toHaveTextContent('06:00–07:00 · no prices in this version');
    expect(options[0]).toBeDisabled();
    expect(options[2]).toHaveTextContent(/^08:00–09:00$/);
    expect(options[2]).toBeEnabled();
    expect(screen.getByText('NEXT VERSION')).toBeInTheDocument();
    expect(screen.getByText('every hour the version has priced.')).toBeInTheDocument();
  });

  it('declares the map layers of the instance version and a click handler', async () => {
    const { map } = mount();

    await waitFor(() => {
      expect(map.layers.map((layer) => layer.id)).toEqual([
        'l5-study-circle',
        'l5-hub-outlines',
        'l5-bike-stations',
      ]);
    });
    expect(map.clickListenerCount).toBe(1);
  });
});

describe('TravellerView · the trip', () => {
  it('lists typed names after 250 ms, and a clicked line sets the point and fills the field', async () => {
    const { trips, user } = mount();

    await user.type(pointA(), 'plain');
    expect(trips.placeCalls).toEqual([]);
    const list = await screen.findByRole('listbox');
    expect(trips.placeCalls).toEqual([{ instanceVersionId: 'geneva-3km.v1', text: 'plain' }]);
    expect(
      within(list)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual(['Plainpalais · stop · hub H4', 'Plainpalais · bike station · hub H4']);

    const [first] = within(list).getAllByRole('option');
    if (first === undefined) throw new Error('no line');
    await user.click(first);

    await waitFor(() => {
      expect(pointA()).toHaveValue('hub H4 · Plainpalais');
    });
    expect(trips.quoteCalls.at(-1)).toMatchObject({
      pricingVersionId: 'geneva-3km.v1.B',
      from: PLAINPALAIS,
      to: null,
    });
  });

  it('chooses a line with the arrow keys and Enter and prices the trip under the scope line', async () => {
    const { user } = mount();

    await user.type(pointA(), 'plain');
    await screen.findByRole('listbox');
    await user.keyboard('{ArrowDown}{Enter}');
    await user.type(pointB(), 'corn');
    await screen.findByRole('listbox');
    await user.keyboard('{ArrowDown}{Enter}');

    await waitFor(() => {
      expect(pointB()).toHaveValue('hub H1 · Cornavin');
    });
    expect(pointA()).toHaveValue('hub H4 · Plainpalais');
    expect(await screen.findByText('Monday 08:00–09:00 · Version B')).toBeInTheDocument();
    const cards = screen.getAllByRole('listitem').filter((item) => item.dataset.mode !== undefined);
    expect(cards.map((item) => item.dataset.mode)).toEqual(['car', 'pt_bike', 'pt_only']);
    expect(card('Car')).toHaveTextContent('🚗');
    expect(card('Car')).toHaveTextContent('4.50 CHF');
    expect(card('Public transport + shared bike')).toHaveTextContent('3.00 CHF');
    expect(card('Public transport')).toHaveTextContent('2.00 CHF');
  });

  it('sets the focused field on a map click, else A when empty, else B', async () => {
    const { map, user } = mount();

    act(() => {
      map.click(PLAINPALAIS);
    });
    await waitFor(() => {
      expect(pointA()).toHaveValue('hub H4 · Plainpalais');
    });
    act(() => {
      map.click(CORNAVIN);
    });
    await waitFor(() => {
      expect(pointB()).toHaveValue('hub H1 · Cornavin');
    });

    await user.click(pointA());
    act(() => {
      map.click(CORNAVIN);
    });
    await waitFor(() => {
      expect(pointA()).toHaveValue('hub H1 · Cornavin');
    });
  });

  it('keeps the focused field when a press on the map moves the focus to its canvas', async () => {
    const { map, user } = mount();
    act(() => {
      map.click(PLAINPALAIS);
    });
    act(() => {
      map.click(CORNAVIN);
    });
    await waitFor(() => {
      expect(pointB()).toHaveValue('hub H1 · Cornavin');
    });
    const canvas = document.createElement('canvas');
    canvas.tabIndex = 0;
    document.body.append(canvas);

    await user.click(pointA());
    act(() => {
      canvas.focus();
    });
    act(() => {
      map.click(CORNAVIN);
    });
    await waitFor(() => {
      expect(pointA()).toHaveValue('hub H1 · Cornavin');
    });
    // The kept field is used once: the next click, with no field focused, sets B.
    act(() => {
      map.click(PLAINPALAIS);
    });
    await waitFor(() => {
      expect(pointB()).toHaveValue('hub H4 · Plainpalais');
    });
    canvas.remove();
  });

  it('swaps the two points', async () => {
    const { map, user } = mount();
    act(() => {
      map.click(PLAINPALAIS);
    });
    act(() => {
      map.click(CORNAVIN);
    });
    await waitFor(() => {
      expect(pointB()).toHaveValue('hub H1 · Cornavin');
    });

    await user.click(screen.getByRole('button', { name: 'Swap A and B' }));

    await waitFor(() => {
      expect(pointA()).toHaveValue('hub H1 · Cornavin');
    });
    expect(pointB()).toHaveValue('hub H4 · Plainpalais');
  });

  it('leaves the field of a point with no hub empty and says how far the nearest hub is', async () => {
    const { map } = mount();

    act(() => {
      map.click(NOWHERE);
    });

    expect(
      await screen.findByText(
        'No hub here: the nearest hub, H7, is 413 m away. Click closer to a stop or a bike station.',
      ),
    ).toBeInTheDocument();
    expect(pointA()).toHaveValue('');
    expect(screen.queryByText(/CHF/)).not.toBeInTheDocument();
  });
});

describe('TravellerView · switching the version', () => {
  async function priced() {
    const rig = mount();
    act(() => {
      rig.map.click(PLAINPALAIS);
    });
    act(() => {
      rig.map.click(CORNAVIN);
    });
    await screen.findByText('Monday 08:00–09:00 · Version B');
    return rig;
  }

  it('pushes the route, quotes the points again and strikes the previous price through', async () => {
    const { user, routes, trips } = await priced();
    expect(document.querySelector('del')).toBeNull();

    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Pricing version' }),
      'geneva-3km.v1.C',
    );

    expect(routes.at(-1)).toEqual({
      kind: 'traveller',
      instance: { instanceId: 'geneva-3km', version: 1 },
      letter: 'C',
      period: null,
    });
    expect(await screen.findByText('Monday 08:00–09:00 · Version C')).toBeInTheDocument();
    await waitFor(() => {
      expect(card('Public transport + shared bike')?.querySelector('del')).toHaveTextContent(
        '3.00 CHF',
      );
    });
    expect(card('Public transport + shared bike')).toHaveTextContent('3.50 CHF');
    expect(trips.quoteCalls.at(-1)).toMatchObject({
      pricingVersionId: 'geneva-3km.v1.C',
      from: PLAINPALAIS,
      to: CORNAVIN,
    });
  });

  it('strikes nothing through across instance versions', async () => {
    const { user } = await priced();

    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Pricing version' }),
      'geneva-2km.v1.A',
    );

    expect(await screen.findByText('Monday 08:00–09:00 · Version A')).toBeInTheDocument();
    expect(document.querySelector('del')).toBeNull();
  });
});
