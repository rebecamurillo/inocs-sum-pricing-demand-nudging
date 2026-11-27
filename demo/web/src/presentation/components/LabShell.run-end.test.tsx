import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { fakeCityInstances } from '../../application/ports/fake-city-instance-gateway';
import {
  fakePricingGateway,
  sampleSealedPricing,
} from '../../application/ports/fake-pricing-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { PricingGateway } from '../../application/ports/pricing-gateway';
import {
  fakeRunGateway,
  sampleRunningBuild,
  sampleStep,
} from '../../application/ports/fake-run-gateway';
import { DEFAULT_LAYOUT } from '../../domain/layout';
import type { PricingVersion } from '../../domain/pricing-version';
import type { Run } from '../../domain/run';
import { GatewaysProvider } from '../hooks/gateways';
import { fakeMapFactory, installBrowserStubs } from '../map/fake-map';
import { MapFactoryProvider } from '../map/MapContext';
import { LabShell } from './LabShell';

const allowed = { allowed: true, reasons: [] };

const runningA: Run = {
  ...sampleRunningBuild,
  id: 'run-pricing-A',
  kind: 'pricing',
  subject: { type: 'pricing_version', id: 'geneva-3km.v1.A' },
  steps: [
    sampleStep({ step: 'pricing_model', number: 5, state: 'running', startedAt: new Date() }),
    sampleStep({ step: 'traveller_simulation', number: 6 }),
  ],
};

let stubs: ReturnType<typeof installBrowserStubs>;

beforeEach(() => {
  stubs = installBrowserStubs(false);
});

afterEach(() => {
  stubs.restore();
  window.location.hash = '';
});

describe('LabShell · the end of a pricing run on its own L-2', () => {
  it('opens the result route when the version turns `result` before the run is read again', async () => {
    let version: PricingVersion = sampleSealedPricing({ state: 'running', runId: runningA.id });
    const base = fakePricingGateway([version]);
    const pricing: PricingGateway = {
      ...base,
      list: () => Promise.resolve([version]),
      get: () => Promise.resolve(version),
    };
    const runs = fakeRunGateway([runningA]);
    const gateways: Gateways = {
      systemStatus: {
        load: () =>
          Promise.resolve({
            components: [],
            canBuildInstances: allowed,
            canRunPricing: allowed,
            canSimulate: allowed,
          }),
      },
      layoutPreferences: { load: () => DEFAULT_LAYOUT, save: () => undefined },
      cityDatasets: { list: () => Promise.resolve([]) },
      basemap: { exists: () => Promise.resolve(false), url: () => '' },
      cityInstances: fakeCityInstances(),
      runs,
      pricing,
    };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    window.location.hash = '#/lab/geneva-3km.v1/pricing/A';
    render(
      <QueryClientProvider client={client}>
        <GatewaysProvider gateways={gateways}>
          <MapFactoryProvider factory={fakeMapFactory().factory}>
            <LabShell />
          </MapFactoryProvider>
        </GatewaysProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('button', { name: 'Running…' })).toBeDisabled();

    // The run list answers first: the version is read again and has its result, while the
    // cached run still says running (its own poll comes up to 2 s later).
    version = { ...version, state: 'result' };
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['pricing-version'] });
    });

    await waitFor(() => {
      expect(window.location.hash).toBe('#/lab/geneva-3km.v1/result/A');
    });
  });
});
