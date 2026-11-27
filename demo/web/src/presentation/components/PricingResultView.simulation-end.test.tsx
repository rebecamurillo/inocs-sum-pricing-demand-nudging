import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { fakeCityInstances, sampleMenu } from '../../application/ports/fake-city-instance-gateway';
import {
  fakePricing,
  samplePricingResult,
  sampleSealedPricing,
} from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway, sampleStep } from '../../application/ports/fake-run-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { PricingGateway } from '../../application/ports/pricing-gateway';
import type { PricingResult } from '../../domain/pricing-result';
import type { Run } from '../../domain/run';
import type { SystemStatus, Verdict } from '../../domain/system-status';
import { GatewaysProvider } from '../hooks/gateways';
import { ACTIVE_RUNS_KEY } from '../hooks/useRuns';
import { MapProvider } from '../map/MapContext';
import { PricingResultView } from './PricingResultView';

// L-3 on its own, without the menu: nothing else reads the result again when the run ends.

const version = sampleSealedPricing({ name: 'Incentive', state: 'result' });
const allowed: Verdict = { allowed: true, reasons: [] };
const status: SystemStatus = {
  components: [],
  canBuildInstances: allowed,
  canRunPricing: allowed,
  canSimulate: allowed,
  simulationRule: { id: 'balanced-score', version: 2 },
};

function olderResult(): PricingResult {
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
}

const AT = new Date('2026-11-27T10:00:00Z');
const simulationRun = (state: Run['state']): Run => ({
  id: 'run-simulation-A',
  kind: 'simulation',
  subject: { type: 'pricing_version', id: 'geneva-3km.v1.A' },
  state,
  attempt: 1,
  queuedAt: AT,
  startedAt: AT,
  finishedAt: state === 'running' ? null : AT,
  serverTime: AT,
  queuePosition: null,
  runner: { alive: true, lastHeartbeatAt: AT },
  steps: [
    sampleStep({
      step: 'traveller_simulation',
      number: 6,
      state: state === 'running' ? 'running' : 'done',
      startedAt: AT,
    }),
  ],
  failure: null,
});

function mount(pricing: PricingGateway, runs: ReturnType<typeof fakeRunGateway>) {
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.resolve(status) },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: fakeCityInstances({ menu: () => Promise.resolve(sampleMenu) }),
    runs,
    pricing,
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
            onNavigate={vi.fn()}
          />
        </MapProvider>
      </GatewaysProvider>
    </QueryClientProvider>,
  );
  return client;
}

/** A pricing gateway whose result is the older one until `fresh` is set. */
function staleUntilFresh() {
  const stored = fakePricing([version], { 'geneva-3km.v1.A': samplePricingResult() });
  const state = { fresh: false };
  const pricing: PricingGateway = {
    ...stored.gateway,
    result: (id) => (state.fresh ? stored.gateway.result(id) : Promise.resolve(olderResult())),
  };
  return { pricing, state };
}

describe('PricingResultView · the end of a simulation run', () => {
  it('reads the result again when the run it showed leaves the active runs', async () => {
    const { pricing, state } = staleUntilFresh();
    const runs = fakeRunGateway([simulationRun('running')]);
    const client = mount(pricing, runs);
    const box = await screen.findByTestId('older-rule');
    expect(await within(box).findByText(/^Traveller simulation · running for/)).toBeVisible();

    state.fresh = true;
    runs.put(simulationRun('succeeded'));
    await client.invalidateQueries({ queryKey: ACTIVE_RUNS_KEY });

    await waitFor(() => {
      expect(screen.queryByTestId('older-rule')).toBeNull();
    });
  });

  it('reads the result again when the queued run ended before the active runs listed it', async () => {
    const { pricing, state } = staleUntilFresh();
    const runs = fakeRunGateway([]);
    // The worker takes the run and ends it before the run list is read again.
    const ended: PricingGateway = {
      ...pricing,
      simulate: async (id) => {
        const answer = await pricing.simulate(id);
        state.fresh = true;
        runs.put(simulationRun('succeeded'));
        return answer;
      },
    };
    mount(ended, runs);

    await userEvent.click(await screen.findByRole('button', { name: 'Simulate again with v2' }));

    await waitFor(() => {
      expect(screen.queryByTestId('older-rule')).toBeNull();
    });
  });
});
