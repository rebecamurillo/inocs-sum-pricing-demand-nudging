import { emptyTrips } from '../../application/ports/fake-trip-gateway';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Gateways } from '../../application/ports/gateways';
import { fakePricingGateway } from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import { emptyCityInstances } from '../../application/ports/fake-city-instance-gateway';
import type { SystemStatus } from '../../domain/system-status';
import { GatewaysProvider } from './gateways';
import { SYSTEM_STATUS_POLL_MS, useSystemStatus } from './useSystemStatus';

const allowed = { allowed: true, reasons: [] };
const status: SystemStatus = {
  components: [],
  canBuildInstances: allowed,
  canRunPricing: allowed,
  canSimulate: allowed,
  simulationRule: null,
};

afterEach(() => {
  vi.useRealTimers();
});

describe('useSystemStatus', () => {
  it('reads the status on mount and again every 10 s', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const load = vi.fn(() => Promise.resolve(status));
    const gateways: Gateways = {
      systemStatus: { load },
      layoutPreferences: { load: vi.fn(), save: vi.fn() },
      cityDatasets: { list: () => Promise.resolve([]) },
      basemap: { exists: () => Promise.resolve(false), url: () => '' },
      cityInstances: emptyCityInstances,
      runs: fakeRunGateway(),
      pricing: fakePricingGateway(),
      trips: emptyTrips,
    };
    const client = new QueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <GatewaysProvider gateways={gateways}>{children}</GatewaysProvider>
      </QueryClientProvider>
    );

    const { result } = renderHook(() => useSystemStatus(), { wrapper });
    await waitFor(() => {
      expect(result.current.data).toBe(status);
    });
    expect(load).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(SYSTEM_STATUS_POLL_MS);
    await waitFor(() => {
      expect(load).toHaveBeenCalledTimes(2);
    });
    client.clear();
  });
});
