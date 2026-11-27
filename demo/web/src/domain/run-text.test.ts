import { describe, expect, it } from 'vitest';
import type { PlannedStep } from './city-instance';
import type { Run, RunStep } from './run';
import {
  FAILURE_REASONS,
  NO_RUN,
  PRICING_VERSIONS_OFF,
  buildingSentence,
  cancelLabels,
  cancelQuestion,
  cancelledCard,
  elapsedSeconds,
  failedStepLine,
  failureReason,
  formatDuration,
  keptLabel,
  lastTimeSentence,
  queuedAgainLine,
  queuedSentence,
  routesProgressLine,
  runAgainFromLabel,
  runLineBuilding,
  runLineReady,
  runLineSilent,
  runnerSilentLine,
  stepLine,
  subjectName,
} from './run-text';
import { ordinal } from './ordinal';

const step = (overrides: Partial<RunStep>): RunStep => ({
  step: 'area',
  number: 1,
  state: 'pending',
  startedAt: null,
  finishedAt: null,
  counts: {},
  progress: null,
  ...overrides,
});

const plan = (causes: PlannedStep['causes']): PlannedStep => ({
  step: 'area',
  number: 1,
  action: 'kept',
  causes,
  lastDurationS: null,
});

describe('ordinals', () => {
  it.each([
    [1, '1st'],
    [2, '2nd'],
    [3, '3rd'],
    [4, '4th'],
    [11, '11th'],
    [12, '12th'],
    [13, '13th'],
    [21, '21st'],
    [22, '22nd'],
    [101, '101st'],
    [111, '111th'],
  ])('writes %i as %s', (n, text) => {
    expect(ordinal(n)).toBe(text);
  });
});

describe('durations', () => {
  it('writes seconds, minutes and hours', () => {
    expect(formatDuration(42)).toBe('42 s');
    expect(formatDuration(0)).toBe('0 s');
    expect(formatDuration(252)).toBe('4 min 12 s');
    expect(formatDuration(3780)).toBe('1 h 03 min');
    expect(formatDuration(59.9)).toBe('59 s');
    expect(formatDuration(-5)).toBe('0 s');
  });

  it('writes the last time on the instance', () => {
    expect(lastTimeSentence(252)).toBe('Last time on this instance: 4 min 12 s.');
  });
});

describe('the step lines', () => {
  const ctx = { basedNumber: null, plan: undefined, elapsedS: null, reason: null };

  it('writes a done step with its counts', () => {
    expect(
      stepLine(step({ state: 'done', counts: { stops: 1412, bike_stations: 118 } }), ctx),
    ).toMatchObject({
      heading: '1 Area',
      mark: '✓',
      text: '1 412 stops and platforms · 118 bike stations',
      tone: 'done',
    });
    expect(
      stepLine(step({ step: 'hubs', number: 2, state: 'done', counts: { hubs: 64 } }), ctx).text,
    ).toBe('64 hubs');
    expect(
      stepLine(
        step({ step: 'routes', number: 3, state: 'done', counts: { hub_pairs_with_routes: 1806 } }),
        ctx,
      ).text,
    ).toBe('1 806 hub pairs with routes');
    expect(
      stepLine(
        step({
          step: 'travellers_and_bikes',
          number: 4,
          state: 'done',
          counts: { travellers: 72240 },
        }),
        ctx,
      ).text,
    ).toBe('72 240 travellers');
  });

  it('writes a done step whose counts are not known without them', () => {
    expect(stepLine(step({ state: 'done' }), ctx).text).toBe('');
  });

  it('writes a kept step with where it was kept from', () => {
    const kept = step({ state: 'kept', counts: { stops: 30, bike_stations: 12 } });

    expect(stepLine(kept, { ...ctx, basedNumber: 1, plan: plan([]) }).text).toBe(
      'kept from v1 · 30 stops and platforms · 12 bike stations',
    );
    expect(stepLine(kept, ctx).text).toBe(
      'kept: already computed with the same inputs · 30 stops and platforms · 12 bike stations',
    );
  });

  it('keeps the label short when nothing was counted', () => {
    expect(keptLabel(1, plan([]))).toBe('kept from v1');
    expect(keptLabel(1, plan([{ kind: 'parameter', parameters: ['radius_m'] }]))).toBe(
      'kept: already computed with the same inputs',
    );
    expect(keptLabel(null, undefined)).toBe('kept: already computed with the same inputs');
  });

  it('writes a running step with its elapsed time and a pending step as waiting', () => {
    expect(stepLine(step({ state: 'running' }), { ...ctx, elapsedS: 252 })).toMatchObject({
      mark: '●',
      text: '4 min 12 s',
      tone: 'running',
    });
    expect(stepLine(step({ state: 'pending' }), ctx)).toMatchObject({
      mark: null,
      text: 'waiting',
      tone: 'waiting',
    });
  });

  it('writes the routes step with its pairs done out of the total', () => {
    const routes = step({
      step: 'routes',
      number: 3,
      state: 'running',
      progress: { done: 12, total: 48 },
      counts: { queries_failed: 2 },
    });

    expect(stepLine(routes, { ...ctx, elapsedS: 5 })).toMatchObject({
      heading: '3 Routes — 12 of 48 hub pairs · 2 queries gave no route so far',
      progress: { done: 12, total: 48 },
    });
    expect(routesProgressLine({ done: 1, total: 2 }, 1)).toBe(
      '1 of 2 hub pairs · 1 query gave no route so far',
    );
    expect(routesProgressLine({ done: 1412, total: 1806 }, 0)).toBe(
      '1 412 of 1 806 hub pairs · 0 queries gave no route so far',
    );
  });

  it('writes a failed step in red with its reason', () => {
    const failed = stepLine(step({ step: 'routes', number: 3, state: 'failed' }), {
      ...ctx,
      reason: 'the trip planner did not answer',
    });

    expect(failed).toMatchObject({
      mark: '✕',
      text: 'Routes failed: the trip planner did not answer. Steps before it are kept.',
      tone: 'failed',
    });
  });

  it('writes a cancelled step', () => {
    expect(stepLine(step({ state: 'cancelled' }), ctx).text).toBe('cancelled');
  });
});

