import { describe, expect, it } from 'vitest';
import {
  blockingComponents,
  componentLabel,
  type ComponentName,
  type ComponentStatus,
  type SystemStatus,
} from './system-status';

describe('componentLabel', () => {
  it.each<[ComponentName, string]>([
    ['storage', 'Storage'],
    ['pricingModel', 'Pricing model'],
    ['solver', 'Solver'],
    ['tripPlanner', 'Trip planner'],
  ])('names %s in plain English', (name, label) => {
    expect(componentLabel(name)).toBe(label);
  });
});

const available = (name: ComponentName): ComponentStatus => ({
  name,
  available: true,
  reason: null,
});
const unavailable = (name: ComponentName, reason: string): ComponentStatus => ({
  name,
  available: false,
  reason,
});

function statusOf(components: readonly ComponentStatus[]): SystemStatus {
  return {
    apiVersion: '0.1.0',
    components,
    canReadStoredResults: true,
    canStartRuns: components.every((component) => component.available),
  };
}

describe('blockingComponents', () => {
  it('is empty when every component is available', () => {
    const status = statusOf([available('storage'), available('solver')]);

    expect(blockingComponents(status)).toEqual([]);
  });

  it('lists the unavailable components with their reasons, in report order', () => {
    const status = statusOf([
      available('storage'),
      unavailable('pricingModel', 'Not installed.'),
      available('solver'),
      unavailable('tripPlanner', 'No answer.'),
    ]);

    expect(blockingComponents(status)).toEqual([
      unavailable('pricingModel', 'Not installed.'),
      unavailable('tripPlanner', 'No answer.'),
    ]);
  });
});
