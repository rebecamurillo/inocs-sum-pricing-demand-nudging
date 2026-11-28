import { useMemo, useState, type ReactNode } from 'react';
import type { InstanceView as InstanceViewValue } from '../../application/use-cases/load-instance-view';
import { versionNumberOf } from '../../domain/draft-text';
import { clockTime, versionTag } from '../../domain/l1-text';
import { circleBounds } from '../../domain/map';
import type { Run, RunStep } from '../../domain/run';
import { isActive } from '../../domain/run';
import {
  OPEN_LOG,
  STEP_NAMES,
  buildingSentence,
  cancelLabels,
  cancelQuestion,
  elapsedSeconds,
  failureReason,
  lastTimeSentence,
  queuedAgainLine,
  queuedSentence,
  runAgainFromLabel,
  runnerSilentLine,
  stepLine,
  stepNameOf,
  subjectName,
} from '../../domain/run-text';
import { L1_BRIEF, L1_SENTENCE } from '../../domain/l1-text';
import { useInstanceGeometry, useInstanceMenu } from '../hooks/useCityInstances';
import {
  stepSignature,
  useActiveRuns,
  useNow,
  useRun,
  useRunActions,
  useRunSync,
} from '../hooks/useRuns';
import { l1Layers } from '../map/l1-layers';
import { useMapFit, useMapLayers } from '../map/MapContext';
import { ChangesTable } from './ChangesTable';
import { LoadingCard } from './LoadingCard';
import { VersionDelete } from './VersionDelete';
import styles from './BuildingView.module.css';

const isDone = (step: RunStep) => step.state === 'done' || step.state === 'kept';

