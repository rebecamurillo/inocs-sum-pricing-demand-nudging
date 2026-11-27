import { ApiProblemError } from '../../application/errors';
import type { PricingGateway, PricingRunQueued } from '../../application/ports/pricing-gateway';
import {
  GOAL_NAMES,
  HEADLINE_NAMES,
  type GoalComparison,
  type GoalName,
  type HeadlineName,
  type HubPairResult,
  type HubResult,
  type ModeCounts,
  type OptionResult,
  type PricingResult,
  type ResultNumber,
  type SimulationOutcome,
} from '../../domain/pricing-result';
import {
  PRICING_GOAL_NAMES,
  type PricingChanges,
  type PricingGoals,
  type PricingVersion,
} from '../../domain/pricing-version';
import type { components } from './generated/schema';

type Schemas = components['schemas'];

const apiRoot = '/api/v1';

function toGoals(wire: Schemas['PricingGoalsResource']): PricingGoals {
  return Object.fromEntries(PRICING_GOAL_NAMES.map((name) => [name, wire[name]])) as PricingGoals;
}

function toVersion(wire: Schemas['PricingVersionResource']): PricingVersion {
  return {
    id: wire.id,
    instanceVersionId: wire.instance_version_id,
    letter: wire.letter,
    name: wire.name,
    status: wire.status,
    state: wire.state,
    basedOnId: wire.based_on_id,
    runId: wire.run_id,
    keptFrom:
      wire.kept_from === null ? null : { id: wire.kept_from.id, letter: wire.kept_from.letter },
    goals: toGoals(wire.goals),
    rules: wire.rules.map((rule) => ({
      rule: rule.rule,
      field: rule.field,
      passed: rule.passed,
      message: rule.message,
    })),
    lastDurationS: wire.last_duration_s,
  };
}

function toNumber(wire: Schemas['NumberResource']): ResultNumber {
  return { value: wire.value, unit: wire.unit, source: wire.source, group: wire.group };
}

const optional = (wire: Schemas['NumberResource'] | null | undefined): ResultNumber | null =>
  wire === null || wire === undefined ? null : toNumber(wire);

/** The three modes by their wire names; null when one is absent (a missing key is never 0). */
function modes(
  wire: Readonly<Record<string, Schemas['NumberResource']>>,
  key: (mode: string) => string,
): ModeCounts | null {
  const car = wire[key('car')];
  const ptOnly = wire[key('pt_only')];
  const ptBike = wire[key('pt_bike')];
  if (car === undefined || ptOnly === undefined || ptBike === undefined) return null;
  return { car: car.value, ptOnly: ptOnly.value, ptBike: ptBike.value };
}

function toSimulation(wire: Schemas['SimulationResultResource']): SimulationOutcome {
  return {
    ruleId: wire.rule_id,
    ruleVersion: wire.rule_version,
    ruleCurrent: wire.rule_current,
    travellers: modes(wire.travellers, (mode) => mode) ?? { car: 0, ptOnly: 0, ptBike: 0 },
    displaced: wire.displaced.value,
    unserved: wire.unserved.value,
  };
}

function toResult(wire: Schemas['PricingResultResponse']): PricingResult {
  const simulation = (scheme: 'model_prices' | 'flat') => {
    const found = wire.simulations.find((item) => item.price_scheme === scheme);
    if (found === undefined) throw new Error(`The result has no simulation with ${scheme}.`);
    return toSimulation(found);
  };
  const empty: GoalComparison = { model: null, modelPrices: null, flat: null, change: null };
  const goals = Object.fromEntries(
    GOAL_NAMES.map((name) => {
      const found = wire.goals.find((item) => item.name === name);
      return [
        name,
        found === undefined
          ? empty
          : {
              model: optional(found.model),
              modelPrices: optional(found.model_prices),
              flat: optional(found.flat),
              change: optional(found.change),
            },
      ];
    }),
  ) as Record<GoalName, GoalComparison>;
  const headline = Object.fromEntries(
    HEADLINE_NAMES.flatMap((name) => {
      const found = wire.headline[name];
      return found === undefined ? [] : [[name, toNumber(found)]];
    }),
  ) as Partial<Record<HeadlineName, ResultNumber>>;
  return {
    pricingVersionId: wire.pricing_version_id,
    periodId: wire.period_id,
    simulations: { modelPrices: simulation('model_prices'), flat: simulation('flat') },
    modelSplit: modes(wire.model_split, (mode) => `travellers_${mode}`),
    goals,
    headline,
  };
}

function toOption(wire: Schemas['OptionResultResource']): OptionResult {
  return {
    arcId: wire.arc_id,
    mode: wire.mode,
    legs: wire.legs.map((leg) => ({
      mode: leg.mode,
      line: leg.line ?? null,
      fromPlace: leg.from_place ?? null,
      toPlace: leg.to_place ?? null,
      durationS: leg.duration_s,
    })),
    duration: toNumber(wire.duration),
    bikeLegs: optional(wire.bike_legs),
    bikePrice: optional(wire.bike_price),
    riders: optional(wire.riders),
  };
}

function toHubPair(wire: Schemas['HubPairResultResource']): HubPairResult {
  return {
    originHub: wire.origin_hub,
    destinationHub: wire.destination_hub,
    meanBikePrice: optional(wire.mean_bike_price),
    minBikePrice: optional(wire.min_bike_price),
    maxBikePrice: optional(wire.max_bike_price),
    travellers: modes(wire.travellers, (mode) => mode) ?? { car: 0, ptOnly: 0, ptBike: 0 },
    options: wire.options.map(toOption),
  };
}

