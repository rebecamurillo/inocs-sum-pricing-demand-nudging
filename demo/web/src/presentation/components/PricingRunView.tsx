import { useEffect, useRef, useState } from 'react';
import { versionTag } from '../../domain/l1-text';
import {
  CONTINUES,
  DUPLICATE,
  PRICING_RUN_BRIEF,
  RESULT_OPENS,
  RUNNING_LABEL,
  changedGoals,
  instanceLine,
  openMeanwhileLabel,
  previousFinished,
  pricingFailureReason,
  pricingModelLine,
  runAgainLabel,
  simulationLine,
  type PricingStepLine,
} from '../../domain/pricing-run-text';
import { PRICING_BRIEF, pricingVersionName } from '../../domain/pricing-goals-text';
import { pricingVersionId, type PricingVersion } from '../../domain/pricing-version';
import type { LabRoute } from '../../domain/route';
import type { Run, RunStep } from '../../domain/run';
import { isActive } from '../../domain/run';
import {
  OPEN_LOG,
  RUN_AGAIN,
  STEP_NAMES,
  cancelLabels,
  cancelQuestion,
  cancelledCard,
  elapsedSeconds,
  failedStepLine,
  queuedAgainLine,
  queuedSentence,
  runnerSilentLine,
  subjectName,
} from '../../domain/run-text';
import { clockTime } from '../../domain/l1-text';
import { missingPricingVersionLabel, nothingAtThisLink } from '../../domain/unknown-link';
import { useInstanceMenu, useInstanceView } from '../hooks/useCityInstances';
import {
  usePricingActions,
  usePricingList,
  usePricingRunSync,
  usePricingVersion,
} from '../hooks/usePricingVersions';
import { useActiveRuns, useNow, useRun, useRunActions } from '../hooks/useRuns';
import { LoadingCard } from './LoadingCard';
import styles from './BuildingView.module.css';
import own from './PricingRunView.module.css';

interface PricingRunViewProps {
  readonly instanceVersionId: string;
  readonly instanceId: string;
  readonly number: number;
  readonly letter: string;
  readonly advancedView: boolean;
  readonly onNavigate: (route: LabRoute) => void;
}

interface CardProps extends Omit<PricingRunViewProps, 'letter'> {
  readonly version: PricingVersion;
  readonly instanceLabel: string;
  readonly hubPairs: number | null;
}

function StepItem({ line }: { line: PricingStepLine }) {
  return (
    <li className={styles.step} data-tone={line.tone}>
      <span className={styles.status}>
        {line.mark === null ? (
          line.text
        ) : (
          <>
            <span className={styles.spinner} aria-hidden="true">
              {line.mark}
            </span>{' '}
            {line.text}
          </>
        )}
      </span>
    </li>
  );
}

function stepOf(run: Run, name: RunStep['step']): RunStep {
  return (
    run.steps.find((step) => step.step === name) ?? {
      step: name,
      number: name === 'pricing_model' ? 5 : 6,
      state: 'pending',
      startedAt: null,
      finishedAt: null,
      counts: {},
      progress: null,
      lastDurationS: null,
    }
  );
}

