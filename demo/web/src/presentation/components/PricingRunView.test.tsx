import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fakeCityInstances, sampleMenu } from '../../application/ports/fake-city-instance-gateway';
import { fakePricing, sampleSealedPricing } from '../../application/ports/fake-pricing-gateway';
import {
  fakeRunGateway,
  sampleStep,
  type FakeRunGateway,
} from '../../application/ports/fake-run-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { PricingVersion } from '../../domain/pricing-version';
import type { LabRoute } from '../../domain/route';
import type { Run } from '../../domain/run';
import { GatewaysProvider } from '../hooks/gateways';
import { PricingRunView } from './PricingRunView';

const AT = new Date('2026-11-27T10:00:00Z');

const finishedA = sampleSealedPricing({
  id: 'geneva-3km.v1.A',
  letter: 'A',
  runId: 'run-a',
  goals: { pt_fare_chf: 2 },
});

const versionC = (overrides: Partial<PricingVersion> = {}): PricingVersion =>
  sampleSealedPricing({
    id: 'geneva-3km.v1.C',
    letter: 'C',
    name: 'Version C',
    state: 'running',
    runId: 'run-c',
    keptFrom: { id: 'geneva-3km.v1.A', letter: 'A' },
    goals: { pt_fare_chf: 2.4 },
    ...overrides,
  });

/** A pricing run whose server clock follows the browser's. */
function pricingRun(overrides: Partial<Run> = {}): Run {
  return {
    id: 'run-c',
    kind: 'pricing',
    subject: { type: 'pricing_version', id: 'geneva-3km.v1.C' },
    state: 'running',
    attempt: 1,
    queuedAt: AT,
    startedAt: new Date(Date.now() - 185_000),
    finishedAt: null,
    serverTime: new Date(),
    queuePosition: null,
    runner: { alive: true, lastHeartbeatAt: new Date() },
    steps: [
      sampleStep({
        step: 'pricing_model',
        number: 5,
        state: 'running',
        startedAt: new Date(Date.now() - 185_000),
        lastDurationS: 400,
      }),
      sampleStep({ step: 'traveller_simulation', number: 6 }),
    ],
    failure: null,
    ...overrides,
  };
}

function mount(options: {
  version?: PricingVersion;
  runs?: Run[];
  advancedView?: boolean;
  onNavigate?: (route: LabRoute) => void;
}) {
  const pricing = fakePricing([finishedA, options.version ?? versionC()]);
  const runs: FakeRunGateway = fakeRunGateway(options.runs ?? [pricingRun()]);
  const onNavigate = options.onNavigate ?? vi.fn();
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.reject(new Error('not called')) },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: fakeCityInstances({ menu: () => Promise.resolve(sampleMenu) }),
    runs,
    pricing: pricing.gateway,
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <PricingRunView
          instanceVersionId="geneva-3km.v1"
          instanceId="geneva-3km"
          number={1}
          letter="C"
          advancedView={options.advancedView ?? false}
          onNavigate={onNavigate}
        />
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  return { runs, pricing, onNavigate };
}

afterEach(() => {
  vi.useRealTimers();
});

