import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { fakeCityInstances } from '../../application/ports/fake-city-instance-gateway';
import { fakePricingGateway } from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import {
  fakeTrips,
  sampleOptions,
  type FakeTrips,
} from '../../application/ports/fake-trip-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { MapHub } from '../../domain/map';
import type { LabRoute } from '../../domain/route';
import { finishedVersionChoices, type TripQuote, type VersionChoice } from '../../domain/traveller';
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

function mount(
  initialLetter = 'B',
  answer: Partial<TripQuote> | null = null,
  hubs: MapHub[] | null = null,
) {
  const trips: FakeTrips = fakeTrips();
  trips.answer(answer);
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.reject(new Error('not called')) },
    layoutPreferences: { load: () => ({}) as never, save: () => undefined },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances:
      hubs === null
        ? fakeCityInstances()
        : {
            ...fakeCityInstances(),
            hubs: () => Promise.resolve(hubs.map((hub) => ({ ...hub, label: `Hub ${hub.id}` }))),
          },
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

const fakeTripsOptions = () => sampleOptions('geneva-3km.v1.B');
const pointA = () => screen.getByRole('combobox', { name: 'Point A' });
const pointB = () => screen.getByRole('combobox', { name: 'Point B' });
const present = <T extends HTMLElement>(element: T | null): T => {
  if (element === null) throw new Error('element not found');
  return element;
};
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

