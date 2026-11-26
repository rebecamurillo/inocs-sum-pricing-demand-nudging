import { describe, expect, it } from 'vitest';
import {
  componentLabel,
  stateLabel,
  type ComponentName,
  type ComponentState,
} from './system-status';

describe('componentLabel', () => {
  it.each<[ComponentName, string]>([
    ['storage', 'Storage'],
    ['runner', 'Runner'],
    ['solver', 'Solver'],
    ['package', 'Pricing package'],
    ['tripPlanner', 'Trip planner'],
  ])('names %s in plain English', (name, label) => {
    expect(componentLabel(name)).toBe(label);
  });
});

describe('stateLabel', () => {
  it.each<[ComponentState, string]>([
    ['available', 'Available'],
    ['limited', 'Limited'],
    ['unavailable', 'Unavailable'],
  ])('names %s in plain English', (state, label) => {
    expect(stateLabel(state)).toBe(label);
  });
});