describe('PricingRunView running', () => {
  it('shows the brief, the steps with their clock, the table and the bar', async () => {
    mount({});

    expect(
      await screen.findByText(
        'The pricing model is setting the bike prices for Monday 08:00–09:00; then the travellers are simulated.',
      ),
    ).toBeVisible();
    expect(
      screen.getByText(/^✓ City instance · Geneva 3 km v1 · 1 806 hub pairs with routes$/),
    ).toBeVisible();
    expect(
      screen.getByText(
        /5 Pricing model — running for 3 min \d+ s · last time on this instance: 6 min 40 s/,
      ),
    ).toBeVisible();
    expect(
      screen.getByText(
        "5b Traveller simulation — waiting · with Version C's prices, then with the flat price 1.00 CHF · placeholder rule: half price, half travel time",
      ),
    ).toBeVisible();
    expect(screen.getByText('The result opens when both steps are done.')).toBeVisible();
    expect(screen.getByText('What this version changes')).toBeVisible();
    expect(screen.getByText('2.00').tagName).toBe('S');
    expect(screen.getByText('2.40').tagName).toBe('B');
    expect(
      screen.getByText(
        'It continues if you open another page, and you can queue another version meanwhile.',
      ),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Running…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Open Version A meanwhile' })).toBeVisible();
  });

  it('leaves the last time out when none was measured and the previous button out without a finished version', async () => {
    const run = pricingRun();
    mount({
      version: versionC({ keptFrom: null }),
      runs: [
        {
          ...run,
          steps: [
            sampleStep({ step: 'pricing_model', number: 5, state: 'running', startedAt: AT }),
            sampleStep({ step: 'traveller_simulation', number: 6 }),
          ],
        },
      ],
    });

    expect(await screen.findByText(/5 Pricing model — running for/)).not.toHaveTextContent(
      'last time',
    );
    expect(screen.queryByText('What this version changes')).not.toBeInTheDocument();
  });

  it('opens the previous finished version meanwhile', async () => {
    const user = userEvent.setup();
    const { onNavigate } = mount({});

    await user.click(await screen.findByRole('button', { name: 'Open Version A meanwhile' }));

    expect(onNavigate).toHaveBeenCalledWith({
      kind: 'result',
      instance: { instanceId: 'geneva-3km', version: 1 },
      letter: 'A',
      period: null,
    });
  });

  it('writes the kept steps and step 5b running', async () => {
    mount({
      runs: [
        pricingRun({
          steps: [
            sampleStep({ step: 'pricing_model', number: 5, state: 'kept' }),
            sampleStep({
              step: 'traveller_simulation',
              number: 6,
              state: 'running',
              startedAt: new Date(Date.now() - 62_000),
            }),
          ],
        }),
      ],
    });

    expect(
      await screen.findByText(
        /5 Pricing model — ✓ kept: these goals were already solved on this instance/,
      ),
    ).toBeVisible();
    expect(screen.getByText(/5b Traveller simulation — running for 1 min \d+ s/)).toBeVisible();
  });

  it('opens the result route once when the run ends', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { runs, onNavigate } = mount({});
    await screen.findByText(/5 Pricing model — running for/);

    runs.put(pricingRun({ state: 'succeeded', finishedAt: new Date() }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });

    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith({
        kind: 'result',
        instance: { instanceId: 'geneva-3km', version: 1 },
        letter: 'C',
        period: null,
      });
    });
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  it('stops the clock and says so while the runner is not answering', async () => {
    mount({
      runs: [
        pricingRun({
          runner: { alive: false, lastHeartbeatAt: new Date('2026-11-27T10:42:00Z') },
        }),
      ],
    });

    expect(await screen.findByText(/The runner has not answered since/)).toHaveTextContent(
      /The runner has not answered since .*\. The run is kept and starts again when the runner is back \(once\)\./,
    );
  });

  it('says a run was queued again after a stop of the runner', async () => {
    mount({ runs: [pricingRun({ attempt: 2 })] });

    expect(
      await screen.findByText(
        'The runner stopped during Pricing model. The run was queued again (2nd attempt): Pricing model starts again from the beginning; steps before it are kept.',
      ),
    ).toBeVisible();
  });
});

