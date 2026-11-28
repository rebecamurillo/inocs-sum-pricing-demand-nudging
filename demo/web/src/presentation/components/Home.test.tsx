import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { emptyCityInstances } from '../../application/ports/fake-city-instance-gateway';
import { fakePricing, sampleShowcase } from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import { emptyTrips } from '../../application/ports/fake-trip-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { Showcase } from '../../domain/showcase';
import { GatewaysProvider } from '../hooks/gateways';
import { MapFactoryProvider } from '../map/MapContext';
import { fakeMapFactory, installBrowserStubs } from '../map/fake-map';
import { Home } from './Home';

const showcase: Showcase = sampleShowcase;

function renderHome(answer: Showcase | null | Error | 'pending' = null, basemapExists = false) {
  const { factory, maps } = fakeMapFactory();
  const base = fakePricing([], {}, { showcase: answer === 'pending' ? null : answer }).gateway;
  const pricing =
    answer === 'pending'
      ? { ...base, getShowcase: () => new Promise<never>(() => undefined) }
      : base;
  const requests = vi.spyOn(pricing, 'getShowcase');
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.reject(new Error('Home does not read the status.')) },
    layoutPreferences: { load: () => ({}) as never, save: () => undefined },
    cityDatasets: { list: () => Promise.reject(new Error('no')) },
    basemap: {
      exists: () => Promise.resolve(basemapExists),
      url: (id: string) => `basemap/${id}.pmtiles`,
    },
    cityInstances: emptyCityInstances,
    runs: fakeRunGateway(),
    pricing,
    trips: emptyTrips,
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={factory}>
          <Home />
        </MapFactoryProvider>
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  return { requests, maps };
}

function stubMotion(reduced: boolean) {
  window.matchMedia = (query: string) =>
    ({
      matches: reduced && query.includes('prefers-reduced-motion'),
      media: query,
    }) as MediaQueryList;
  const scroll = vi.fn();
  Element.prototype.scrollIntoView = scroll;
  return scroll;
}

beforeEach(() => {
  window.location.hash = '#/';
});

afterEach(() => {
  cleanup();
  window.location.hash = '';
});

