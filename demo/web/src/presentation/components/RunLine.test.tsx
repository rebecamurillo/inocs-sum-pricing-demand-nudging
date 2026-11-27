import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { emptyCityInstances } from '../../application/ports/fake-city-instance-gateway';
import { fakePricingGateway } from '../../application/ports/fake-pricing-gateway';
import {
  fakeRunGateway,
  sampleBuildSteps,
  sampleRunningBuild,
} from '../../application/ports/fake-run-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { InstanceMenuEntry } from '../../domain/city-instance';
import type { Run } from '../../domain/run';
import { GatewaysProvider } from '../hooks/gateways';
import { RunLine } from './RunLine';

const entries: InstanceMenuEntry[] = [
  {
    id: 'geneva-3km',
    name: 'Geneva 3 km',
    datasetId: 'd',
    versions: [
      {
        id: 'geneva-3km.v2',
        number: 2,
        status: 'sealed',
        state: 'building',
        pricingVersionCount: 0,
        pricingVersionLetters: [],
      },
    ],
  },
];

afterEach(() => {
  vi.useRealTimers();
});

/** The running build, 4 min 12 s old when read, on a server clock that follows the browser's. */
function live(overrides: Partial<Run> = {}): Run {
  return {
    ...sampleRunningBuild,
    startedAt: new Date(Date.now() - 252_000),
    serverTime: new Date(Date.now()),
    ...overrides,
  };
}

function mount(
  runs = fakeRunGateway([live()]),
  openVersionId: string | null = null,
  onOpen = vi.fn(),
) {
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.reject(new Error('not called')) },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: emptyCityInstances,
    runs,
    pricing: fakePricingGateway(),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = (open: string | null) => (
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>
        <RunLine entries={entries} openVersionId={open} onOpen={onOpen} />
      </GatewaysProvider>
    </QueryClientProvider>
  );
  const rendered = render(view(openVersionId));
  return {
    runs,
    onOpen,
    client,
    rerender: (open: string | null) => {
      rendered.rerender(view(open));
    },
  };
}

describe('RunLine', () => {
  it('reads "No run in progress" with no run', async () => {
    const { runs } = mount(fakeRunGateway());

    await waitFor(() => {
      expect(runs.calls).toContain('listActive');
    });
    expect(screen.getByText('No run in progress')).toBeVisible();
  });

  it('writes the running build with its clock', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const runs = fakeRunGateway();
    const started = live();
    // The server's clock follows the browser's: each answer carries the time it was given.
    runs.listActive = () => Promise.resolve([{ ...started, serverTime: new Date(Date.now()) }]);
    mount(runs);

    expect(await screen.findByText('● Geneva 3 km v2 building · 4 min 12 s')).toBeVisible();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByText(/^● Geneva 3 km v2 building · 4 min 1[45] s$/)).toBeVisible();
  });

  it('counts the runs queued behind it', async () => {
    const queued = (id: string, position: number): Run => ({
      ...live(),
      id,
      state: 'queued',
      queuePosition: position,
      startedAt: null,
    });
    mount(fakeRunGateway([live(), queued('run-3', 1), queued('run-4', 2)]));

    expect(
      await screen.findByText('● Geneva 3 km v2 building · 4 min 12 s · 2 queued'),
    ).toBeVisible();
  });

  it('says the runner is not answering and stops the clock', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mount(fakeRunGateway([live({ runner: { alive: false, lastHeartbeatAt: null } })]));

    expect(await screen.findByText('● Geneva 3 km v2 · the runner is not answering')).toBeVisible();
  });

  it('polls every 2 s while a run shows and every 15 s when none does', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { runs } = mount();
    await screen.findByText(/building/);
    const reads = () => runs.calls.filter((call) => call === 'listActive').length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await waitFor(() => {
      expect(reads()).toBe(2);
    });

    runs.put({ ...live(), state: 'succeeded', steps: sampleBuildSteps(5) });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await screen.findByText(/ready/);
    const idle = reads();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(reads()).toBe(idle);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    await waitFor(() => {
      expect(reads()).toBe(idle + 1);
    });
  });

  it('says a build is ready when it ended while another view was open, and "Open" opens it', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { runs, onOpen } = mount();
    await screen.findByText(/building/);

    runs.put({ ...live(), state: 'succeeded', steps: sampleBuildSteps(5) });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(await screen.findByText(/^✓ Geneva 3 km v2: ready ·/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Open' }));

    expect(onOpen).toHaveBeenCalledWith('geneva-3km', 2);
    expect(screen.getByText('No run in progress')).toBeVisible();
  });

  it('says nothing of a build that ended while its own L-1 was open', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { runs } = mount(fakeRunGateway([live()]), 'geneva-3km.v2');
    await screen.findByText(/building/);

    runs.put({ ...live(), state: 'succeeded', steps: sampleBuildSteps(5) });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    await waitFor(() => {
      expect(screen.getByText('No run in progress')).toBeVisible();
    });
    expect(screen.queryByText(/ready/)).not.toBeInTheDocument();
  });

  it('says nothing of a build that failed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { runs } = mount();
    await screen.findByText(/building/);

    runs.put({ ...live(), state: 'failed' });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    await waitFor(() => {
      expect(screen.getByText('No run in progress')).toBeVisible();
    });
  });
});