function StepList({
  run,
  answeredAt,
  now,
  view,
  reason,
}: {
  run: Run;
  answeredAt: number;
  now: number;
  view: InstanceViewValue;
  reason: string | null;
}) {
  const { version } = view;
  const basedNumber = version.basedOnId === null ? null : versionNumberOf(version.basedOnId);
  return (
    <ol className={styles.steps} aria-label="Build steps">
      {run.steps.map((step) => {
        const planned = version.buildPlan.steps.find((candidate) => candidate.step === step.step);
        const line = stepLine(step, {
          basedNumber,
          plan: planned,
          elapsedS: elapsedSeconds(run, answeredAt, now, step.startedAt),
          reason,
        });
        const last = planned?.lastDurationS ?? null;
        return (
          <li key={step.step} className={styles.step} data-tone={line.tone}>
            <span className={styles.heading}>{line.heading}</span>
            {line.progress !== null && line.progress.total > 0 && (
              <div
                className={styles.bar}
                role="progressbar"
                aria-label="Hub pairs routed"
                aria-valuemin={0}
                aria-valuenow={line.progress.done}
                aria-valuemax={line.progress.total}
              >
                <span
                  className={styles.fill}
                  style={{ width: `${String((line.progress.done / line.progress.total) * 100)}%` }}
                />
              </div>
            )}
            <span className={styles.status}>
              {line.mark === '●' ? (
                <>
                  <span className={styles.spinner} aria-hidden="true">
                    ●
                  </span>
                  {line.text}
                </>
              ) : line.mark === null ? (
                line.text
              ) : (
                `${line.mark} ${line.text}`.trim()
              )}
            </span>
            {step.state === 'running' && last !== null && (
              <span className={styles.last}>{lastTimeSentence(last)}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function RunBar({
  run,
  versionId,
  name,
  failedStep,
  deletion,
}: {
  run: Run;
  versionId: string;
  name: string;
  failedStep: string | null;
  deletion: ReactNode;
}) {
  const actions = useRunActions(versionId);
  const [confirming, setConfirming] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const queued = run.state === 'queued';
  const labels = cancelLabels(queued);

  if (run.state === 'failed') {
    return (
      <>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.primary}
            disabled={actions.again.isPending}
            onClick={() => {
              setRefused(null);
              actions.again.mutate(undefined, {
                onSuccess: (answer) => {
                  if (answer.kind === 'refused') setRefused(answer.detail);
                },
              });
            }}
          >
            {runAgainFromLabel(failedStep ?? STEP_NAMES.area)}
          </button>
          {deletion}
        </div>
        {refused !== null && <p className={styles.error}>{refused}</p>}
        {actions.again.isError && <p className={styles.error}>{actions.again.error.message}</p>}
      </>
    );
  }
  if (!isActive(run)) return <div className={styles.actions}>{deletion}</div>;
  if (confirming) {
    return (
      <div className={styles.confirm} role="group" aria-label="Cancel this run">
        <p>{cancelQuestion(name, queued)}</p>
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
  }
  return (
    <div className={styles.actions}>
      <button
        type="button"
        className={styles.secondary}
        onClick={() => {
          setConfirming(true);
        }}
      >
        {labels.open}
      </button>
      {deletion}
    </div>
  );
}

/** A build that is queued, running or failed (L-1): its four steps, what is kept, and what can be done. */
export function BuildingView({
  view,
  advancedView,
}: {
  view: InstanceViewValue;
  advancedView: boolean;
}) {
  const { version, instanceName, dataset } = view;
  const { run, answeredAt, isError, error } = useRun(version.buildRunId);
  const { runs: activeRuns } = useActiveRuns();
  const menu = useInstanceMenu().data ?? [];
  const signature = stepSignature(run);
  const geometry = useInstanceGeometry(version.id, signature).data ?? null;
  useRunSync(run, version.id);
  const active = run !== null && isActive(run);
  const now = useNow(active && run.runner.alive, answeredAt);

  const stepDone = (number: number) => {
    const found = run?.steps.find((step) => step.number === number);
    return found !== undefined && isDone(found);
  };
  const [stationsDone, hubsDone, pairsDone] = [stepDone(1), stepDone(2), stepDone(3)];
  // The map follows the build: stops and stations after step 1, the hubs after step 2, the
  // hub-pair lines after step 3.
  const declaration = useMemo(
    () =>
      geometry === null
        ? null
        : l1Layers({
            centre: { lat: version.parameters.centerLat, lon: version.parameters.centerLon },
            radiusM: version.parameters.radiusM,
            stations: stationsDone ? geometry.stations : [],
            hubs: hubsDone ? geometry.hubs : [],
            hubPairs: pairsDone ? geometry.hubPairs : [],
          }),
    [geometry, version.parameters, stationsDone, hubsDone, pairsDone],
  );
  const bounds = useMemo(
    () =>
      circleBounds(
        { lat: version.parameters.centerLat, lon: version.parameters.centerLon },
        version.parameters.radiusM,
      ),
    [version.parameters],
  );
  useMapLayers(declaration);
  useMapFit(bounds);

  if (isError) {
    return <p className={styles.error}>The run could not be read: {error?.message}</p>;
  }
  if (run === null) return <LoadingCard />;

  const basedNumber = version.basedOnId === null ? null : versionNumberOf(version.basedOnId);
  const name = `${instanceName} ${versionTag(version.number)}`;
  const failedStep = run.steps.find((step) => step.state === 'failed');
  const failure = run.failure;
  const reason =
    failure === null
      ? null
      : failureReason(failure.code, version.periods[0]?.routingDate ?? null, failure.reason);
  const failedName =
    failedStep !== undefined
      ? STEP_NAMES[failedStep.step]
      : failure?.step != null
        ? stepNameOf(failure.step)
        : null;
  const running = activeRuns.find((candidate) => candidate.state === 'running');
  const ahead = run.state === 'queued' && running !== undefined && run.queuePosition !== null;
  const silent = active && !run.runner.alive;
  const firstOpen = run.steps.find((step) => !isDone(step));
  const heartbeat = run.runner.lastHeartbeatAt;

  return (
    <div className={styles.view}>
      <p className={styles.brief}>
        <span className={styles.rhythm}>{L1_BRIEF}</span>
        <span>{L1_SENTENCE}</span>
      </p>
      <div className={styles.head}>
        <h2 className={styles.name}>{instanceName}</h2>
        <span className={styles.tag}>{versionTag(version.number)}</span>
      </div>
      {silent && (
        <p className={styles.notice} role="status">
          {runnerSilentLine(heartbeat === null ? null : clockTime(heartbeat))}
        </p>
      )}
      {active && run.attempt >= 2 && firstOpen !== undefined && (
        <p className={styles.notice}>{queuedAgainLine(STEP_NAMES[firstOpen.step], run.attempt)}</p>
      )}
      {ahead && (
        <p className={styles.sentence}>
          {queuedSentence(run.queuePosition + 1, subjectName(running, menu), running.kind)}
        </p>
      )}
      {run.state === 'running' && (
        <p className={styles.sentence}>
          {buildingSentence(elapsedSeconds(run, answeredAt, now), basedNumber)}
        </p>
      )}
      <StepList run={run} answeredAt={answeredAt} now={now} view={view} reason={reason} />
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
      <RunBar
        run={run}
        versionId={version.id}
        name={name}
        failedStep={failedName}
        deletion={
          <VersionDelete
            versionId={version.id}
            instanceName={instanceName}
            number={version.number}
          />
        }
      />
      {basedNumber !== null && (
        <ChangesTable
          changes={version.changes}
          plan={version.buildPlan}
          draftNumber={version.number}
          basedNumber={basedNumber}
          bikeStationsFetchedAt={dataset.bikeStationsFetchedAt}
        />
      )}
    </div>
  );
}