function ChangesBlock({ version }: { version: PricingVersion }) {
  const sourceId = version.keptFrom?.id ?? version.basedOnId;
  const source = usePricingVersion(sourceId).data ?? null;
  const rows = changedGoals(version, source);
  if (source === null || rows.length === 0) return null;
  return (
    <table className={own.changes}>
      <thead>
        <tr>
          <th scope="col">What this version changes</th>
          <th scope="col">Version {source.letter}</th>
          <th scope="col">Version {version.letter}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.name}>
            <td>{row.name}</td>
            <td>
              <s className={own.struck}>{row.before}</s>
            </td>
            <td>
              <b>{row.after}</b>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Card({
  version,
  instanceVersionId,
  instanceId,
  number,
  instanceLabel,
  hubPairs,
  advancedView,
  onNavigate,
}: CardProps) {
  const { run, answeredAt, isError, error } = useRun(version.runId);
  const { runs: activeRuns } = useActiveRuns();
  const menu = useInstanceMenu().data ?? [];
  const versions = usePricingList(instanceVersionId).data ?? [];
  const actions = useRunActions(instanceVersionId);
  const pricing = usePricingActions();
  const [confirming, setConfirming] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const active = run !== null && isActive(run);
  const now = useNow(active && run.runner.alive, answeredAt);
  usePricingRunSync(run);

  const resultRoute: LabRoute = {
    kind: 'result',
    instance: { instanceId, version: number },
    letter: version.letter,
    period: null,
  };
  // The end of the run on its own view opens the result, once: whichever of the run and the
  // version (read again when the run list sees the run end) says so first.
  const opened = useRef<string | null>(null);
  const succeeded = run?.state === 'succeeded' || version.state === 'result';
  useEffect(() => {
    if (run === null || !succeeded || opened.current === run.id) return;
    opened.current = run.id;
    onNavigate(resultRoute);
    // `resultRoute` is rebuilt each render; the run's id and state say when to open it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.id, succeeded]);

  if (isError) return <p className={styles.error}>The run could not be read: {error?.message}</p>;
  if (run === null) return <LoadingCard />;

  const flat = version.goals.flat_price_per_ride_chf;
  const model = stepOf(run, 'pricing_model');
  const simulation = stepOf(run, 'traveller_simulation');
  const clock = (step: RunStep) => ({
    elapsedS: elapsedSeconds(run, answeredAt, now, step.startedAt),
  });
  const failure = run.failure;
  const failedStep = run.steps.find((step) => step.state === 'failed');
  const failedKey =
    failedStep?.step === 'traveller_simulation' || failure?.step === 'traveller_simulation'
      ? 'traveller_simulation'
      : 'pricing_model';
  const reason = failure === null ? null : pricingFailureReason(failure.code, failure.reason);

  const running = activeRuns.find((candidate) => candidate.state === 'running');
  const queuedRuns = activeRuns.filter((candidate) => candidate.state === 'queued');
  const ahead = running ?? queuedRuns.find((candidate) => candidate.id !== run.id);
  const showQueued = run.state === 'queued' && ahead !== undefined && run.queuePosition !== null;
  const silent = active && !run.runner.alive;
  const firstOpen = run.steps.find((step) => step.state !== 'done' && step.state !== 'kept');
  const heartbeat = run.runner.lastHeartbeatAt;
  const previous = previousFinished(versions, version.letter);
  const queued = run.state === 'queued';
  const labels = cancelLabels(queued);
  const name = `Version ${version.letter}`;
  const stopped = run.steps.find((step) => step.state === 'cancelled')?.step ?? 'pricing_model';

  const runAgain = () => {
    setRefused(null);
    pricing.run.mutate(
      { id: version.id, flush: () => Promise.resolve() },
      {
        onSuccess: (answer) => {
          if (answer.kind === 'refused') setRefused(answer.detail);
        },
      },
    );
  };
  const duplicate = () => {
    pricing.duplicate.mutate(version, {
      onSuccess: (draft) => {
        onNavigate({
          kind: 'pricing',
          instance: { instanceId, version: number },
          letter: draft.letter,
          period: null,
        });
      },
    });
  };
  const failedActions = pricing.run.isError
    ? pricing.run.error.message
    : pricing.duplicate.isError
      ? pricing.duplicate.error.message
      : null;

  let bar;
  if (run.state === 'failed') {
    bar = (
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.primary}
          disabled={pricing.run.isPending}
          onClick={runAgain}
        >
          {runAgainLabel(failedKey)}
        </button>
        <button
          type="button"
          className={styles.secondary}
          disabled={pricing.duplicate.isPending}
          onClick={duplicate}
        >
          {DUPLICATE}
        </button>
      </div>
    );
  } else if (run.state === 'cancelled') {
    bar = (
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.primary}
          disabled={pricing.run.isPending}
          onClick={runAgain}
        >
          {RUN_AGAIN}
        </button>
        <button
          type="button"
          className={styles.secondary}
          disabled={pricing.duplicate.isPending}
          onClick={duplicate}
        >
          {DUPLICATE}
        </button>
      </div>
    );
  } else if (confirming) {
    bar = (
      <div className={styles.confirm} role="group" aria-label="Cancel this run">
        <p>{cancelQuestion(name, queued, 'pricing')}</p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.primary}
            disabled={actions.cancel.isPending}
            onClick={() => {
              actions.cancel.mutate(run.id, {
                onSuccess: () => {
                  setConfirming(false);
                },
              });
            }}
          >
            {labels.confirm}
          </button>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              setConfirming(false);
            }}
          >
            {labels.keep}
          </button>
        </div>
        {actions.cancel.isError && <p className={styles.error}>{actions.cancel.error.message}</p>}
      </div>
    );
  } else if (active) {
    bar = (
      <div className={styles.actions}>
        <button type="button" className={styles.primary} disabled>
          {RUNNING_LABEL}
        </button>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            setConfirming(true);
          }}
        >
          {labels.open}
        </button>
        {previous !== null && (
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              onNavigate({ ...resultRoute, letter: previous.letter });
            }}
          >
            {openMeanwhileLabel(previous.letter)}
          </button>
        )}
      </div>
    );
  } else {
    bar = null;
  }

  return (
    <div className={styles.view}>
      <p className={styles.brief}>
        <span className={styles.rhythm}>{PRICING_BRIEF}</span>
        <span>{PRICING_RUN_BRIEF}</span>
      </p>
      <div className={styles.head}>
        <h2 className={styles.name}>{pricingVersionName(version)}</h2>
        <span className={styles.tag}>{versionTag(number)}</span>
      </div>
      {silent && (
        <p className={styles.notice} role="status">
          {runnerSilentLine(heartbeat === null ? null : clockTime(heartbeat))}
        </p>
      )}
      {active && run.attempt >= 2 && firstOpen !== undefined && (
        <p className={styles.notice}>{queuedAgainLine(STEP_NAMES[firstOpen.step], run.attempt)}</p>
      )}
      {showQueued && (
        <p className={styles.sentence}>
          {queuedSentence(run.queuePosition + 1, subjectName(ahead, menu), ahead.kind)}
        </p>
      )}
      {run.state === 'cancelled' && (
        <p className={styles.sentence}>
          {cancelledCard(STEP_NAMES[stopped], run.finishedAt ?? run.serverTime)}
        </p>
      )}
      <ol className={styles.steps} aria-label="Pricing run steps">
        <li className={styles.step} data-tone="done">
          <span className={styles.status}>{instanceLine(instanceLabel, hubPairs)}</span>
        </li>
        <StepItem line={pricingModelLine(model, clock(model))} />
        <StepItem line={simulationLine(simulation, clock(simulation), version.letter, flat)} />
      </ol>
      <p className={styles.sentence}>{RESULT_OPENS}</p>
      {run.state === 'failed' && reason !== null && (
        <p className={styles.reason} role="alert">
          {failedStepLine(STEP_NAMES[failedKey], reason)}
        </p>
      )}
      {run.state === 'failed' && advancedView && failure !== null && (
        <p className={styles.reason}>
          {failure.reason}{' '}
          <a
            className={styles.link}
            href={`/api/v1/runs/${encodeURIComponent(run.id)}/log`}
            target="_blank"
            rel="noreferrer"
          >
            {OPEN_LOG}
          </a>
        </p>
      )}
      <ChangesBlock version={version} />
      {active && <p className={styles.sentence}>{CONTINUES}</p>}
      {bar}
      {refused !== null && <p className={styles.error}>{refused}</p>}
      {failedActions !== null && <p className={styles.error}>{failedActions}</p>}
    </div>
  );
}

/** L-2 of a pricing version that was run: the running or queued card, the failed card, the cancelled card. */
export function PricingRunView(props: PricingRunViewProps) {
  const id = pricingVersionId(props.instanceVersionId, props.letter);
  const query = usePricingVersion(id);
  const view = useInstanceView(props.instanceVersionId);
  if (query.isPending || view.isPending) return <LoadingCard />;
  if (query.isError || view.isError) {
    const message = query.error?.message ?? view.error?.message ?? '';
    return <p className={styles.error}>The pricing version could not be read: {message}</p>;
  }
  const instanceName = view.data?.instanceName ?? props.instanceId;
  const label = `${instanceName} ${versionTag(props.number)}`;
  if (query.data === null) {
    return <p>{nothingAtThisLink(label, missingPricingVersionLabel(props.letter))}</p>;
  }
  return (
    <Card
      key={query.data.id}
      {...props}
      version={query.data}
      instanceLabel={label}
      hubPairs={view.data?.version.counts?.hubPairsWithRoutes ?? null}
    />
  );
}