describe('PricingRunView queued', () => {
  const ahead: Run = pricingRun({
    id: 'run-a2',
    subject: { type: 'pricing_version', id: 'geneva-3km.v1.B' },
  });
  const queued = pricingRun({
    state: 'queued',
    startedAt: null,
    queuePosition: 1,
    steps: [
      sampleStep({ step: 'pricing_model', number: 5 }),
      sampleStep({ step: 'traveller_simulation', number: 6 }),
    ],
  });

  it('says its place in line and offers to remove it from the queue', async () => {
    const user = userEvent.setup();
    const { runs } = mount({ version: versionC({ state: 'queued' }), runs: [ahead, queued] });

    expect(
      await screen.findByText(
        'Queued, 2nd in line: Version B is running. Runs go one at a time; this one starts when the run before it ends.',
      ),
    ).toBeVisible();
    expect(screen.getByText('5 Pricing model — waiting')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Remove from the queue' }));
    expect(
      screen.getByText(
        'Cancel this run? Nothing has run yet. Version C stays in the menu as cancelled: you can run it again or duplicate it.',
      ),
    ).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Remove from the queue' }));

    await waitFor(() => {
      expect(runs.calls).toContain('cancel run-c');
    });
  });
});

describe('PricingRunView cancelling', () => {
  it('asks in place, then sends the cancellation; "Keep running" goes back', async () => {
    const user = userEvent.setup();
    const { runs } = mount({});

    await user.click(await screen.findByRole('button', { name: 'Cancel run' }));
    expect(
      screen.getByText(
        'Cancel this run? The running step stops and is not stored; steps already done are kept. Version C stays in the menu as cancelled: you can run it again or duplicate it.',
      ),
    ).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Keep running' }));
    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Cancel run' }));
    await user.click(screen.getByRole('button', { name: 'Cancel the run' }));

    await waitFor(() => {
      expect(runs.calls).toContain('cancel run-c');
    });
  });
});

describe('PricingRunView failed', () => {
  const failedRun = (
    code: string,
    reason: string,
    step: 'pricing_model' | 'traveller_simulation' = 'pricing_model',
  ): Run =>
    pricingRun({
      state: 'failed',
      finishedAt: new Date(),
      steps: [
        sampleStep({
          step: 'pricing_model',
          number: 5,
          state: step === 'pricing_model' ? 'failed' : 'done',
        }),
        sampleStep({
          step: 'traveller_simulation',
          number: 6,
          state: step === 'pricing_model' ? 'pending' : 'failed',
        }),
      ],
      failure: { step, code, reason },
    });

  it('names the step, the reason in words and offers to run again from it', async () => {
    const user = userEvent.setup();
    const { pricing } = mount({
      version: versionC({ state: 'failed' }),
      runs: [failedRun('solver_no_solution', 'the solver found no solution (status INFEASIBLE)')],
    });

    expect(
      await screen.findByText(
        'Pricing model failed: the solver ended without a solution (no set of prices meets every constraint). Steps before it are kept.',
      ),
    ).toBeVisible();
    expect(screen.queryByText(/time limit/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Open the run's log")).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Run again from Pricing model' }));

    await waitFor(() => {
      expect(pricing.versions().find((version) => version.id === 'geneva-3km.v1.C')?.state).toBe(
        'queued',
      );
    });
  });

  it('offers to run again from the traveller simulation when it broke its check', async () => {
    mount({
      version: versionC({ state: 'failed' }),
      runs: [
        failedRun(
          'simulation_check_failed',
          'the traveller simulation broke its check: the travellers of a pair do not add up',
          'traveller_simulation',
        ),
      ],
    });

    expect(
      await screen.findByRole('button', { name: 'Run again from Traveller simulation' }),
    ).toBeVisible();
    expect(
      screen.getByText(
        "Traveller simulation failed: the traveller simulation broke its check (the travellers of a pair do not add up); nothing was stored. The pricing model's result is kept. Steps before it are kept.",
      ),
    ).toBeVisible();
  });

  it('adds the stored reason and the log link in the Advanced view', async () => {
    mount({
      version: versionC({ state: 'failed' }),
      advancedView: true,
      runs: [failedRun('stage_error', 'RuntimeError: boom')],
    });

    expect(await screen.findByText(/RuntimeError: boom/)).toBeVisible();
    expect(screen.getByRole('link', { name: "Open the run's log" })).toHaveAttribute(
      'href',
      '/api/v1/runs/run-c/log',
    );
  });

  it('offers "Delete…" beside "Duplicate" and asks before deleting the failed version', async () => {
    const user = userEvent.setup();
    const { onNavigate } = mount({
      version: versionC({ state: 'failed' }),
      runs: [failedRun('killed', 'the process was stopped by the system (signal 9)')],
    });

    await user.click(await screen.findByRole('button', { name: 'Delete…' }));

    expect(
      screen.getByText(/^Delete Version C · .+\? This removes its goals and its result\./),
    ).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Delete Version C' }));
    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith({
        kind: 'instance',
        instance: { instanceId: 'geneva-3km', version: 1 },
        period: null,
      });
    });
  });

  it('duplicates into a draft and opens its L-2', async () => {
    const user = userEvent.setup();
    const { onNavigate } = mount({
      version: versionC({ state: 'failed' }),
      runs: [failedRun('killed', 'the process was stopped by the system (signal 9)')],
    });

    await user.click(await screen.findByRole('button', { name: 'Duplicate' }));

    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith(
        expect.objectContaining({ kind: 'pricing', letter: 'B' }),
      );
    });
  });
});

describe('PricingRunView cancelled', () => {
  it('writes where the run stopped and offers "Run again" and "Duplicate"', async () => {
    mount({
      version: versionC({ state: 'cancelled' }),
      runs: [
        pricingRun({
          state: 'cancelled',
          finishedAt: new Date('2026-11-27T10:00:00Z'),
          steps: [
            sampleStep({ step: 'pricing_model', number: 5, state: 'cancelled' }),
            sampleStep({ step: 'traveller_simulation', number: 6 }),
          ],
        }),
      ],
    });

    expect(
      await screen.findByText(
        'Run cancelled during Pricing model on 27 Nov 2026. Steps before it are kept.',
      ),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Run again' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Duplicate' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Delete…' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Running…' })).not.toBeInTheDocument();
  });
});
