import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { emptyCityInstances } from '../../application/ports/fake-city-instance-gateway';
import {
  fakeRunGateway,
  sampleBuildSteps,
  sampleRunningBuild,
} from '../../application/ports/fake-run-gateway';
import type { Gateways } from '../../application/ports/gateways';
import type { Run } from '../../domain/run';
import { GatewaysProvider } from './gateways';
import {
  ACTIVE_POLL_MS,
  IDLE_POLL_MS,
  RUN_POLL_MS,
  useActiveRuns,
  useNow,
  useRun,
} from './useRuns';

afterEach(() => {
  vi.useRealTimers();
});

function setup(runs = fakeRunGateway([sampleRunningBuild])) {
  const gateways: Gateways = {
    systemStatus: { load: () => Promise.reject(new Error('not called')) },
    layoutPreferences: { load: vi.fn(), save: vi.fn() },
    cityDatasets: { list: () => Promise.resolve([]) },
    basemap: { exists: () => Promise.resolve(false), url: () => '' },
    cityInstances: emptyCityInstances,
    runs,
  };
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <GatewaysProvider gateways={gateways}>{children}</GatewaysProvider>
    </QueryClientProvider>
  );
  return { runs, client, wrapper };
}

const count = (runs: { calls: string[] }, call: string) =>
  runs.calls.filter((item) => item === call).length;

describe('useRun', () => {
  it('reads the run, polls it every 2 s while it runs and stops when it ends', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { runs, client, wrapper } = setup();

    const { result } = renderHook(() => useRun('run-2'), { wrapper });
    await waitFor(() => {
      expect(result.current.run?.state).toBe('running');
    });
    expect(count(runs, 'get run-2')).toBe(1);

    await vi.advanceTimersByTimeAsync(RUN_POLL_MS);
    await waitFor(() => {
      expect(count(runs, 'get run-2')).toBe(2);
    });

    const ended: Run = { ...sampleRunningBuild, state: 'succeeded', steps: sampleBuildSteps(5) };
    runs.put(ended);
    await vi.advanceTimersByTimeAsync(RUN_POLL_MS);
    await waitFor(() => {
      expect(result.current.run?.state).toBe('succeeded');
    });
    const reads = count(runs, 'get run-2');
    await vi.advanceTimersByTimeAsync(RUN_POLL_MS * 3);
    expect(count(runs, 'get run-2')).toBe(reads);
    client.clear();
  });

  it('records the browser time of the answer', async () => {
    const { client, wrapper } = setup();
    const before = Date.now();

    const { result } = renderHook(() => useRun('run-2'), { wrapper });
    await waitFor(() => {
      expect(result.current.run).not.toBeNull();
    });

    expect(result.current.answeredAt).toBeGreaterThanOrEqual(before);
    client.clear();
  });

  it('reads nothing without a run id', () => {
    const { runs, client, wrapper } = setup();

    const { result } = renderHook(() => useRun(null), { wrapper });

    expect(result.current.run).toBeNull();
    expect(runs.calls).toEqual([]);
    client.clear();
  });
});

describe('useActiveRuns', () => {
  it('polls every 2 s while a run is active and every 15 s while none is', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { runs, client, wrapper } = setup();

    const { result } = renderHook(() => useActiveRuns(), { wrapper });
    await waitFor(() => {
      expect(result.current.runs).toHaveLength(1);
    });
    await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS);
    await waitFor(() => {
      expect(count(runs, 'listActive')).toBe(2);
    });

    runs.put({ ...sampleRunningBuild, state: 'succeeded' });
    await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS);
    await waitFor(() => {
      expect(result.current.runs).toHaveLength(0);
    });
    const reads = count(runs, 'listActive');
    await vi.advanceTimersByTimeAsync(IDLE_POLL_MS - 1000);
    expect(count(runs, 'listActive')).toBe(reads);
    await vi.advanceTimersByTimeAsync(2000);
    await waitFor(() => {
      expect(count(runs, 'listActive')).toBe(reads + 1);
    });
    client.clear();
  });
});

describe('useNow', () => {
  it('ticks each second while it is on and stops when it is off', () => {
    vi.useFakeTimers({ now: new Date('2026-11-27T10:00:00Z') });
    const { result, rerender } = renderHook(({ on }) => useNow(on, 0), {
      initialProps: { on: true },
    });
    const start = result.current;

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(result.current - start).toBe(3000);

    rerender({ on: false });
    const stopped = result.current;
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(result.current).toBe(stopped);
  });

  it('holds the time of the last answer while it is off', () => {
    const { result } = renderHook(() => useNow(false, 1234));

    expect(result.current).toBe(1234);
  });

  it('leaves no timer behind when it unmounts', () => {
    vi.useFakeTimers();
    const { unmount } = renderHook(() => useNow(true, 0));
    expect(vi.getTimerCount()).toBe(1);

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});
