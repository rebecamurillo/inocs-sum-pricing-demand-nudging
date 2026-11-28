import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { emptyCityInstances } from '../../application/ports/fake-city-instance-gateway';
import { fakePricingGateway } from '../../application/ports/fake-pricing-gateway';
import { fakeRunGateway } from '../../application/ports/fake-run-gateway';
import { emptyTrips } from '../../application/ports/fake-trip-gateway';
import type { Gateways } from '../../application/ports/gateways';
import { DEFAULT_LAYOUT } from '../../domain/layout';
import { GatewaysProvider } from '../hooks/gateways';
import { fakeMapFactory, installBrowserStubs } from '../map/fake-map';
import { MapFactoryProvider } from '../map/MapContext';
import { App } from './App';

let stubs: ReturnType<typeof installBrowserStubs>;

function renderApp() {
  const gateways: Gateways = {
    systemStatus: {
      load: () =>
        Promise.resolve({
          components: [],
          canBuildInstances: { allowed: true, reasons: [] },
          canRunPricing: { allowed: true, reasons: [] },
          canSimulate: { allowed: true, reasons: [] },
          simulationRule: null,
        }),
    },
    layoutPreferences: { load: () => DEFAULT_LAYOUT, save: () => undefined },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: emptyCityInstances,
    runs: fakeRunGateway(),
    pricing: fakePricingGateway(),
    trips: emptyTrips,
  };
  const { factory } = fakeMapFactory();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <MapFactoryProvider factory={factory}>
          <App />
        </MapFactoryProvider>
      </GatewaysProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  stubs = installBrowserStubs(false);
  Element.prototype.scrollIntoView = () => undefined;
});

afterEach(() => {
  cleanup();
  stubs.restore();
  window.location.hash = '';
});

describe('App', () => {
  it.each(['', '#/', '#/play', '#/labx'])('renders Home for %j and keeps the hash', (hash) => {
    window.location.hash = hash;
    renderApp();

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Price shared bikes by the trip',
    );
    expect(window.location.hash).toBe(hash);
  });

  it('renders the Lab on #/lab, and Home when "← Home" is clicked', async () => {
    window.location.hash = '#/lab';
    renderApp();

    expect(screen.getByText('Dynamic pricing · Lab')).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('link', { name: '← Home' }));

    expect(window.location.hash).toBe('#/');
    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument();
  });

  it('replaces a malformed Lab link by #/lab', () => {
    window.location.hash = '#/lab/geneva-3km';
    renderApp();

    expect(window.location.hash).toBe('#/lab');
    expect(screen.getByText('Dynamic pricing · Lab')).toBeInTheDocument();
  });
});
