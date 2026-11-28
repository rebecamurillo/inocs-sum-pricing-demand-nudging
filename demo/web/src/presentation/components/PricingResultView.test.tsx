import { emptyTrips } from '../../application/ports/fake-trip-gateway';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { fakeCityInstances, sampleMenu } from '../../application/ports/fake-city-instance-gateway';
import {
  fakePricing,
  samplePricingResult,
  sampleSealedPricing,
  sampleShowcase,
} from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway, sampleStep } from '../../application/ports/fake-run-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { PricingResult } from '../../domain/pricing-result';
import type { Run } from '../../domain/run';
import type { SystemStatus, Verdict } from '../../domain/system-status';
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

function mount(
  options: {
    result?: PricingResult;
    gateway?: Gateways['pricing'];
    advancedView?: boolean;
    status?: SystemStatus;
    runs?: readonly Run[];
    details?: Parameters<typeof fakePricing>[2];
    /** Other versions stored with the open one. */
    extra?: readonly ReturnType<typeof sampleSealedPricing>[];
    onCompareOff?: () => void;
  } = {},
) {
  const fake = fakePricing(
    [version, ...(options.extra ?? [])],
    { 'geneva-3km.v1.A': options.result ?? samplePricingResult() },
    options.details,
  );
  const onNavigate = vi.fn<(route: LabRoute) => void>();
  const gateways: Gateways = {
    systemStatus: {
      load: () =>
        options.status === undefined
          ? Promise.reject(new Error('not called'))
          : Promise.resolve(options.status),
    },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: fakeCityInstances({ menu: () => Promise.resolve(sampleMenu) }),
    runs: fakeRunGateway(options.runs),
    pricing: options.gateway ?? fake.gateway,
    trips: emptyTrips,
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
            advancedView={options.advancedView ?? false}
            onNavigate={onNavigate}
            onCompareOff={options.onCompareOff}
          />
        </MapProvider>
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  return { client, onNavigate, fake };
}

const allowed: Verdict = { allowed: true, reasons: [] };
const status = (canSimulate: Verdict = allowed, version: number | null = 2): SystemStatus => ({
  components: [],
  canBuildInstances: allowed,
  canRunPricing: allowed,
  canSimulate,
  simulationRule: version === null ? null : { id: 'balanced-score', version },
});

/** The result of Version A simulated with the placeholder rule v1 while the Lab now has v2. */
const olderResult = (): PricingResult => {
  const base = samplePricingResult();
  const older = (outcome: PricingResult['simulations']['flat']) => ({
    ...outcome,
    ruleVersion: 1,
    ruleCurrent: false,
  });
  return {
    ...base,
    simulations: {
      modelPrices: older(base.simulations.modelPrices),
      flat: older(base.simulations.flat),
    },
  };
};

const AT = new Date('2026-11-27T10:00:00Z');
const simulationRun = (state: 'queued' | 'running', overrides: Partial<Run> = {}): Run => ({
  id: 'run-sim-A',
  kind: 'simulation',
  subject: { type: 'pricing_version', id: 'geneva-3km.v1.A' },
  state,
  attempt: 1,
  queuedAt: AT,
  startedAt: state === 'running' ? AT : null,
  finishedAt: null,
  serverTime: new Date(AT.getTime() + 252_000),
  queuePosition: state === 'queued' ? 1 : null,
  runner: { alive: true, lastHeartbeatAt: AT },
  steps: [
    sampleStep({
      step: 'traveller_simulation',
      number: 6,
      state: state === 'running' ? 'running' : 'pending',
      startedAt: state === 'running' ? AT : null,
    }),
  ],
  failure: null,
  ...overrides,
});

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

  describe('Advanced view', () => {
    const groups = [
      'What the solver maximised',
      'Solver',
      'Traveller simulation',
      "The package's own summary (optimizer/metrics.py)",
      'Parameters used',
      'Choice-model coefficients',
      'About this result',
    ];

    it('is absent with the switch off', async () => {
      mount();
      await screen.findByRole('button', { name: /^Price and flow per hub pair \(/ });

      expect(screen.queryByRole('heading', { name: 'Advanced view' })).toBeNull();
      for (const name of groups) expect(screen.queryByRole('heading', { name })).toBeNull();
    });

    it('adds the seven groups after the hub-pair link with the switch on', async () => {
      mount({ advancedView: true });

      const link = await screen.findByRole('button', { name: /^Price and flow per hub pair \(/ });
      const title = await screen.findByRole('heading', { level: 2, name: 'Advanced view' });
      expect(link.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      for (const name of groups) {
        expect(screen.getByRole('heading', { name })).toBeInTheDocument();
      }
    });

    it('counts the hub pairs and the offered bike options once the table is read', async () => {
      mount({ advancedView: true });

      const solver = (await screen.findByRole('heading', { name: 'Solver' })).closest('section');
      if (solver === null) throw new Error('No Solver group.');
      await within(solver).findByText(/^\d[\d ]* · 4$/);
    });
  });

  describe('simulated with an older rule', () => {
    it('says so above the simulation group, names both rules and dims the simulated figures only', async () => {
      mount({ result: olderResult(), status: status() });

      const box = await screen.findByTestId('older-rule');
      expect(
        within(box).getByText(
          "Simulated with an older rule. These simulations used the placeholder rule v1; the Lab now simulates with v2. The pricing model's numbers do not change.",
        ),
      ).toBeVisible();
      expect(within(box).getByRole('button', { name: 'Simulate again with v2' })).toBeEnabled();
      const group = screen.getByTestId('simulation-group');
      expect(box.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(
        within(group).getByText(
          'Simulated travellers · placeholder rule: half price, half travel time · older rule (v1)',
        ),
      ).toBeVisible();
      expect(
        screen.getByRole('list', { name: 'Simulated split of the travellers' }),
      ).toHaveAttribute('data-older-rule');
      expect(screen.getByTestId('tile-profit').closest('ul')).toHaveAttribute('data-older-rule');
      expect(screen.getByTestId('model-group').querySelector('[data-older-rule]')).toBeNull();
    });

    it('shows no box when the simulations used the current rule, or the current rule is not known', async () => {
      mount({ status: status() });
      await screen.findByTestId('simulation-group');
      expect(screen.queryByTestId('older-rule')).toBeNull();
      expect(
        screen.getByRole('list', { name: 'Simulated split of the travellers' }),
      ).not.toHaveAttribute('data-older-rule');
    });

    it('shows no box when the API names no current rule yet', async () => {
      mount({ result: olderResult(), status: status(allowed, null) });
      await screen.findByTestId('simulation-group');

      expect(screen.queryByTestId('older-rule')).toBeNull();
    });

    it('queues a simulation run when the visitor chooses "Simulate again"', async () => {
      const { fake } = mount({ result: olderResult(), status: status() });

      await userEvent.click(await screen.findByRole('button', { name: 'Simulate again with v2' }));

      await vi.waitFor(() => {
        expect(fake.simulated()).toEqual(['geneva-3km.v1.A']);
      });
    });

    it('shows the API reason when the simulation is refused', async () => {
      mount({
        result: olderResult(),
        status: status(),
        details: { simulateRefusal: 'A run of this version is queued or running.' },
      });

      await userEvent.click(await screen.findByRole('button', { name: 'Simulate again with v2' }));

      expect(await screen.findByText('A run of this version is queued or running.')).toBeVisible();
    });

    it('replaces the action by the running line, keeps the old figures and counts the elapsed time', async () => {
      mount({ result: olderResult(), status: status(), runs: [simulationRun('running')] });

      const box = await screen.findByTestId('older-rule');
      expect(
        await within(box).findByText('Traveller simulation · running for 4 min 12 s'),
      ).toBeVisible();
      expect(within(box).queryByRole('button')).toBeNull();
      expect(
        screen.getByRole('img', { name: /^With Version A's prices: Car 30 000/ }),
      ).toBeVisible();
    });

    it('says the simulation is queued, behind the run that goes first', async () => {
      const ahead: Run = {
        ...simulationRun('running'),
        id: 'run-pricing-B',
        kind: 'pricing',
        subject: { type: 'pricing_version', id: 'geneva-3km.v1.B' },
      };
      mount({
        result: olderResult(),
        status: status(),
        runs: [ahead, simulationRun('queued', { queuePosition: 1 })],
      });

      const box = await screen.findByTestId('older-rule');
      expect(await within(box).findByText(/^Queued, 2nd in line:/)).toBeVisible();
      expect(within(box).queryByRole('button')).toBeNull();
    });

    it('turns the action off with the reason when the runner is not running', async () => {
      const off: Verdict = {
        allowed: false,
        reasons: [{ component: 'runner', reason: 'No worker reported.' }],
      };
      mount({ result: olderResult(), status: status(off) });

      const box = await screen.findByTestId('older-rule');
      expect(
        await within(box).findByText(
          'Simulation is off: the runner is not running. Stored results stay available.',
        ),
      ).toBeVisible();
      expect(within(box).getByRole('button', { name: 'Simulate again with v2' })).toBeDisabled();
      expect(
        within(box).getAllByText(/^Simulation is off: the runner is not running\./),
      ).toHaveLength(2);
    });

    it('keeps the last rule the status named when it names none any more', async () => {
      const { client } = mount({ result: olderResult(), status: status() });
      await screen.findByTestId('older-rule');

      client.setQueryData(['system-status'], status(allowed, null));

      expect(await screen.findByRole('button', { name: 'Simulate again with v2' })).toBeVisible();
    });
  });

  describe('actions', () => {
    it('holds "Compare versions →" (primary), "Duplicate" and "Delete…", after the goals', async () => {
      mount();
      const compare = await screen.findByRole('button', { name: 'Compare versions →' });
      const duplicate = screen.getByRole('button', { name: 'Duplicate' });
      const remove = screen.getByRole('button', { name: 'Delete…' });
      const goals = screen.getByRole('heading', { name: 'The three goals of this version' });

      const bar = compare.parentElement ?? document.body;
      expect(bar).toBe(duplicate.parentElement);
      expect(bar).toBe(remove.parentElement);
      const buttons = within(bar).getAllByRole('button');
      expect(buttons).toHaveLength(4);
      expect(buttons[0]).toBe(compare);
      expect(buttons[1]).toBe(screen.getByRole('button', { name: 'Open in the traveller view' }));
      expect(compare.className).toMatch(/primary/);
      expect(duplicate.className).not.toMatch(/primary/);
      expect(
        goals.compareDocumentPosition(compare) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });

    it('opens L-4 with the finished versions of the instance version, the open one included', async () => {
      const { onNavigate } = mount({
        extra: ['B', 'C', 'D', 'E'].map((letter) =>
          sampleSealedPricing({ id: `geneva-3km.v1.${letter}`, letter, name: `Version ${letter}` }),
        ),
      });

      await userEvent.click(await screen.findByRole('button', { name: 'Compare versions →' }));

      expect(onNavigate).toHaveBeenCalledWith({
        kind: 'compare',
        instance: { instanceId: 'geneva-3km', version: 1 },
        letters: ['A', 'B', 'C', 'D'],
        period: null,
      });
    });

    it('opens L-5 with this version', async () => {
      const { onNavigate } = mount();

      await userEvent.click(
        await screen.findByRole('button', { name: 'Open in the traveller view' }),
      );

      expect(onNavigate).toHaveBeenCalledWith({
        kind: 'traveller',
        instance: { instanceId: 'geneva-3km', version: 1 },
        letter: 'A',
        period: null,
      });
    });

    it('asks for the off state when fewer than two versions are finished', async () => {
      const onCompareOff = vi.fn();
      const { onNavigate } = mount({ onCompareOff });

      await userEvent.click(await screen.findByRole('button', { name: 'Compare versions →' }));

      expect(onCompareOff).toHaveBeenCalledOnce();
      expect(onNavigate).not.toHaveBeenCalled();
    });

    it('creates a draft from the goals and opens its L-2', async () => {
      const { onNavigate, fake } = mount();

      await userEvent.click(await screen.findByRole('button', { name: 'Duplicate' }));

      await vi.waitFor(() => {
        expect(onNavigate).toHaveBeenCalledWith({
          kind: 'pricing',
          instance: { instanceId: 'geneva-3km', version: 1 },
          letter: 'B',
          period: null,
        });
      });
      expect(fake.versions().map((item) => item.basedOnId)).toContain('geneva-3km.v1.A');
    });

    it('asks before deleting, and "Keep" closes the question', async () => {
      const { fake } = mount();

      await userEvent.click(await screen.findByRole('button', { name: 'Delete…' }));

      const group = screen.getByRole('group', { name: 'Delete' });
      expect(
        within(group).getByText(
          'Delete Version A · Incentive? This removes its goals and its result. Other versions of Geneva 3 km v1 stay. This cannot be undone.',
        ),
      ).toBeVisible();
      await userEvent.click(within(group).getByRole('button', { name: 'Keep' }));
      expect(screen.queryByRole('group', { name: 'Delete' })).toBeNull();
      expect(fake.versions()).toHaveLength(1);
    });

    it("deletes on confirmation and opens the instance version's L-1", async () => {
      const { onNavigate, fake } = mount();

      await userEvent.click(await screen.findByRole('button', { name: 'Delete…' }));
      await userEvent.click(screen.getByRole('button', { name: 'Delete Version A' }));

      await vi.waitFor(() => {
        expect(onNavigate).toHaveBeenCalledWith({
          kind: 'instance',
          instance: { instanceId: 'geneva-3km', version: 1 },
          period: null,
        });
      });
      expect(fake.versions()).toEqual([]);
    });

    it.each([
      ['run_active', 'A run of this version is queued or running.'],
      ['is_showcase', "Version A is the home page's result: choose another one first."],
    ] as const)('shows the %s refusal as a note and stays', async (code, note) => {
      const { onNavigate, fake } = mount({
        details: { removeRefusals: { 'geneva-3km.v1.A': code } },
      });

      await userEvent.click(await screen.findByRole('button', { name: 'Delete…' }));
      await userEvent.click(screen.getByRole('button', { name: 'Delete Version A' }));

      expect(await screen.findByText(note)).toBeVisible();
      expect(screen.queryByRole('group', { name: 'Delete' })).toBeNull();
      expect(onNavigate).not.toHaveBeenCalled();
      expect(fake.versions()).toHaveLength(1);
    });
  });
});

describe('PricingResultView · the home page', () => {
  const action = { name: 'Use on the home page' };
  const heldByB = { ...sampleShowcase, pricingVersionId: 'geneva-3km.v1.B', letter: 'B' };

  it('puts "Use on the home page" between Duplicate and Delete…, with its first hover text', async () => {
    mount();

    const button = await screen.findByRole('button', action);

    const names = screen
      .getAllByRole('button')
      .map((item) => item.textContent)
      .filter((text) => /^(Compare|Open in|Duplicate|Use on|Delete…)/.test(text));
    expect(names).toEqual([
      'Compare versions →',
      'Open in the traveller view',
      'Duplicate',
      'Use on the home page',
      'Delete…',
    ]);
    expect(button).toHaveAttribute('title', "Shows this version's result on the home page.");
  });

  it('names the version it would replace in its hover text', async () => {
    mount({ details: { showcase: heldByB } });

    expect(await screen.findByRole('button', action)).toHaveAttribute(
      'title',
      "Shows this version's result on the home page, in place of Version B's.",
    );
  });

  it('shows the first hover text when the showcase cannot be read', async () => {
    mount({ details: { showcase: new Error('down') } });

    expect(await screen.findByRole('button', action)).toHaveAttribute(
      'title',
      "Shows this version's result on the home page.",
    );
  });

  it('sets the showcase on one click, then shows the link and drops the action', async () => {
    const { fake } = mount();

    await userEvent.click(await screen.findByRole('button', action));

    await vi.waitFor(() => {
      expect(fake.showcaseSet()).toEqual([
        { pricingVersionId: 'geneva-3km.v1.A', periodId: samplePricingResult().periodId },
      ]);
    });
    const link = await screen.findByRole('link', { name: 'On the home page' });
    expect(link).toHaveAttribute('href', '#/');
    expect(screen.queryByRole('button', action)).toBeNull();
    expect(screen.queryByRole('button', { name: /remove|clear/i })).toBeNull();
  });

  it('shows the link and no action when this version is the showcase', async () => {
    mount({ details: { showcase: { ...sampleShowcase, pricingVersionId: 'geneva-3km.v1.A' } } });

    expect(await screen.findByRole('link', { name: 'On the home page' })).toBeVisible();
    expect(screen.queryByRole('button', action)).toBeNull();
  });

  it('keeps the action and says so when the API did not answer', async () => {
    mount({ details: { setShowcaseFails: true } });

    await userEvent.click(await screen.findByRole('button', action));

    expect(
      await screen.findByText("Not set: the demonstrator's API did not answer."),
    ).toBeVisible();
    expect(screen.getByRole('button', action)).toBeVisible();
    expect(screen.queryByRole('link', { name: 'On the home page' })).toBeNull();
  });

  it('shows the note instead of a confirmation when this version is the showcase', async () => {
    mount({ details: { showcase: { ...sampleShowcase, pricingVersionId: 'geneva-3km.v1.A' } } });

    await vi.waitFor(() => {
      expect(screen.queryByRole('button', action)).toBeNull();
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Delete…' }));

    expect(
      screen.getByText("Version A is the home page's result: choose another one first."),
    ).toBeVisible();
    expect(screen.queryByRole('group', { name: 'Delete' })).toBeNull();
  });
});