describe('Home · the two sections', () => {
  it('shows the header with the Try it button', () => {
    stubMotion(false);
    renderHome();
    const header = screen.getByRole('banner');
    expect(within(header).getByText('Dynamic pricing')).toBeInTheDocument();
    expect(within(header).getByRole('button', { name: 'Try it' })).toBeInTheDocument();
  });

  it('shows section 1 verbatim with one h1', () => {
    stubMotion(false);
    renderHome();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Price shared bikes by the trip, and fewer people take the car.',
    );
    for (const text of [
      'For cities and public transport operators',
      'A research model from the SUM project sets the bike price of each trip, to nudge travellers from the car to shared bikes and public transport.',
      'The problem',
      'For each trip, people compare time, price and changes. Too often the car wins, and a flat bike price is the same on every trip.',
      'The idea',
      "You say what matters: more riders, the operator's profit, bikes where they are needed. The model chooses a price for each trip, lower where a bike can replace a car. Nobody is forced: travellers still choose.",
      'A familiar lever, a different goal',
      'Plane tickets move with demand to fill the plane. Here the price moves with the trip, to take cars off the street.',
    ]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    expect(document.body).not.toHaveTextContent('[Q-28]');
    expect(document.body).not.toHaveTextContent('[comparison to confirm]');
  });

  it('shows section 2 with the two cards, the limits line and the footer', () => {
    stubMotion(false);
    renderHome();
    expect(screen.getByText('Two ways in. Choose by what you want to do.')).toBeInTheDocument();
    for (const text of [
      '5 minutes · for everyone',
      "Play: take the operator's seat",
      'One mission: get travellers out of their cars without losing revenue. Three choices, three tries, then watch your prices at work over one day.',
      'Coming after the proof of concept',
      'For analysts and researchers',
      'Lab: run the model yourself',
      'Prepare a city instance, set the pricing goals, run the model live for one morning hour, then compare versions and the price of any trip.',
    ]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
    expect(screen.getAllByRole('article')).toHaveLength(2);
    const limits = screen.getByTestId('limits-line');
    expect(limits).toHaveTextContent(
      "A research model by placeholder, Inria INOCS, run on one zone of Geneva with simulated demand. The figure above comes from the model's prices and a simulation of travellers, not from a trial in the street.",
    );
    const footer = screen.getByRole('contentinfo');
    expect(footer).toHaveTextContent(
      'Funded by the European Union under Horizon Europe, project SUM.',
    );
    expect(footer).toHaveTextContent('Pricing model: placeholder, Inria INOCS.');
    expect(footer).not.toHaveTextContent('Run unmodified.');
    expect(screen.queryByText(/Aa/)).not.toBeInTheDocument();
  });
});

describe('Home · the buttons', () => {
  it('has one primary button, "Open the Lab →", which opens #/lab', async () => {
    stubMotion(false);
    renderHome();
    const open = screen.getByRole('button', { name: 'Open the Lab →' });
    expect(open).toHaveAttribute('data-primary', 'true');
    expect(document.querySelectorAll('[data-primary="true"]')).toHaveLength(1);

    await userEvent.setup().click(open);

    expect(window.location.hash).toBe('#/lab');
  });

  it('has a disabled secondary Play button that does nothing', async () => {
    stubMotion(false);
    renderHome();
    const play = screen.getByRole('button', { name: 'Play the game →' });
    expect(play).toHaveAttribute('aria-disabled', 'true');
    expect(play).toHaveAttribute(
      'title',
      'Play is designed and is built after the proof of concept.',
    );
    expect(play).not.toHaveAttribute('data-primary');

    await userEvent.setup().click(play);

    expect(window.location.hash).toBe('#/');
  });

  it('scrolls to section 2 smoothly and leaves the hash alone', async () => {
    const scroll = stubMotion(false);
    renderHome();

    await userEvent.setup().click(screen.getByRole('button', { name: 'Try it' }));

    expect(scroll).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
    expect(scroll.mock.contexts[0]).toBe(screen.getByRole('region', { name: 'Try it' }));
    expect(window.location.hash).toBe('#/');
  });

  it('does not scroll smoothly under reduced motion', async () => {
    const scroll = stubMotion(true);
    renderHome();

    await userEvent.setup().click(screen.getByRole('button', { name: 'Try it' }));

    expect(scroll).toHaveBeenCalledWith({ behavior: 'auto', block: 'start' });
  });
});

describe('Home · the visual', () => {
  it('shows a skeleton while the showcase is pending', () => {
    stubMotion(false);
    const { requests } = renderHome('pending');
    const visual = screen.getByTestId('home-visual');
    expect(within(visual).getByTestId('home-skeleton')).toHaveAttribute('aria-busy', 'true');
    expect(visual).not.toHaveTextContent('No result');
    expect(requests).toHaveBeenCalledTimes(1);
  });

  it('shows the no-showcase text, with no figure and no tag, on a 404', async () => {
    stubMotion(false);
    renderHome(null);
    const visual = screen.getByTestId('home-visual');
    await waitFor(() => {
      expect(visual).toHaveTextContent(
        'No result on this page yet. In the Lab, open the result of a pricing version and choose "Use on the home page".',
      );
    });
    expect(screen.queryByTestId('home-skeleton')).not.toBeInTheDocument();
    expect(visual).not.toHaveTextContent('SIMULATION');
    expect(visual.querySelector('canvas, svg')).toBeNull();
  });

  it('shows the API text when the showcase fails', async () => {
    stubMotion(false);
    renderHome(new Error('down'));
    await waitFor(() => {
      expect(screen.getByTestId('home-visual')).toHaveTextContent(
        "The result could not be loaded: the demonstrator's API did not answer.",
      );
    });
  });

  it('shows the stat tile with the figure, the tag, the source line, the scope and the provisional line', async () => {
    stubMotion(false);
    const { requests } = renderHome(showcase);
    const tile = await screen.findByTestId('home-tile');

    expect(within(tile).getByTestId('home-figure')).toHaveTextContent(/^4$/);
    expect(tile).toHaveTextContent(
      '4 fewer car trips for every 100 simulated travellers, against a flat bike price of 1.00 CHF',
    );
    expect(within(tile).getByText('SIMULATION')).toBeInTheDocument();
    expect(tile).toHaveTextContent(
      'Simulated travellers \u00b7 placeholder rule: half price, half travel time',
    );
    expect(tile).not.toHaveTextContent('(v1)');
    expect(tile).toHaveTextContent(
      'Geneva, 3 km zone, Monday 08:00\u201309:00 \u00b7 Version B of Geneva 3 km v1',
    );
    expect(tile).toHaveTextContent(
      "Provisional: the model's author has not yet validated the simulation's rule or the claims of this page.",
    );
    expect(screen.queryByText("PRICING MODEL'S RESULT")).not.toBeInTheDocument();
    expect(requests).toHaveBeenCalledTimes(1);
  });

  it('writes the older rule on the source line when the rule is stale', async () => {
    stubMotion(false);
    renderHome({ ...showcase, rule: { id: 'balanced_score', version: 1, current: false } });
    const tile = await screen.findByTestId('home-tile');
    expect(tile).toHaveTextContent(
      'Simulated travellers \u00b7 placeholder rule: half price, half travel time \u00b7 older rule (v1)',
    );
  });

  it.each([
    [
      -3,
      '3 more car trips for every 100 simulated travellers, against a flat bike price of 1.00 CHF',
    ],
    [
      1,
      '1 fewer car trip for every 100 simulated travellers, against a flat bike price of 1.00 CHF',
    ],
    [
      0.2,
      '0: as many car trips as with a flat bike price of 1.00 CHF, for every 100 simulated travellers',
    ],
  ])('writes the line for a difference of %s points', async (points, line) => {
    stubMotion(false);
    renderHome({
      ...showcase,
      carShareDifference: { ...showcase.carShareDifference, value: points },
    });
    expect(await screen.findByTestId('home-tile')).toHaveTextContent(line);
  });

  it('writes the legend under the map box', async () => {
    stubMotion(false);
    renderHome(showcase);
    const legend = await screen.findByTestId('home-legend');
    expect(legend).toHaveTextContent(
      "Each line: a trip between two hubs by public transport + shared bike, the only trips the pricing model prices. Colour: mean bike price, low to high \u00b7 width: bike rides. Computed from the model's flows.",
    );
    expect(screen.getByTestId('home-visual')).not.toContainElement(legend);
  });

  it('creates its own non-interactive map, fitted without animation, and draws the layers', async () => {
    stubMotion(false);
    const { maps } = renderHome(showcase);
    await screen.findByTestId('home-tile');
    const map = maps[0];
    if (map === undefined) throw new Error('Home made no map');

    expect(maps).toHaveLength(1);
    expect(map.options.interactive).toBe(false);
    expect(map.options.fadeDuration).toBe(300);
    expect(map.container).toBe(screen.getByTestId('home-map'));

    map.emitStyleReady();
    expect(map.fits).toHaveLength(1);
    expect(map.fits[0]?.animate).toBe(false);
    expect(map.layers.map((layer) => layer.id)).toEqual([
      'home-study-circle',
      'home-hub-outlines',
      'home-pair-lines',
    ]);
  });

  it('turns the fade off under reduced motion', async () => {
    const stubs = installBrowserStubs(true);
    try {
      const { maps } = renderHome(showcase);
      await screen.findByTestId('home-tile');
      expect(maps[0]?.options.fadeDuration).toBe(0);
    } finally {
      stubs.restore();
    }
  });

  it('adds the basemap file to the style when the data set has one, and none otherwise', async () => {
    stubMotion(false);
    const { maps } = renderHome(showcase, true);
    await screen.findByTestId('home-tile');
    const map = maps[0];
    await waitFor(() => {
      expect(map?.styles).toHaveLength(1);
    });
    expect(JSON.stringify(map?.styles[0])).toContain('pmtiles://basemap/geneva-1.pmtiles');
    cleanup();

    const none = renderHome(showcase, false);
    await screen.findByTestId('home-tile');
    expect(none.maps[0]?.styles).toHaveLength(0);
  });

  it('removes the map when Home goes away', async () => {
    stubMotion(false);
    const { maps } = renderHome(showcase);
    await screen.findByTestId('home-tile');
    cleanup();
    expect(maps[0]?.removed).toBe(true);
  });
});
