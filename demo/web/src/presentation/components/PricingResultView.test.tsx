import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { fakeCityInstances, sampleMenu } from '../../application/ports/fake-city-instance-gateway';
import {
  fakePricing,
  samplePricingResult,
  sampleSealedPricing,
} from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { PricingResult } from '../../domain/pricing-result';
import type { LabRoute } from '../../domain/route';
import { GatewaysProvider } from '../hooks/gateways';
import { MapProvider } from '../map/MapContext';
import { PricingResultView } from './PricingResultView';

function nth<T>(list: readonly T[], at: number): T {
  const found = list[at];
  if (found === undefined) throw new Error(`No element at ${String(at)}.`);
  return found;
}

const version = sampleSealedPricing({ name: 'Incentive', state: 'result' });

function mount(options: { result?: PricingResult; gateway?: Gateways['pricing'] } = {}) {
  const fake = fakePricing([version], {
    'geneva-3km.v1.A': options.result ?? samplePricingResult(),
  });
  const onNavigate = vi.fn<(route: LabRoute) => void>();
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.reject(new Error('not called')) },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: fakeCityInstances({ menu: () => Promise.resolve(sampleMenu) }),
    runs: fakeRunGateway(),
    pricing: options.gateway ?? fake.gateway,
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <MapProvider>
          <PricingResultView
            instanceVersionId="geneva-3km.v1"
            instanceId="geneva-3km"
            number={1}
            letter="A"
            advancedView={false}
            onNavigate={onNavigate}
          />
        </MapProvider>
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  return { client, onNavigate, fake };
}

const withUnserved = (unserved: number): PricingResult => {
  const base = samplePricingResult();
  return {
    ...base,
    simulations: {
      modelPrices: { ...base.simulations.modelPrices, unserved },
      flat: base.simulations.flat,
    },
  };
};