describe('the building sentences', () => {
  it('writes the sentence with and without a version it is based on', () => {
    expect(buildingSentence(252, 1)).toBe(
      'Building for 4 min 12 s. It continues if you open another page; v1 and its pricing versions stay available meanwhile.',
    );
    expect(buildingSentence(7, null)).toBe(
      'Building for 7 s. It continues if you open another page.',
    );
  });

  it('writes the queued sentence with the place in line', () => {
    expect(queuedSentence(2, 'Geneva 3 km v2', 'build')).toBe(
      'Queued, 2nd in line: Geneva 3 km v2 is building. Runs go one at a time; this one starts when the run before it ends.',
    );
    expect(queuedSentence(3, 'Version C', 'pricing')).toContain(
      '3rd in line: Version C is running.',
    );
    expect(queuedSentence(12, 'x', 'build')).toContain('12th in line');
  });
});

describe('the runner lines', () => {
  it('writes the silent runner with the time of its last answer', () => {
    expect(runnerSilentLine('10:42')).toBe(
      'The runner has not answered since 10:42. The run is kept and starts again when the runner is back (once).',
    );
    expect(runnerSilentLine(null)).toBe(
      'The runner has not answered. The run is kept and starts again when the runner is back (once).',
    );
  });

  it('writes the run queued again with its attempt', () => {
    expect(queuedAgainLine('Routes', 2)).toBe(
      'The runner stopped during Routes. The run was queued again (2nd attempt): Routes starts again from the beginning; steps before it are kept.',
    );
  });

  it('names no time limit', () => {
    const all = [
      runnerSilentLine('10:42'),
      queuedAgainLine('Routes', 3),
      FAILURE_REASONS.interrupted,
    ];
    expect(all.join(' ')).not.toMatch(/\b\d+ ?(min|minutes|hours?)\b|time limit|timed out/i);
  });
});

describe('the clock', () => {
  const run = (overrides: Partial<Run> = {}) =>
    ({
      startedAt: new Date('2026-11-27T10:00:00Z'),
      serverTime: new Date('2026-11-27T10:04:12Z'),
      runner: { alive: true, lastHeartbeatAt: null },
      ...overrides,
    }) as Run;

  it('offsets the browser clock by the server time seen at the answer', () => {
    // The browser is 1 h 30 min ahead of the server; 3 s after the answer the run is at 4:15.
    const answered = Date.parse('2026-11-27T11:34:12Z');

    expect(elapsedSeconds(run(), answered, answered)).toBe(252);
    expect(elapsedSeconds(run(), answered, answered + 3000)).toBe(255);
    expect(elapsedSeconds(run(), answered, answered + 3999)).toBe(255);
  });

  it('stops at the last answer when the runner is not alive', () => {
    const answered = Date.parse('2026-11-27T10:04:12Z');
    const silent = run({ runner: { alive: false, lastHeartbeatAt: null } });

    expect(elapsedSeconds(silent, answered, answered + 60_000)).toBe(252);
  });

  it('counts from a step start and is never negative', () => {
    const answered = Date.parse('2026-11-27T10:04:12Z');

    expect(elapsedSeconds(run(), answered, answered, new Date('2026-11-27T10:04:00Z'))).toBe(12);
    expect(elapsedSeconds(run(), answered, answered, null)).toBe(0);
    expect(
      elapsedSeconds(run(), answered, answered - 10_000, new Date('2026-11-27T10:05:00Z')),
    ).toBe(0);
  });
});