describe('TravellerView · the options of a trip', () => {
  function pricedWith(answer: Partial<TripQuote> | null = null, a = PLAINPALAIS, b = CORNAVIN) {
    const rig = mount('B', answer);
    act(() => {
      rig.map.click(a);
    });
    act(() => {
      rig.map.click(b);
    });
    return rig;
  }

  it('heads the cards with both hubs and their names beside the scope line', async () => {
    pricedWith();

    expect(
      await screen.findByRole('heading', {
        name: 'Priced between hub H4 (Plainpalais) and hub H1 (Cornavin)',
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('Monday 08:00–09:00 · Version B')).toBeInTheDocument();
  });

  it('shows the most taken option of each card with its duration line and make-up', async () => {
    pricedWith();
    await screen.findByText('Monday 08:00–09:00 · Version B');

    const bike = card('Public transport + shared bike');
    expect(bike).toHaveTextContent('3.00 CHF');
    expect(bike).toHaveTextContent('18 min · 1 transfer');
    expect(bike).toHaveTextContent('Fare 2.00 + bike ride 1.00');
    expect(bike).toHaveTextContent('SET BY THE PRICING MODEL');
    expect(bike?.querySelector('strong')).toHaveTextContent('1.00');
    expect(bike?.querySelectorAll('div[aria-hidden="true"] > span')).toHaveLength(3);
    expect(card('Public transport')).toHaveTextContent('25 min · 2 transfers');
    expect(card('Public transport')).toHaveTextContent('Fare 2.00');
    expect(card('Public transport')).not.toHaveTextContent('SET BY THE PRICING MODEL');
    expect(card('Car')).toHaveTextContent('9 min · 0 transfers');
    expect(card('Car')).toHaveTextContent('Car cost 1.70 + parking fee 2.80');
    expect(screen.queryByText('Shared bike')).not.toBeInTheDocument();
  });

  it('lists the other bike options on a click, the highest flow first', async () => {
    const { user } = pricedWith();
    await screen.findByText('Monday 08:00–09:00 · Version B');
    expect(screen.queryByText('Tram 15 → Rive · bike Rive → Cornavin')).not.toBeInTheDocument();

    const button = screen.getByRole('button', { name: '+ 2 other bike options offered' });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    await user.click(button);

    expect(button).toHaveAttribute('aria-expanded', 'true');
    // The leg list of the selected card is a list of its own; this one is the button's.
    const lines = within(
      present(document.getElementById(button.getAttribute('aria-controls') ?? '')),
    )
      .getAllByRole('listitem')
      .map((item) => item.textContent);
    expect(lines).toEqual([
      'bike Plainpalais → Bel-Air · Tram 12 → Rive · bike Rive → Cornavin25 min9.99 CHF',
      'Tram 15 → Rive · bike Rive → Cornavin22 min4.20 CHF',
    ]);
  });

  it('closes the list of the other bike options when the trip changes', async () => {
    const { user, map } = pricedWith();
    await screen.findByText('Monday 08:00–09:00 · Version B');
    await user.click(screen.getByRole('button', { name: '+ 2 other bike options offered' }));
    expect(screen.getByText('Tram 15 → Rive · bike Rive → Cornavin')).toBeInTheDocument();

    act(() => {
      map.click({ lat: CORNAVIN.lat + 0.001, lon: CORNAVIN.lon });
    });

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: '+ 2 other bike options offered' }),
      ).toHaveAttribute('aria-expanded', 'false');
    });
    expect(screen.queryByText('Tram 15 → Rive · bike Rive → Cornavin')).not.toBeInTheDocument();
  });

  it('shows no button when the model offers no other bike option', async () => {
    pricedWith({
      options: fakeTripsOptions().filter((option) => option.mode !== 'pt_bike' || option.mostTaken),
    });
    await screen.findByText('Monday 08:00–09:00 · Version B');

    expect(screen.queryByRole('button', { name: /other bike options/ })).not.toBeInTheDocument();
  });

  it('writes the make-up of a bike option with two bike legs', async () => {
    pricedWith({
      options: fakeTripsOptions().map((option) =>
        option.mode === 'pt_bike' && option.mostTaken
          ? { ...option, bikeLegs: 2, bikePrice: 0.9 }
          : option,
      ),
    });
    await screen.findByText('Monday 08:00–09:00 · Version B');

    expect(card('Public transport + shared bike')).toHaveTextContent(
      'Fare 2.00 + 2 bike rides × 0.90',
    );
  });

  it('puts the three notes under the cards, in order, and nothing on recommendation', async () => {
    pricedWith();
    await screen.findByText('Monday 08:00–09:00 · Version B');

    const notes = [
      "The bike price is the pricing model's price for this option, per bike ride, added to the public transport fare. Durations and legs: trip planner, between the two hubs.",
      'The pricing model prices a shared bike only together with a public transport trip: a trip by shared bike alone has no option here.',
      'Durations and legs are those of the hub pair: the walk from your point to the hub is not included.',
    ].map((text) => screen.getByText(text));
    const list = screen.getAllByRole('list').find((item) => item.className.includes('cards'));
    expect(list?.compareDocumentPosition(notes[0] as Node)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    notes.slice(1).forEach((note, at) => {
      expect(notes[at]?.compareDocumentPosition(note)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    });
    expect(document.body.textContent).not.toMatch(/recommend/i);
  });

  it('puts a message in place of the bike card with no bike option, the other cards staying', async () => {
    pricedWith({
      status: 'no_bike_option',
      options: fakeTripsOptions().filter((option) => option.mode !== 'pt_bike'),
    });

    expect(
      await screen.findByText(
        'No bike option offered: the pricing model offers none on this hub pair in Version B.',
      ),
    ).toBeInTheDocument();
    const cards = screen.getAllByRole('listitem').filter((item) => item.dataset.mode !== undefined);
    expect(cards.map((item) => item.dataset.mode)).toEqual(['car', 'pt_bike', 'pt_only']);
    expect(card('Car')).toHaveTextContent('4.50 CHF');
  });

  it('puts a message in place of the car card with no car route', async () => {
    pricedWith({
      noCarOption: true,
      options: fakeTripsOptions().filter((option) => option.mode !== 'car'),
    });

    expect(
      await screen.findByText(
        "No car route: the trip planner's car query failed for this hub pair when the instance was built.",
      ),
    ).toBeInTheDocument();
    const cards = screen.getAllByRole('listitem').filter((item) => item.dataset.mode !== undefined);
    expect(cards.map((item) => item.dataset.mode)).toEqual(['car', 'pt_bike', 'pt_only']);
  });
});