function toHub(wire: Schemas['HubResultResource']): HubResult {
  return {
    hubId: wire.hub_id,
    label: wire.label,
    lat: wire.lat,
    lon: wire.lon,
    ridesStarting: toNumber(wire.rides_starting),
    ridesEnding: toNumber(wire.rides_ending),
    meanBikePrice: optional(wire.mean_bike_price),
  };
}

function problemOf(body: unknown): Schemas['ProblemDetails'] | null {
  if (typeof body !== 'object' || body === null) return null;
  const candidate = body as Partial<Schemas['ProblemDetails']>;
  return typeof candidate.code === 'string' && typeof candidate.detail === 'string'
    ? (candidate as Schemas['ProblemDetails'])
    : null;
}

function unexpected(status: number, body: unknown, path: string): ApiProblemError {
  const problem = problemOf(body);
  if (problem !== null && typeof problem.title === 'string') return new ApiProblemError(problem);
  return new ApiProblemError({
    code: 'unexpected_response',
    title: `The API answered with status ${String(status)}`,
    detail: `${path} could not be read or written.`,
  });
}

export class HttpPricingGateway implements PricingGateway {
  private readonly fetchImpl: typeof fetch;

  constructor(fetchImpl: typeof fetch) {
    this.fetchImpl = fetchImpl;
  }

  async list(instanceVersionId: string): Promise<PricingVersion[]> {
    const path = `${apiRoot}/instance-versions/${encodeURIComponent(instanceVersionId)}/pricing-versions`;
    const answer = await this.call('GET', path, undefined);
    if (answer.status !== 200) throw unexpected(answer.status, answer.body, path);
    return (answer.body as Schemas['PricingVersionList']).items.map(toVersion);
  }

  async get(id: string): Promise<PricingVersion | null> {
    const path = `${apiRoot}/pricing-versions/${encodeURIComponent(id)}`;
    const answer = await this.call('GET', path, undefined);
    if (answer.status === 404) return null;
    if (answer.status !== 200) throw unexpected(answer.status, answer.body, path);
    return toVersion(answer.body as Schemas['PricingVersionResource']);
  }

  async result(id: string): Promise<PricingResult | null> {
    const path = `${apiRoot}/pricing-versions/${encodeURIComponent(id)}/result`;
    const answer = await this.call('GET', path, undefined);
    if (answer.status === 404) return null;
    if (answer.status !== 200) throw unexpected(answer.status, answer.body, path);
    return toResult(answer.body as Schemas['PricingResultResponse']);
  }

  async hubPairResults(id: string): Promise<HubPairResult[] | null> {
    const path = `${apiRoot}/pricing-versions/${encodeURIComponent(id)}/hub-pair-results`;
    const answer = await this.call('GET', path, undefined);
    if (answer.status === 404) return null;
    if (answer.status !== 200) throw unexpected(answer.status, answer.body, path);
    return (answer.body as Schemas['HubPairResultList']).items.map(toHubPair);
  }

  async hubResults(id: string): Promise<HubResult[] | null> {
    const path = `${apiRoot}/pricing-versions/${encodeURIComponent(id)}/hub-results`;
    const answer = await this.call('GET', path, undefined);
    if (answer.status === 404) return null;
    if (answer.status !== 200) throw unexpected(answer.status, answer.body, path);
    return (answer.body as Schemas['HubResultList']).items.map(toHub);
  }

  async create(instanceVersionId: string, basedOn?: string): Promise<PricingVersion> {
    const path = `${apiRoot}/instance-versions/${encodeURIComponent(instanceVersionId)}/pricing-versions`;
    const answer = await this.call(
      'POST',
      path,
      basedOn === undefined ? {} : { based_on: basedOn },
    );
    if (answer.status !== 201) throw unexpected(answer.status, answer.body, path);
    return toVersion(answer.body as Schemas['PricingVersionResource']);
  }

  async patch(id: string, changes: PricingChanges): Promise<PricingVersion> {
    const path = `${apiRoot}/pricing-versions/${encodeURIComponent(id)}`;
    const answer = await this.call('PATCH', path, changes);
    if (answer.status !== 200) throw unexpected(answer.status, answer.body, path);
    return toVersion(answer.body as Schemas['PricingVersionResource']);
  }

  async discard(id: string): Promise<void> {
    const path = `${apiRoot}/pricing-versions/${encodeURIComponent(id)}`;
    const answer = await this.call('DELETE', path, undefined);
    if (answer.status !== 204) throw unexpected(answer.status, answer.body, path);
  }

  async run(id: string): Promise<PricingRunQueued> {
    const path = `${apiRoot}/pricing-versions/${encodeURIComponent(id)}/runs`;
    const answer = await this.call('POST', path, undefined);
    if (answer.status === 202) {
      return { kind: 'queued', runId: (answer.body as Schemas['RunResource']).id };
    }
    const problem = problemOf(answer.body);
    if ((answer.status === 409 || answer.status === 503) && problem !== null) {
      return { kind: 'refused', detail: problem.detail };
    }
    throw unexpected(answer.status, answer.body, path);
  }

  /** Every status comes back; only an unreachable API throws. */
  private async call(
    method: string,
    path: string,
    body: unknown,
  ): Promise<{ status: number; body: unknown }> {
    let response: Response;
    try {
      response = await this.fetchImpl(path, {
        method,
        headers:
          body === undefined
            ? { Accept: 'application/json' }
            : { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (cause) {
      throw new ApiProblemError({
        code: 'api_unreachable',
        title: 'The API could not be reached',
        detail: cause instanceof Error ? cause.message : String(cause),
      });
    }
    let parsed: unknown;
    try {
      parsed = (await response.json()) as unknown;
    } catch {
      parsed = undefined;
    }
    return { status: response.status, body: parsed };
  }
}
