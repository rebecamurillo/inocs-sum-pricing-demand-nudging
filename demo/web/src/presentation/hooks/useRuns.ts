import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import {
  cancelRun,
  loadActiveRuns,
  loadRun,
  runAgain,
} from '../../application/use-cases/follow-run';
import { isActive, type Run } from '../../domain/run';
import { useGateways } from './gateways';
import { INSTANCE_MENU_KEY, instanceViewKey } from './useCityInstances';

/** The open run is read this often while it is queued or running. */
export const RUN_POLL_MS = 2000;
/** The list of queued and running runs: this often while it has a run, `IDLE_POLL_MS` otherwise. */
export const ACTIVE_POLL_MS = 2000;
export const IDLE_POLL_MS = 15_000;

export const runKey = (runId: string | null) => ['run', runId] as const;
export const ACTIVE_RUNS_KEY = ['runs', 'active'] as const;

/** The open run, read again every 2 s until it ends; `answeredAt` is the browser's time of the answer. */
export function useRun(runId: string | null) {
  const { runs } = useGateways();
  const query = useQuery({
    queryKey: runKey(runId),
    queryFn: async () => {
      const run = await loadRun({ runs }, runId ?? '');
      return { run, answeredAt: Date.now() };
    },
    enabled: runId !== null,
    refetchInterval: (current) => {
      const run = current.state.data?.run;
      return run !== undefined && isActive(run) ? RUN_POLL_MS : false;
    },
    retry: false,
  });
  return {
    run: query.data?.run ?? null,
    answeredAt: query.data?.answeredAt ?? 0,
    isError: query.isError,
    error: query.error,
  };
}

/** The queued and running runs: every 2 s while there is one, every 15 s while there is none. */
export function useActiveRuns() {
  const { runs } = useGateways();
  const query = useQuery({
    queryKey: ACTIVE_RUNS_KEY,
    queryFn: async () => ({ runs: await loadActiveRuns({ runs }), answeredAt: Date.now() }),
    refetchInterval: (current) =>
      (current.state.data?.runs.length ?? 0) > 0 ? ACTIVE_POLL_MS : IDLE_POLL_MS,
    retry: false,
  });
  return {
    runs: query.data?.runs ?? [],
    answeredAt: query.data?.answeredAt ?? 0,
  };
}

/**
 * The browser's time in ms, ticking each second while `ticking`; the time of the last answer
 * while it is off, so that a clock stops where the last answer left it.
 */
export function useNow(ticking: boolean, answeredAt: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!ticking) return undefined;
    const timer = setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, [ticking]);
  return ticking ? Math.max(now, answeredAt) : answeredAt;
}

/** What follows a step's or a run's change of state: the subject, the menu and the run list are read again. */
export function useRefreshAll() {
  const client = useQueryClient();
  return (versionId: string | null) =>
    Promise.all([
      client.invalidateQueries({ queryKey: INSTANCE_MENU_KEY }),
      client.invalidateQueries({ queryKey: ACTIVE_RUNS_KEY }),
      ...(versionId === null
        ? []
        : [client.invalidateQueries({ queryKey: instanceViewKey(versionId) })]),
    ]);
}

/** Reads the version, the menu and the run list again when a step or the run changes its state. */
export function useRunSync(run: Run | null, versionId: string) {
  const refresh = useRefreshAll();
  const previous = useRef<string | null>(null);
  const signature =
    run === null ? null : `${run.id}:${run.state}:${run.steps.map((step) => step.state).join(',')}`;
  useEffect(() => {
    if (signature === null) return;
    const before = previous.current;
    previous.current = signature;
    if (before !== null && before !== signature) void refresh(versionId);
    // `refresh` is rebuilt each render; the signature is what says something changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, versionId]);
}

/** The step states of a run, as a key: the map's data are read again when it changes. */
export function stepSignature(run: Run | null): string {
  return run === null
    ? ''
    : run.steps.map((step) => `${String(step.number)}${step.state[0] ?? ''}`).join('');
}

export interface EndedBuild {
  readonly runId: string;
  readonly versionId: string;
}

export interface EndedBuildTracker {
  /** The build that succeeded while another view was open; null when there is none to tell. */
  readonly ended: EndedBuild | null;
  readonly clear: () => void;
}

/**
 * Remembers the build the run line last showed as running; when it leaves the run list and
 * succeeded, it is the ended build until its L-1 is opened or another run shows. Held by a
 * component that stays mounted, so that closing the menu does not forget it.
 */
export function useEndedBuild(openVersionId: string | null, enabled = true): EndedBuildTracker {
  const { runs: gateway } = useGateways();
  const { runs } = useActiveRuns();
  const refresh = useRefreshAll();
  const [ended, setEnded] = useState<EndedBuild | null>(null);
  const watched = useRef<EndedBuild | null>(null);
  const running = runs.find((run) => run.state === 'running');
  const head = running ?? runs.find((run) => run.state === 'queued') ?? null;

  useEffect(() => {
    if (!enabled) return;
    const before = watched.current;
    if (before !== null && !runs.some((run) => run.id === before.runId)) {
      watched.current = null;
      void refresh(before.versionId);
      loadRun({ runs: gateway }, before.runId).then(
        (run) => {
          if (run.state === 'succeeded') setEnded(before);
        },
        () => undefined,
      );
    }
    if (running?.subject.type === 'instance_version') {
      watched.current = { runId: running.id, versionId: running.subject.id };
    }
    // `refresh` is rebuilt each render; the run list is what says a run ended.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs, enabled]);

  if (ended !== null && (head !== null || openVersionId === ended.versionId)) setEnded(null);

  return {
    ended,
    clear: () => {
      setEnded(null);
    },
  };
}

/** Cancelling a run and queuing a build again; each refreshes what it changed. */
export function useRunActions(versionId: string) {
  const { runs, cityInstances } = useGateways();
  const client = useQueryClient();
  const refresh = useRefreshAll();
  const cancel = useMutation({
    mutationFn: (runId: string) => cancelRun({ runs }, runId),
    onSuccess: async (answer) => {
      client.setQueryData(runKey(answer.id), { run: answer, answeredAt: Date.now() });
      await refresh(versionId);
    },
  });
  const again = useMutation({
    mutationFn: () => runAgain({ cityInstances }, versionId),
    onSuccess: (answer) => (answer.kind === 'queued' ? refresh(versionId) : undefined),
  });
  return { cancel, again };
}
