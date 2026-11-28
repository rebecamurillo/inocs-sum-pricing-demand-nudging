import { emptyTrips } from '../../application/ports/fake-trip-gateway';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { fakeCityInstances } from '../../application/ports/fake-city-instance-gateway';
import {
  fakePricing,
  samplePricingDraft,
  sampleSealedPricing,
} from '../../application/ports/fake-pricing-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { PricingGateway } from '../../application/ports/pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import type { PricingVersion } from '../../domain/pricing-version';
import type { LabRoute } from '../../domain/route';
import type { SystemStatus } from '../../domain/system-status';
import { GatewaysProvider } from '../hooks/gateways';
import { PricingGoalsForm } from './PricingGoalsForm';

const allowed = { allowed: true, reasons: [] };
const open: SystemStatus = {
  components: [],
  canBuildInstances: allowed,
  canRunPricing: allowed,
  canSimulate: allowed,
  simulationRule: null,
};
const SAVED = { timeout: 3000 };

interface Options {
  versions?: PricingVersion[];
  pricing?: Partial<PricingGateway>;
  status?: SystemStatus;
  advancedView?: boolean;
  letter?: string;
}

function mount({
  versions,
  pricing,
  status = open,
  advancedView = false,
  letter = 'D',
}: Options = {}) {
  const store = fakePricing(versions ?? [samplePricingDraft()]);
  const gateway: PricingGateway = { ...store.gateway, ...pricing };
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.resolve(status) },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: fakeCityInstances(),
    runs: fakeRunGateway(),
    pricing: gateway,
    trips: emptyTrips,
  };
  const onNavigate = vi.fn<(route: LabRoute) => void>();
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <GatewaysProvider gateways={gateways}>
        <PricingGoalsForm
          instanceVersionId="geneva-3km.v1"
          instanceId="geneva-3km"
          number={1}
          letter={letter}
          advancedView={advancedView}
          onNavigate={onNavigate}
        />
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  return { gateway, onNavigate, store };
}

const field = (name: string) => screen.getByRole('textbox', { name });
const ready = () => screen.findByRole('heading', { name: 'Pricing goals' });

async function type(name: string, text: string) {
  const box = field(name);
  await userEvent.clear(box);
  await userEvent.type(box, text);
}

