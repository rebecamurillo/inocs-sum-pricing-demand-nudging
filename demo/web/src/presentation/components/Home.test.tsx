import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { emptyCityInstances } from '../../application/ports/fake-city-instance-gateway';
import { fakePricing } from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import { emptyTrips } from '../../application/ports/fake-trip-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { Showcase } from '../../domain/showcase';
import { GatewaysProvider } from '../hooks/gateways';
import { Home } from './Home';

const showcase: Showcase = {
  pricingVersionId: 'geneva-3km.v1.B',
  periodId: 'monday-08',
  instanceVersionId: 'geneva-3km.v1',
  instanceVersionName: 'Geneva 3 km',
  letter: 'B',
  markedAt: '2026-11-27T10:00:00Z',
};

function renderHome(answer: Showcase | null | Error | 'pending' = null) {
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
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: emptyCityInstances,
    runs: fakeRunGateway(),
    pricing,
    trips: emptyTrips,
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <Home />
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  return { requests };
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

  it('keeps the empty visual, with no text, when a showcase is marked', async () => {
    stubMotion(false);
    const { requests } = renderHome(showcase);
    await waitFor(() => {
      expect(screen.queryByTestId('home-skeleton')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('home-visual')).toHaveTextContent('');
    expect(requests).toHaveBeenCalledTimes(1);
  });
});
