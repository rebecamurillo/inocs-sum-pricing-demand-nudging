import { describe, expect, it } from 'vitest';
import { MODES, periodTravellers, sumModes, type SimulationOutcome } from './pricing-result';

const simulation: SimulationOutcome = {
  ruleId: 'balanced-score',
  ruleVersion: 1,
  ruleCurrent: true,
  ruleParameters: { price_weight: 0.5, time_weight: 0.5 },
  travellers: { car: 30, ptOnly: 50, ptBike: 18 },
  bikeRides: { value: 18, unit: 'bike_rides', source: 'simulation', group: 'headline' },
  revenue: { value: 20, unit: 'chf', source: 'simulation', group: 'headline' },
  cost: { value: 10, unit: 'chf', source: 'simulation', group: 'headline' },
  displaced: 4,
  unserved: 2,
  createdAt: '2026-11-10T09:00:00Z',
};

describe('the modes', () => {
  it('come in the fixed order with their colours and a distinct icon', () => {
    expect(MODES.map((mode) => [mode.key, mode.label, mode.colour])).toEqual([
      ['car', 'Car', '#eb6834'],
      ['ptOnly', 'Public transport', '#2a78d6'],
      ['ptBike', 'Public transport + shared bike', '#1baf7a'],
    ]);
    expect(new Set(MODES.map((mode) => mode.icon)).size).toBe(3);
  });
});

describe('the period travellers', () => {
  it('are the three modes plus those left with no option', () => {
    expect(sumModes(simulation.travellers)).toBe(98);
    expect(periodTravellers(simulation)).toBe(100);
  });
});