describe('PricingGoalsForm · reading the goals', () => {
  it('states the brief, the four steps and what each goal means', async () => {
    mount();
    await ready();

    expect(screen.getByText('Pricing version · pipeline step 5')).toBeInTheDocument();
    expect(
      screen.getByText(
        'The model sets a bike price for each bike option it offers on each hub pair, for the period. These values say what it should look for.',
      ),
    ).toBeInTheDocument();
    for (const heading of [
      'Period to price',
      'Cost and lowest price',
      'What the model favours',
      'Kept from Version C',
    ]) {
      expect(screen.getByRole('region', { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByText('CHF per bike ride')).toBeInTheDocument();
    expect(
      screen.getByText(
        'What one bike ride costs to operate. The model subtracts it from the price of every ride.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('The model never prices an offered bike ride under this.'),
    ).toBeInTheDocument();
    expect(screen.getByText('1 · fixed')).toBeInTheDocument();
    expect(screen.getByText('Price minus cost, on every bike ride.')).toBeInTheDocument();
    expect(
      screen.getByText(
        'One more traveller on public transport + bike counts like CHF 8.00 of profit.',
      ),
    ).toBeInTheDocument();
    expect(field('Cost of one ride for the operator')).toHaveValue('0.60');
    expect(field('Ridership weight')).toHaveValue('8.0');
    expect(field('Options shown per hub pair')).toHaveValue('10');
    expect(field('Flat price for the comparison, CHF per ride')).toHaveValue('1.00');
    expect(
      screen.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' }),
    ).toBeEnabled();
  });

  it('offers the hours 06 to 22 and only 08 selectable', async () => {
    mount();
    await ready();

    const hours = within(screen.getByRole('group', { name: 'Periods to price, Monday' }));
    expect(hours.getAllByRole('button')).toHaveLength(17);
    expect(hours.getByRole('button', { name: '08:00 to 09:00' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    const other = hours.getByRole('button', { name: '09:00 to 10:00' });
    expect(other).toBeDisabled();
    expect(other).toHaveAttribute('title', 'Next version');
    expect(screen.getByText('NEXT VERSION')).toBeInTheDocument();
  });

  it('shows no letter for a draft, and "Default values" when nothing was kept', async () => {
    mount({ versions: [samplePricingDraft({ keptFrom: null })] });
    await ready();

    expect(screen.getByRole('region', { name: 'Default values' })).toBeInTheDocument();
    expect(screen.queryByText(/Version D/)).not.toBeInTheDocument();
    expect(field('Name')).toHaveValue('');
    expect(field('Name')).toHaveAttribute('placeholder', 'New version');
  });

  it('writes "This run" with the pairs and the last duration when there is one', async () => {
    mount({ versions: [samplePricingDraft({ lastDurationS: 404 })] });
    await ready();

    expect(screen.getByText('This run: Geneva 3 km v1')).toBeInTheDocument();
    expect(screen.getByText('1 806 hub pairs with routes')).toBeInTheDocument();
    expect(screen.getByText('1 period · Monday 08:00–09:00')).toBeInTheDocument();
    expect(screen.getByText('Last run on this instance: 6 min 44 s')).toBeInTheDocument();
  });

  it('omits the last duration of a first run', async () => {
    mount();
    await ready();

    expect(screen.queryByText(/Last run on this instance/)).not.toBeInTheDocument();
  });

  it('adds the package names in small monospace with Advanced view, none for the flat price', async () => {
    mount({ advancedView: true });
    await ready();

    for (const name of [
      'cost_bike',
      'P_bar',
      'ridership_weight',
      'theta',
      'pt_price',
      'parking_fee',
      'max_displayed_alternatives',
    ]) {
      expect(screen.getByText(name).tagName).toBe('CODE');
    }
    const flat = screen.getByRole('group', { name: 'Flat price for the comparison, CHF per ride' });
    expect(within(flat).queryByText(/_/)).not.toBeInTheDocument();
  });

  it('hides the package names without Advanced view', async () => {
    mount();
    await ready();

    expect(screen.queryByText('P_bar')).not.toBeInTheDocument();
  });

  it('strikes through the previous value of a goal that differs from the kept-from version', async () => {
    mount({
      versions: [
        sampleSealedPricing({
          id: 'geneva-3km.v1.C',
          letter: 'C',
          goals: { ridership_weight: 1.5 },
        }),
        samplePricingDraft(),
      ],
    });
    await ready();

    const ridership = screen.getByRole('group', { name: 'Ridership' });
    expect((await within(ridership).findByText('1.5')).tagName).toBe('S');
  });

  it('says there is nothing at the link for an unknown letter', async () => {
    mount({ letter: 'Q' });

    expect(
      await screen.findByText(
        'Nothing at this link: Geneva 3 km v1 has no Version Q. It may have been deleted.',
      ),
    ).toBeInTheDocument();
  });
});

describe('PricingGoalsForm · what changes at once', () => {
  it('shows the cost message, the bars and the ranking as the visitor types', async () => {
    mount();
    await ready();
    expect(screen.getByText(/Break-even at the lowest price\./)).toBeInTheDocument();
    expect(
      screen.getByText(
        'The model favours, in this order: 1 Ridership · 2 Profit · 3 Station balance',
      ),
    ).toBeInTheDocument();

    await type('Lowest price of a ride', '0.40');
    expect(
      screen.getByText(/On a ride sold at CHF 0.40 the operator loses CHF 0.20\./),
    ).toBeInTheDocument();
    await type('Lowest price of a ride', '0.80');
    expect(
      screen.getByText(/At the lowest price the operator still earns CHF 0.20 on a ride\./),
    ).toBeInTheDocument();

    await type('Station balance weight', '9');
    expect(
      screen.getByText(
        'The model favours, in this order: 1 Station balance · 2 Ridership · 3 Profit',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /counts like up to CHF 9.00 of profit; the opposite ride counts against as much\./,
      ),
    ).toBeInTheDocument();
    const bar = screen.getByRole('img', { name: 'Station balance bar' }).firstElementChild;
    expect(bar).toHaveStyle({ width: '100%' });
  });

  it('keeps the last number while the text is not one', async () => {
    mount();
    await ready();

    await type('Lowest price of a ride', 'abc');

    expect(field('Lowest price of a ride')).toHaveValue('abc');
    expect(screen.getByText(/Break-even at the lowest price\./)).toBeInTheDocument();
  });
});

describe('PricingGoalsForm · autosave', () => {
  it('sends one PATCH 500 ms after the last change, then says "Draft saved"', async () => {
    const patch = vi.fn<PricingGateway['patch']>(() =>
      Promise.resolve(samplePricingDraft({ goals: { lowest_price_chf: 0.4 } })),
    );
    mount({ pricing: { patch } });
    await ready();

    await type('Lowest price of a ride', '0.40');

    expect(patch).not.toHaveBeenCalled();
    expect(
      await screen.findByText(/^Draft saved · \d{2}:\d{2}$/, undefined, SAVED),
    ).toBeInTheDocument();
    expect(patch).toHaveBeenCalledTimes(1);
    expect(patch).toHaveBeenCalledWith('geneva-3km.v1.D', { lowest_price_chf: 0.4 });
  });

  it('sends a typed name trimmed, and nothing for an empty one', async () => {
    const { store } = mount();
    await ready();

    await userEvent.type(field('Name'), '  Cheaper ');
    await screen.findByText(/^Draft saved/, undefined, SAVED);
    expect(store.versions()[0]?.name).toBe('Cheaper');

    await userEvent.clear(field('Name'));
    await new Promise((resolve) => setTimeout(resolve, 700));
    expect(store.versions()[0]?.name).toBe('Cheaper');
  });

  it('turns a broken rule red, names its value and disables the primary', async () => {
    mount();
    await ready();

    await type('Options shown per hub pair', '0');

    expect(
      await screen.findByText(
        'Options shown per hub pair must be at least 1: now 0',
        undefined,
        SAVED,
      ),
    ).toBeInTheDocument();
    expect(field('Options shown per hub pair')).toHaveAttribute('aria-invalid', 'true');
    expect(
      screen.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' }),
    ).toBeDisabled();
    expect(screen.getByText('One rule is not met.')).toBeInTheDocument();

    await type('Options shown per hub pair', '10');
    expect(
      await screen.findByText('Options shown per hub pair: at least 1', undefined, SAVED),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' }),
    ).toBeEnabled();
  });

  it('lists the two rules, each passing', async () => {
    mount();
    await ready();

    const box = screen.getByRole('region', { name: 'Rules checked before running' });
    expect(within(box).getByText('Every amount is 0 or more')).toBeInTheDocument();
    expect(within(box).getByText('Options shown per hub pair: at least 1')).toBeInTheDocument();
  });
});

describe('PricingGoalsForm · running', () => {
  it('waits for the pending PATCH, then posts the run', async () => {
    const log: string[] = [];
    const base = fakePricing([samplePricingDraft()]).gateway;
    const patch = vi.fn((id: string, changes: object) => {
      log.push('patch');
      return base.patch(id, changes);
    });
    const run = vi.fn<PricingGateway['run']>(() => {
      log.push('run');
      return Promise.resolve({ kind: 'queued' as const, runId: 'run-1' });
    });
    mount({ pricing: { patch, run } });
    await ready();

    await type('Cost of one ride for the operator', '0.5');
    await userEvent.click(
      screen.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' }),
    );

    await waitFor(() => {
      expect(run).toHaveBeenCalledWith('geneva-3km.v1.D');
    });
    expect(log).toEqual(['patch', 'run']);
  });

  it('keeps the draft editable and shows the reason when the API refuses', async () => {
    const run = vi.fn<PricingGateway['run']>(() =>
      Promise.resolve({ kind: 'refused' as const, detail: 'The solver is size-limited.' }),
    );
    mount({ pricing: { run } });
    await ready();

    await userEvent.click(
      screen.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' }),
    );

    expect(await screen.findByText('The solver is size-limited.')).toBeInTheDocument();
    expect(field('Lowest price of a ride')).not.toHaveAttribute('readonly');
    expect(
      screen.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' }),
    ).toBeEnabled();
  });

  it('becomes read-only once the run is queued', async () => {
    mount();
    await ready();

    await userEvent.click(
      screen.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' }),
    );

    await waitFor(() => {
      expect(field('Lowest price of a ride')).toHaveAttribute('readonly');
    });
    expect(
      screen.queryByRole('button', { name: 'Run the pricing model · 08:00–09:00' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Discard draft' })).not.toBeInTheDocument();
  });

  it('shows a sealed version read-only, with no action bar', async () => {
    mount({ versions: [sampleSealedPricing({ id: 'geneva-3km.v1.D', letter: 'D' })] });
    await ready();

    expect(field('Cost of one ride for the operator')).toHaveAttribute('readonly');
    expect(field('Name')).toHaveAttribute('readonly');
    expect(screen.getByText('This version was run. Its goals cannot change.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Run the pricing model/ })).not.toBeInTheDocument();
  });
});

describe('PricingGoalsForm · discarding', () => {
  it('asks in place, names the version the values were kept from, and "Keep" closes it', async () => {
    mount();
    await ready();

    await userEvent.click(screen.getByRole('button', { name: 'Discard draft' }));

    expect(
      screen.getByText('Discard this draft? Its values are removed; Version C stays as it is.'),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Keep' }));
    expect(screen.queryByText(/Discard this draft\?/)).not.toBeInTheDocument();
  });

  it('asks the short question for a draft that kept nothing', async () => {
    mount({ versions: [samplePricingDraft({ keptFrom: null })] });
    await ready();

    await userEvent.click(screen.getByRole('button', { name: 'Discard draft' }));

    expect(screen.getByText('Discard this draft? Its values are removed.')).toBeInTheDocument();
  });

  it('deletes the draft and opens the instance version on confirming', async () => {
    const { onNavigate, store } = mount();
    await ready();

    await userEvent.click(screen.getByRole('button', { name: 'Discard draft' }));
    const question = screen.getByText(/Discard this draft\?/).parentElement;
    if (question === null) throw new Error('no confirmation');
    await userEvent.click(within(question).getByRole('button', { name: 'Discard draft' }));

    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith({
        kind: 'instance',
        instance: { instanceId: 'geneva-3km', version: 1 },
        period: null,
      });
    });
    expect(store.versions()).toEqual([]);
  });
});

describe('PricingGoalsForm · the banner', () => {
  const off = (
    component: 'solver' | 'runner' | 'package',
    state: 'limited' | 'unavailable' | 'available',
  ): SystemStatus => ({
    components: [{ name: component, state, reason: 'because' }],
    canBuildInstances: allowed,
    canSimulate: allowed,
    simulationRule: null,
    canRunPricing: { allowed: false, reasons: [{ component, reason: 'because' }] },
  });

  it('names the reason, ends "Stored results stay available." and disables the primary with it', async () => {
    mount({ status: off('solver', 'limited') });

    const sentence =
      "Pricing runs are off: this machine has Gurobi's size-limited licence, which cannot solve a city instance.";
    expect(
      await screen.findByText(`${sentence} Stored results stay available.`),
    ).toBeInTheDocument();
    const primary = screen.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' });
    expect(primary).toBeDisabled();
    expect(screen.getAllByText(sentence, { exact: false })).toHaveLength(2);
  });

  it('shows no banner when only the trip planner is down', async () => {
    mount({
      status: {
        ...open,
        components: [{ name: 'tripPlanner', state: 'unavailable', reason: 'down' }],
      },
    });
    await ready();

    expect(screen.queryByText(/Pricing runs are off/)).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Run the pricing model · 08:00–09:00' }),
    ).toBeEnabled();
  });
});

describe('PricingGoalsForm · the details panel', () => {
  it('is closed by default and opens on the tab of the step', async () => {
    mount();
    await ready();
    expect(
      screen.queryByRole('complementary', { name: 'How the model reads these values' }),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'ⓘ Explain step 3' }));

    const panel = screen.getByRole('complementary', { name: 'How the model reads these values' });
    expect(within(panel).getByRole('tab', { name: '3 Weights' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(within(panel).getByText('What one bike ride is worth to the model')).toBeInTheDocument();
  });

  it('moves the form to one column, and ✕ closes it', async () => {
    mount();
    await ready();
    const work = screen.getByRole('heading', { name: 'Pricing goals' }).closest('[data-details]');

    await userEvent.click(screen.getByRole('button', { name: 'ⓘ Explain step 2' }));
    expect(work).toHaveAttribute('data-details', 'true');

    await userEvent.click(screen.getByRole('button', { name: 'Close the details' }));
    expect(work).toHaveAttribute('data-details', 'false');
    expect(screen.getByRole('button', { name: 'ⓘ Explain step 2' })).toHaveFocus();
  });

  it('reads the values of the form as they change', async () => {
    mount();
    await ready();
    await userEvent.click(screen.getByRole('button', { name: 'ⓘ Explain step 3' }));

    await type('Cost of one ride for the operator', '2');

    const panel = screen.getByRole('complementary', { name: 'How the model reads these values' });
    expect(within(panel).getByText('−0.60')).toBeInTheDocument();
  });
});