describe('PricingResultView', () => {
  it('reads top to bottom: brief, scope, simulation group, the model group, the goal tiles', async () => {
    mount();

    expect(await screen.findByText('Result · pipeline step 6')).toBeVisible();
    expect(
      screen.getByText(/^Version A · Incentive · Geneva 3 km v1 · Monday 08:00–09:00$/),
    ).toBeVisible();
    const simulation = screen.getByTestId('simulation-group');
    const model = screen.getByTestId('model-group');
    const goals = screen.getByRole('heading', { name: 'The three goals of this version' });
    expect(
      simulation.compareDocumentPosition(model) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(model.compareDocumentPosition(goals) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    expect(within(simulation).getByText('SIMULATION')).toBeVisible();
    expect(
      within(simulation).getByText(
        'Simulated travellers · placeholder rule: half price, half travel time',
      ),
    ).toBeVisible();
    expect(
      within(simulation).getByRole('heading', {
        name: "With Version A's prices, 4 in 100 fewer simulated travellers take the car than with the flat price",
      }),
    ).toBeVisible();
    expect(within(simulation).getByText("With Version A's prices")).toBeVisible();
    expect(within(simulation).getByText('With a flat price 1.00 CHF')).toBeVisible();
    expect(within(model).getByText("PRICING MODEL'S RESULT")).toBeVisible();
    expect(within(model).getByText("The pricing model's own split")).toBeVisible();
    expect(within(model).getByText('Version A, pricing model')).toBeVisible();
    expect(within(model).getByText(/^Why it differs from the simulated split:/)).toBeVisible();
  });

  it('lists the three modes in order in one legend, each with an icon', async () => {
    mount();
    const legend = await screen.findByRole('list', { name: 'Modes' });

    const keys = within(legend).getAllByRole('listitem');
    expect(keys.map((key) => key.textContent)).toEqual([
      '🚗Car',
      '🚋Public transport',
      '🚋+🚲Public transport + shared bike',
    ]);
    expect(screen.getAllByRole('list', { name: 'Modes' })).toHaveLength(1);
  });

  it('names each bar with its three counts and draws every bar on one scale', async () => {
    mount();
    const bar = await screen.findByRole('img', {
      name: "With Version A's prices: Car 30 000, Public transport 30 000, Public transport + shared bike 12 240",
    });
    const segments = bar.querySelectorAll<HTMLElement>('[data-mode]');
    const widths = [...segments].map((segment) => parseFloat(segment.style.width));
    [(100 * 30000) / 72240, (100 * 30000) / 72240, (100 * 12240) / 72240].forEach((want, at) => {
      expect(widths[at]).toBeCloseTo(want, 2);
    });
    expect(
      screen.getByRole('img', { name: /^Version A, pricing model: Car 31 000/ }),
    ).toBeVisible();
  });

  it('writes the caption and ends it with the placeholder and the three-mode sentences', async () => {
    mount();
    const caption = (await screen.findByText(/^Each of the 72 240 travellers/)).closest('p');

    expect(caption?.textContent).toBe(
      "Each of the 72 240 travellers of the period takes the option that scores best on half price, half travel time, while a bike and a dock remain at its stations. 1 240 did not get their first choice (no bike or dock); 2 115 with the flat price. Travellers left with no option: 0 · 0. A placeholder until the model's author defines the simulation. The pricing model prices a shared bike only together with a public transport trip: trips by shared bike alone are not part of these results.",
    );
    expect(within(caption as HTMLElement).queryByRole('link')).not.toBeInTheDocument();
  });

  it("links an unserved count above 0 to the instance version's list of hub pairs", async () => {
    const { onNavigate } = mount({ result: withUnserved(12) });
    const link = await screen.findByRole('link', { name: '12' });

    expect(link).toHaveAttribute('href', '#/lab/geneva-3km.v1');
    await userEvent.click(link);
    expect(onNavigate).toHaveBeenCalledWith({
      kind: 'instance',
      instance: { instanceId: 'geneva-3km', version: 1 },
      period: null,
    });
  });

  it('shows four tiles in order with their weights, labels and model lines', async () => {
    mount();
    const tiles = (await screen.findAllByText('simulated travellers · placeholder rule')).map(
      (label) => label.closest('li') as HTMLElement,
    );
    const [profit, ridership, balance] = tiles as [
      HTMLElement,
      HTMLElement,
      HTMLElement,
      HTMLElement,
    ];

    expect(tiles.map((tile) => tile.getAttribute('data-tile'))).toEqual([
      'profit',
      'ridership',
      'station_balance',
      'average_bike_price',
    ]);
    expect(within(profit).getByText('weight 1 · fixed')).toBeVisible();
    expect(within(ridership).getByText('weight 8.00')).toBeVisible();
    expect(
      within(profit).getByText(
        "Pricing model: 4 175 CHF (revenue 11 544 − cost 7 369) · computed from the model's flows",
      ),
    ).toBeVisible();
    expect(
      within(balance).getByText(
        '22 of 118 stations empty or full at 09:00 · 26 with the flat price · 7 at 08:00',
      ),
    ).toBeVisible();
  });

  it('puts the blue tag over model numbers only, never over a simulated one', async () => {
    mount();
    await screen.findByText('Result · pipeline step 6');

    const blue = screen.getAllByText("PRICING MODEL'S RESULT");
    // The model group's own tag, and the tags of the two tiles whose model line is the model's.
    expect(blue).toHaveLength(3);
    expect(within(screen.getByTestId('simulation-group')).queryByText(/PRICING MODEL/)).toBeNull();
    expect(within(screen.getByTestId('model-group')).queryByText('SIMULATION')).toBeNull();
    expect(
      within(screen.getByTestId('model-group')).queryByText(/Simulated travellers/),
    ).toBeNull();
    for (const tag of blue.slice(1)) {
      const line = tag.closest('p') as HTMLElement;
      expect(line.className).toMatch(/model/);
      expect(line.textContent).toMatch(/^Pricing model: /);
      expect(line.closest('li')?.querySelector('[class*="figure"]')?.contains(tag)).toBe(false);
    }
  });

  it('shows the skeleton alone on the first read and the earlier render under it on a re-read', async () => {
    let release: (() => void) | undefined;
    const fake = fakePricing([version]);
    const gateway: Gateways['pricing'] = {
      ...fake.gateway,
      result: async (id) => {
        const answer = await fake.gateway.result(id);
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return answer;
      },
    };
    const answerRead = async () => {
      await vi.waitFor(() => {
        expect(release).toBeDefined();
      });
      const open = release;
      release = undefined;
      await act(async () => {
        open?.();
        await Promise.resolve();
      });
    };
    const { client } = mount({ gateway });

    expect(await screen.findByRole('status', { name: 'Loading' })).toBeVisible();
    expect(screen.queryByTestId('previous-render')).not.toBeInTheDocument();
    expect(screen.queryByText('Result · pipeline step 6')).not.toBeInTheDocument();
    await answerRead();
    expect(await screen.findByText('Result · pipeline step 6')).toBeVisible();
    expect(screen.queryByTestId('previous-render')).not.toBeInTheDocument();

    await act(() => {
      void client.invalidateQueries({ queryKey: ['pricing-result'] });
      return Promise.resolve();
    });
    const previous = await screen.findByTestId('previous-render');
    expect(within(previous).getByText('Result · pipeline step 6')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Loading' })).toBeVisible();
    await answerRead();
    await vi.waitFor(() => {
      expect(screen.queryByTestId('previous-render')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Result · pipeline step 6')).toBeVisible();
  });

  it('keeps the shown result when a re-read fails', async () => {
    let fail = false;
    const fake = fakePricing([version]);
    const gateway: Gateways['pricing'] = {
      ...fake.gateway,
      result: (id) => (fail ? Promise.reject(new Error('network')) : fake.gateway.result(id)),
    };
    const { client } = mount({ gateway });
    expect(await screen.findByText('Result · pipeline step 6')).toBeVisible();

    fail = true;
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['pricing-result'] });
    });
    expect(screen.getByText('Result · pipeline step 6')).toBeVisible();
    expect(screen.queryByText(/^The result could not be read/)).not.toBeInTheDocument();
  });

  it("writes the share of rides under the cost in percent of the API's fraction", async () => {
    mount();
    const price = await screen.findByTestId('tile-average_bike_price');
    expect(price.textContent).toContain('4 667 rides (38 %) under the cost of');
  });

  it('says so when no result is stored', async () => {
    const fake = fakePricing([version], { 'geneva-3km.v1.A': null });
    mount({ gateway: fake.gateway });

    expect(
      await screen.findByText('The result could not be read: no stored result.'),
    ).toBeVisible();
  });

  describe('price and flow per hub pair', () => {
    const linkName = /^Price and flow per hub pair \(/;

    it('ends the result with the link, counting the pairs with routes and those with a bike option', async () => {
      mount();

      const link = await screen.findByRole('button', { name: linkName });
      expect(link).toHaveAttribute('aria-expanded', 'false');
      expect(link).toHaveTextContent(/^▸ /);
      expect(link).toHaveTextContent(
        /Price and flow per hub pair \(\d[\d ]* hub pairs, 2 with a bike option offered\)$/,
      );
      expect(screen.queryByRole('table', { name: 'Price and flow per hub pair' })).toBeNull();
      const goals = screen.getByRole('heading', { name: 'The three goals of this version' });
      expect(goals.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it('opens and closes the table, and a row opens its options', async () => {
      mount();
      const user = userEvent.setup();

      await user.click(await screen.findByRole('button', { name: linkName }));

      const table = screen.getByRole('table', { name: 'Price and flow per hub pair' });
      expect(within(table).getAllByRole('button', { name: 'Show on map' })).toHaveLength(3);
      await user.click(within(table).getByText('H4 Plainpalais → H9 Eaux-Vives'));
      expect(
        within(screen.getByRole('table', { name: 'Offered bike options' })).getAllByRole('row'),
      ).toHaveLength(4);

      await user.click(screen.getByRole('button', { name: linkName }));
      expect(screen.queryByRole('table', { name: 'Price and flow per hub pair' })).toBeNull();
    });

    it('presses "Show on map" for one pair at a time and releases it', async () => {
      mount();
      const user = userEvent.setup();
      await user.click(await screen.findByRole('button', { name: linkName }));

      const buttons = screen.getAllByRole('button', { name: 'Show on map' });
      await user.click(nth(buttons, 0));
      expect(buttons[0]).toHaveAttribute('aria-pressed', 'true');
      await user.click(nth(buttons, 1));
      expect(buttons[0]).toHaveAttribute('aria-pressed', 'false');
      expect(buttons[1]).toHaveAttribute('aria-pressed', 'true');
      await user.click(nth(buttons, 1));
      expect(buttons[1]).toHaveAttribute('aria-pressed', 'false');
    });
  });
});