describe('TravellerView · the no-price messages', () => {
  const none = (status: TripQuote['status'], patch: Partial<TripQuote> = {}) =>
    ({ status, options: [], noCarOption: null, ...patch }) satisfies Partial<TripQuote>;

  async function expectOnly(answer: Partial<TripQuote>, message: string) {
    const rig = mount('B', answer);
    act(() => {
      rig.map.click(PLAINPALAIS);
    });
    act(() => {
      rig.map.click(CORNAVIN);
    });
    const box = await screen.findByRole('status');
    expect(box).toHaveTextContent(message);
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument();
    expect(screen.queryByTestId('card-car')).not.toBeInTheDocument();
    expect(screen.queryByText(/Durations and legs/)).not.toBeInTheDocument();
  }

  it('says why two points in one hub have no price', async () => {
    const rig = mount();
    act(() => {
      rig.map.click(PLAINPALAIS);
    });
    act(() => {
      rig.map.click(PLAINPALAIS);
    });
    expect(await screen.findByRole('status')).toHaveTextContent(
      'No model price for this trip: both points are in hub H4. The model prices trips between hubs.',
    );
    expect(screen.queryByTestId('card-car')).not.toBeInTheDocument();
  });

  it('says why a pair under the minimum distance has no price', async () => {
    await expectOnly(
      none('under_minimum_distance', { minTripDistanceM: 500 }),
      "No model price: hubs H4 and H1 are closer than this instance's minimum trip distance (500 m).",
    );
  });

  it('says why a pair removed by the check has no price', async () => {
    await expectOnly(
      none('removed_by_quality_check'),
      "No model price: the routes of H4 → H1 were removed when the instance's routes were checked.",
    );
  });

  it('says why a pair with no route has no price', async () => {
    await expectOnly(
      none('no_route'),
      'No model price: the trip planner found no public transport route for H4 → H1 when the instance was built.',
    );
  });

  it('names each point outside the zone, A first, with the radius and the instance version', async () => {
    await expectOnly(
      none('outside_zone', {
        fromPoint: {
          status: 'outside_zone',
          hubId: null,
          nearestStopName: null,
          nearestHubId: null,
          distanceFromOutlineM: null,
        },
        toPoint: {
          status: 'outside_zone',
          hubId: null,
          nearestStopName: null,
          nearestHubId: null,
          distanceFromOutlineM: null,
        },
      }),
      'Point A is outside the 3 km zone of Geneva 3 km v1.Point B is outside the 3 km zone of Geneva 3 km v1.',
    );
  });

  it('shows no message for one point', async () => {
    const { map } = mount();
    act(() => {
      map.click(PLAINPALAIS);
    });
    await waitFor(() => {
      expect(pointA()).toHaveValue('hub H4 · Plainpalais');
    });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

describe('TravellerView · the route of the selected option', () => {
  const OUTLINE: [number, number][] = [
    [6.13, 46.19],
    [6.15, 46.19],
    [6.15, 46.21],
    [6.13, 46.19],
  ];
  const hubs: MapHub[] = [
    { id: 'H4', lat: 46.199, lon: 6.14, outline: OUTLINE },
    { id: 'H1', lat: 46.2102, lon: 6.1424, outline: OUTLINE },
    { id: 'H9', lat: 46.22, lon: 6.16, outline: OUTLINE },
  ];
  function priced(answer: Partial<TripQuote> | null = null, a = PLAINPALAIS, b = CORNAVIN) {
    const rig = mount('B', answer, hubs);
    act(() => {
      rig.map.click(a);
    });
    act(() => {
      rig.map.click(b);
    });
    return rig;
  }
  const toggle = (label: string) =>
    present(within(present(card(label))).getAllByRole('button')[0] ?? null);
  const legsOf = (label: string) =>
    within(present(card(label)))
      .queryAllByRole('listitem')
      .filter((item) => item.closest('ol') !== null)
      .map((item) => item.textContent);
  const features = (map: ReturnType<typeof mount>['map'], id: string) => {
    const source = map.sources.get(id);
    if (source?.type !== 'geojson') return [];
    return source.data.features;
  };
  const BIKE_CARD = 'Public transport + shared bike';

  it('presses the PT + bike card first and lists its legs, the others show none', async () => {
    priced();
    await screen.findByText('Monday 08:00–09:00 · Version B');

    expect(toggle(BIKE_CARD)).toHaveAttribute('aria-pressed', 'true');
    expect(toggle('Public transport')).toHaveAttribute('aria-pressed', 'false');
    expect(toggle('Car')).toHaveAttribute('aria-pressed', 'false');
    expect(legsOf(BIKE_CARD)).toEqual([
      'Walk · 2 min',
      'Tram 12 · Plainpalais → Rive · 12 min',
      'Shared bike · Rive → Cornavin · 4 min',
    ]);
    expect(legsOf('Public transport')).toEqual([]);
    expect(legsOf('Car')).toEqual([]);
  });

  it('presses the PT card first when the quote has no bike option', async () => {
    priced({
      status: 'no_bike_option',
      options: sampleOptions('geneva-3km.v1.B').filter((option) => option.mode !== 'pt_bike'),
    });
    await screen.findByText('Monday 08:00–09:00 · Version B');

    expect(toggle('Public transport')).toHaveAttribute('aria-pressed', 'true');
    expect(legsOf('Public transport')).toEqual(['Tram 12 · Plainpalais → Cornavin · 25 min']);
  });

  it('moves the selection and the leg list on a click, and on Enter and Space', async () => {
    const { user } = priced();
    await screen.findByText('Monday 08:00–09:00 · Version B');

    await user.click(toggle('Car'));
    expect(toggle('Car')).toHaveAttribute('aria-pressed', 'true');
    expect(toggle(BIKE_CARD)).toHaveAttribute('aria-pressed', 'false');
    expect(legsOf('Car')).toEqual(['Car · 9 min']);
    expect(legsOf(BIKE_CARD)).toEqual([]);

    toggle('Public transport').focus();
    await user.keyboard('{Enter}');
    expect(toggle('Public transport')).toHaveAttribute('aria-pressed', 'true');
    expect(toggle('Car')).toHaveAttribute('aria-pressed', 'false');

    toggle(BIKE_CARD).focus();
    await user.keyboard(' ');
    expect(toggle(BIKE_CARD)).toHaveAttribute('aria-pressed', 'true');
    expect(toggle('Public transport')).toHaveAttribute('aria-pressed', 'false');
  });

  it('presses the default card again when a new trip shows', async () => {
    const { user, map } = priced();
    await screen.findByText('Monday 08:00–09:00 · Version B');
    await user.click(toggle('Car'));

    act(() => {
      map.click({ lat: 46.2105, lon: 6.1424 });
    });
    await waitFor(() => {
      expect(toggle(BIKE_CARD)).toHaveAttribute('aria-pressed', 'true');
    });
  });

  it('asks for the route options of the hub pair and period', async () => {
    const { trips } = priced();
    await screen.findByText('Monday 08:00–09:00 · Version B');

    await waitFor(() => {
      expect(trips.routeCalls).toEqual([
        {
          instanceVersionId: 'geneva-3km.v1',
          period: 'mon-08',
          originHubId: 'H4',
          destinationHubId: 'H1',
        },
      ]);
    });
  });

  it('asks the route options of the shown quote’s instance version while a switched one loads', async () => {
    const { trips, user } = priced();
    await waitFor(() => {
      expect(trips.routeCalls).toHaveLength(1);
    });
    const quote = trips.gateway.quote.bind(trips.gateway);
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    trips.gateway.quote = async (...args) => {
      await held;
      return quote(...args);
    };

    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Pricing version' }),
      'geneva-2km.v1.A',
    );
    await act(() => Promise.resolve());
    expect(trips.routeCalls.map((call) => call.instanceVersionId)).toEqual(['geneva-3km.v1']);

    act(() => {
      release();
    });
    await waitFor(() => {
      expect(trips.routeCalls.at(-1)?.instanceVersionId).toBe('geneva-2km.v1');
    });
  });

  it('draws the selected option leg by leg in the leg-kind colours and styles', async () => {
    const { map, user } = priced();
    await waitFor(() => {
      expect(map.layers.map((layer) => layer.id)).toContain('l5-route-bike');
    });
    const paint = (id: string) => map.layers.find((layer) => layer.id === id)?.paint;
    expect(map.layers.map((layer) => layer.id).filter((id) => id.startsWith('l5-route'))).toEqual([
      'l5-route-pt',
      'l5-route-bike',
      'l5-route-walk',
    ]);
    expect(paint('l5-route-pt')).toEqual({ 'line-color': '#2a78d6', 'line-width': 3 });
    expect(paint('l5-route-bike')).toMatchObject({
      'line-color': '#008300',
      'line-dasharray': [2, 1],
    });
    expect(paint('l5-route-walk')).toMatchObject({
      'line-color': '#5a6459',
      'line-dasharray': [1, 1.5],
    });
    expect(features(map, 'l5-route-pt').map((f) => f.properties)).toEqual([
      { lineKind: 'straight_line' },
    ]);

    await user.click(toggle('Car'));
    await waitFor(() => {
      expect(map.layers.map((layer) => layer.id)).toContain('l5-route-car');
    });
    expect(map.layers.map((layer) => layer.id)).not.toContain('l5-route-pt');
    expect(paint('l5-route-car')).toEqual({ 'line-color': '#eb6834', 'line-width': 3 });
  });

  it('highlights the outlines of the two matched hubs only', async () => {
    const { map } = priced();
    await waitFor(() => {
      expect(map.layers.map((layer) => layer.id)).toContain('l5-matched-outlines');
    });

    expect(features(map, 'l5-matched-outlines').map((f) => f.properties.id)).toEqual(['H4', 'H1']);
    expect(features(map, 'l5-hub-outlines')).toHaveLength(3);
  });

  it('stands the pins A and B at the points, also for a point with no hub, and clears them', async () => {
    const { map, user } = mount('B', null, hubs);
    act(() => {
      map.click(NOWHERE);
    });
    await waitFor(() => {
      expect(map.markers.filter((m) => !m.removed)).toHaveLength(1);
    });
    act(() => {
      map.click(CORNAVIN);
    });
    await waitFor(() => {
      expect(map.markers.filter((m) => !m.removed)).toHaveLength(2);
    });

    const live = map.markers.filter((m) => !m.removed);
    expect(
      live.map((m) => [m.options.label, m.options.text, m.options.colour, m.options.draggable]),
    ).toEqual([
      ['Point A', 'A', '#2e2d29', false],
      ['Point B', 'B', '#004494', false],
    ]);
    expect(live.map((m) => m.position)).toEqual([NOWHERE, CORNAVIN]);

    await user.click(screen.getByRole('button', { name: 'Swap A and B' }));
    await waitFor(() => {
      expect(map.markers.filter((m) => !m.removed).map((m) => m.position)).toEqual([
        CORNAVIN,
        NOWHERE,
      ]);
    });
  });

  it('lists one legend key per leg kind of the option and the tram and train sentence', async () => {
    const { user } = priced();
    const legend = await screen.findByRole('list', { name: 'Map legend' });
    await waitFor(() => {
      expect(
        within(legend)
          .getAllByRole('listitem')
          .map((item) => item.textContent),
      ).toEqual([
        'Public transport',
        'Shared-bike leg',
        'Walking leg',
        'Tram and train legs: straight lines between stops.',
      ]);
    });

    await user.click(toggle('Car'));
    await waitFor(() => {
      expect(
        within(legend)
          .getAllByRole('listitem')
          .map((item) => item.textContent),
      ).toEqual(['Car', 'Tram and train legs: straight lines between stops.']);
    });
  });

  it('reads the tram, train and bus sentence when the data set has no bus shapes', async () => {
    const rig = mount('B', null, hubs);
    rig.trips.busShapes(false);
    act(() => {
      rig.map.click(PLAINPALAIS);
    });
    act(() => {
      rig.map.click(CORNAVIN);
    });

    expect(
      await screen.findByText('Tram, train and bus legs: straight lines between stops.'),
    ).toBeInTheDocument();
  });

  it('shows no route legend before a route is drawn', async () => {
    mount('B', null, hubs);
    await waitFor(() => {
      expect(screen.queryByRole('list', { name: 'Map legend' })).not.toBeInTheDocument();
    });
  });

  it('fits the route and the pins with 40 px padding, animated', async () => {
    const { map } = priced();
    await waitFor(() => {
      expect(map.fits.at(-1)?.padding).toBe(40);
    });

    const last = map.fits.at(-1);
    expect(last?.animate).toBe(true);
    // West, south, east, north of the stored geometry and both pins.
    expect(last?.bounds).toEqual([6.14, 46.199, 6.15, 46.2102]);
  });

  it('jumps to the route under reduced motion', async () => {
    stubs.restore();
    stubs = installBrowserStubs(true);
    const { map } = priced();
    await waitFor(() => {
      expect(map.fits.at(-1)?.padding).toBe(40);
    });

    expect(map.fits.every((move) => !move.animate)).toBe(true);
    expect(map.calls.some((call) => /easeTo|flyTo/.test(call))).toBe(false);
  });
});
