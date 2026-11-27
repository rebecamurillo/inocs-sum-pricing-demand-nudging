import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  sampleHubPairResults,
  samplePricingResult,
  sampleStoredSimulations,
} from '../../application/ports/fake-pricing-gateway';
import type { PricingResult } from '../../domain/pricing-result';
import { ResultAdvanced } from './ResultAdvanced';

function mount(
  result: PricingResult = samplePricingResult(),
  stored = sampleStoredSimulations(),
  hubPairs: ReturnType<typeof sampleHubPairResults> | null = sampleHubPairResults(),
) {
  return render(
    <ResultAdvanced
      result={result}
      flatPrice={1}
      hubPairs={1412}
      hubPairResults={hubPairs}
      stored={stored}
    />,
  );
}

const group = (name: string | RegExp) => {
  const heading = screen.getByRole('heading', { name });
  const section = heading.closest('section');
  if (section === null) throw new Error('No group around the heading.');
  return within(section);
};

describe('ResultAdvanced', () => {
  it('holds the seven groups in order under one heading', () => {
    mount();

    expect(screen.getByRole('heading', { level: 2, name: 'Advanced view' })).toBeTruthy();
    expect(screen.getAllByRole('heading', { level: 3 }).map((item) => item.textContent)).toEqual([
      'What the solver maximised',
      'Solver',
      'Traveller simulation',
      "The package's own summary (optimizer/metrics.py)",
      'Parameters used',
      'Choice-model coefficients',
      'About this result',
    ]);
  });

  it('lists the objective terms, the label and the tagged value', () => {
    mount();

    const objective = group('What the solver maximised');
    expect(objective.getByText('Ridership term')).toBeTruthy();
    expect(objective.getByText('+ Station balance term')).toBeTruthy();
    expect(objective.getByText("computed from the model's flows")).toBeTruthy();
    const value = objective.getByRole('rowheader', { name: /= Objective value/ }).closest('tr');
    expect(value?.textContent).toContain("PRICING MODEL'S RESULT");
    expect(value?.textContent).toContain('23 456');
  });

  it('keeps only the objective value when the terms are absent', () => {
    const base = samplePricingResult();
    const numbers = Object.fromEntries(
      Object.entries(base.advanced.numbers).filter(([name]) => !name.startsWith('objective_term')),
    );
    mount(samplePricingResult({ advanced: { ...base.advanced, numbers } }));

    const objective = group('What the solver maximised');
    expect(objective.queryByText('Ridership term')).toBeNull();
    expect(objective.queryByText("computed from the model's flows")).toBeNull();
    expect(objective.getByText('= Objective value')).toBeTruthy();
  });

  it('shows the solver numbers under the blue tag, without a flat-price column', () => {
    mount();

    const solver = group('Solver');
    expect(solver.getByText("PRICING MODEL'S RESULT")).toBeTruthy();
    expect(solver.getByText('12.3 s')).toBeTruthy();
    expect(solver.getByText('0.50 %')).toBeTruthy();
    expect(solver.getByText('optimal')).toBeTruthy();
    expect(solver.getByText('1 412 · 4')).toBeTruthy();
    expect(solver.getByText('no')).toBeTruthy();
    expect(solver.queryByText(/flat/i)).toBeNull();
  });

  it('shows the simulation rule under the grey tag and no earlier simulations when there are none', () => {
    mount();

    const simulation = group('Traveller simulation');
    expect(simulation.getByText('SIMULATION')).toBeTruthy();
    expect(
      simulation.getByText(
        'Rule: balanced-score v1 · price weight 0.5 · time weight 0.5 · placeholder',
      ),
    ).toBeTruthy();
    expect(simulation.getByText('12 000 / 11 000')).toBeTruthy();
    expect(
      simulation.getByText(
        'A bike ride is one bike leg; an option with two bike legs counts two rides',
      ),
    ).toBeTruthy();
    expect(screen.queryByText('Earlier simulations of this version')).toBeNull();
  });

  it('lists the earlier simulations when a stored one has an earlier rule', () => {
    mount(samplePricingResult(), sampleStoredSimulations(true));

    const simulation = group('Traveller simulation');
    expect(simulation.getByText('Earlier simulations of this version')).toBeTruthy();
    expect(
      simulation.getByText(
        'balanced-score v0 · price weight 1 · time weight 0 · placeholder · with these prices · 9 Nov 2026',
      ),
    ).toBeTruthy();
  });

  it("shows the package's two averages without a bracketed reference", () => {
    mount();

    const summary = group("The package's own summary (optimizer/metrics.py)");
    expect(summary.getByText('Avg Bike Price (Multimodal, Flow ≥ 1)')).toBeTruthy();
    expect(summary.getByText('0.94 CHF')).toBeTruthy();
    expect(summary.getByText('1.02 CHF')).toBeTruthy();
    expect(document.body.textContent).not.toContain('[Q-');
  });

  it('names the parameters in monospace and the flat price', () => {
    mount();

    const parameters = group('Parameters used');
    const name = parameters.getByText('cost_bike');
    expect(name.tagName).toBe('CODE');
    expect(parameters.getByText('P_bar')).toBeTruthy();
    expect(parameters.getByText('1.00 CHF per ride · traveller simulation only')).toBeTruthy();
  });

  it('lists the coefficients, "not found" for a null one', () => {
    mount();

    const coefficients = group('Choice-model coefficients');
    expect(
      coefficients.getByText(
        'Read from the package source (optimizer/solver.py), fixed inside the model',
      ),
    ).toBeTruthy();
    expect(coefficients.getByText('ASC_PT')).toBeTruthy();
    expect(coefficients.getByText('not found')).toBeTruthy();
  });

  it('says the coefficients are not exposed when the package source was not read', () => {
    mount(samplePricingResult({ coefficients: null }));

    const coefficients = group('Choice-model coefficients');
    expect(
      coefficients.getByText('Fixed inside the model, not exposed by the package.'),
    ).toBeTruthy();
    expect(coefficients.queryByRole('table')).toBeNull();
  });

  it('shows the provenance block', () => {
    mount();

    const about = group('About this result');
    expect(about.getByText('package 0.4.2 · commit 0123456')).toBeTruthy();
    expect(about.getByText('Gurobi 12.0.1 · full licence · status optimal')).toBeTruthy();
    expect(about.getByText('stables.donkey.bike · fetched 10 Nov 2026')).toBeTruthy();
    expect(about.getByText('0.1.0')).toBeTruthy();
  });

  it('shows a dash for the hub pair counts while the table is not read', () => {
    mount(samplePricingResult(), sampleStoredSimulations(), null);

    expect(group('Solver').getByText('—')).toBeTruthy();
  });

  it('never shows "time limit", whatever the solver status', () => {
    const base = samplePricingResult();
    mount(
      samplePricingResult({
        advanced: {
          solverStatusName: 'TIME_LIMIT',
          numbers: {
            ...base.advanced.numbers,
            time_limit_reached: { value: 1, unit: 'flag', source: 'model', group: 'advanced' },
          },
        },
      }),
    );

    expect(document.body.textContent).toContain('stopped with a solution');
    expect(document.body.textContent).toContain('yes');
    expect(document.body.textContent.toLowerCase()).not.toContain('time limit');
  });
});