describe('failure reasons', () => {
  it('writes each of the seven codes', () => {
    expect(Object.keys(FAILURE_REASONS).sort()).toEqual(
      [
        'instance_unbalanced',
        'interrupted',
        'killed',
        'no_public_transport',
        'stage_error',
        'timetable_mismatch',
        'trip_planner_unreachable',
      ].sort(),
    );
    expect(failureReason('trip_planner_unreachable', null, 'x')).toBe(
      'the trip planner did not answer',
    );
    expect(failureReason('instance_unbalanced', null, 'x')).toBe(
      "the model's package could not balance the bike options of this instance",
    );
    expect(failureReason('stage_error', null, 'x')).toBe(
      "an error stopped the step. The details are in the run's log.",
    );
    expect(failureReason('killed', null, 'x')).toBe(
      'the process was stopped by the system; the machine may be out of memory',
    );
    expect(failureReason('interrupted', null, 'x')).toBe(
      'the run was interrupted twice by a stop of the runner',
    );
    expect(failureReason('timetable_mismatch', null, 'x')).toBe(
      "the trip planner's timetable is not the city data's timetable",
    );
  });

  it('writes the routing date of a period without public transport', () => {
    expect(failureReason('no_public_transport', '2025-03-10', 'x')).toBe(
      'the trip planner found no public transport route for any hub pair; the routing date, Monday 10 March 2025, may be outside the timetable (see City data)',
    );
  });

  it('shows the stored reason of a code it does not know', () => {
    expect(failureReason('something_new', null, 'It broke')).toBe('It broke');
  });

  it('closes a reason that ends in a full stop once', () => {
    expect(failedStepLine('Routes', 'the trip planner did not answer')).toBe(
      'Routes failed: the trip planner did not answer. Steps before it are kept.',
    );
    expect(
      failedStepLine('Hubs', "an error stopped the step. The details are in the run's log."),
    ).toBe(
      "Hubs failed: an error stopped the step. The details are in the run's log. Steps before it are kept.",
    );
    expect(runAgainFromLabel('Routes')).toBe('Run again from Routes');
  });
});

describe('cancelling', () => {
  it('writes the confirmation of a running build', () => {
    expect(cancelQuestion('Geneva 3 km v2', false)).toBe(
      'Cancel this run? The running step stops and is not stored; steps already done are kept. Geneva 3 km v2 stays in the menu as cancelled: you can run it again or edit it as a new version.',
    );
    expect(cancelLabels(false)).toEqual({
      open: 'Cancel run',
      confirm: 'Cancel the run',
      keep: 'Keep running',
    });
  });

  it('writes the confirmation of a queued build', () => {
    expect(cancelQuestion('Geneva 3 km v2', true)).toBe(
      'Cancel this run? Nothing has run yet. Geneva 3 km v2 stays in the menu as cancelled: you can run it again or edit it as a new version.',
    );
    expect(cancelLabels(true)).toEqual({
      open: 'Remove from the queue',
      confirm: 'Remove from the queue',
      keep: 'Keep',
    });
  });

  it('writes the cancelled card', () => {
    expect(cancelledCard('Routes', new Date('2026-11-12T10:00:00Z'))).toBe(
      'Run cancelled during Routes on 12 Nov 2026. Steps before it are kept.',
    );
  });
});

describe('the menu and the run line', () => {
  it('writes the run line states', () => {
    expect(runLineBuilding('Geneva 3 km v2', 252, 0)).toBe(
      '● Geneva 3 km v2 building · 4 min 12 s',
    );
    expect(runLineBuilding('Version C', 30, 0, 'pricing')).toBe('● Version C running · 30 s');
    expect(runLineBuilding('Geneva 3 km v2', 252, 2)).toBe(
      '● Geneva 3 km v2 building · 4 min 12 s · 2 queued',
    );
    expect(runLineSilent('Geneva 3 km v2')).toBe('● Geneva 3 km v2 · the runner is not answering');
    expect(runLineReady('Geneva 3 km v2')).toBe('✓ Geneva 3 km v2: ready');
    expect(NO_RUN).toBe('No run in progress');
    expect(PRICING_VERSIONS_OFF).toBe('Available when the instance is built.');
  });

  it('names the subject of a run as the menu writes it', () => {
    const entries = [
      {
        id: 'geneva-3km',
        name: 'Geneva 3 km',
        datasetId: 'd',
        versions: [
          {
            id: 'geneva-3km.v2',
            number: 2,
            status: 'sealed' as const,
            state: 'building',
            pricingVersionCount: 0,
          },
        ],
      },
    ];
    const subject = (type: 'instance_version' | 'pricing_version', id: string) => ({
      subject: { type, id },
    });

    expect(subjectName(subject('instance_version', 'geneva-3km.v2'), entries)).toBe(
      'Geneva 3 km v2',
    );
    expect(subjectName(subject('instance_version', 'other.v1'), entries)).toBe('other.v1');
    expect(subjectName(subject('pricing_version', 'pv-1'), entries)).toBe('pv-1');
  });
});
