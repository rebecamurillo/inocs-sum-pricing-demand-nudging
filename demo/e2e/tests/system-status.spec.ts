import type { Page } from '@playwright/test';
import { expect, test } from '../support/fixtures';

const components = ['Storage', 'Runner', 'Solver', 'Pricing package', 'Trip planner'];

function row(page: Page, label: string) {
  return page.getByRole('listitem').filter({ has: page.getByText(label, { exact: true }) });
}

test.describe('System status', () => {
  test('every component available: all five components read available and builds, pricing runs and simulations can start', async ({
    page,
  }) => {
    await page.goto('/');

    for (const component of components) {
      await expect(row(page, component)).toContainText('Available');
    }
    await expect(page.getByText('Instance builds can start.')).toBeVisible();
    await expect(page.getByText('Pricing runs can start.')).toBeVisible();
    await expect(page.getByText('Simulations can start.')).toBeVisible();
  });

  test('NFR-2 · an unavailable trip planner is shown with its reason and refuses builds only', async ({
    page,
    control,
  }) => {
    const reason = 'No answer from http://otp:8080/otp/gtfs/v1 within 2 s.';
    await control.makeUnavailable('trip_planner', reason);

    await page.goto('/');

    // The row names the component alone; the verdict list reads "Trip planner: …".
    const tripPlanner = row(page, 'Trip planner');
    await expect(tripPlanner).toContainText('Unavailable');
    await expect(tripPlanner).toContainText(reason);
    await expect(page.getByText('Instance builds cannot start:')).toBeVisible();
    await expect(page.getByText(`Trip planner: ${reason}`)).toBeVisible();
    await expect(page.getByText('trip_planner')).toBeHidden();
    await expect(page.getByText('Instance builds can start.')).toBeHidden();
    await expect(page.getByText('Pricing runs can start.')).toBeVisible();
    await expect(page.getByText('Simulations can start.')).toBeVisible();
  });

  test('NFR-2 · with the solver limited, pricing runs are refused with its reason; builds and simulations are not', async ({
    page,
    control,
  }) => {
    const reason = 'Size-limited Gurobi licence: a model of 2001 variables is refused.';
    await control.makeLimited('solver', reason);

    await page.goto('/');

    const solver = row(page, 'Solver');
    await expect(solver).toContainText('Limited');
    await expect(solver).toContainText(reason);
    await expect(page.getByText('Pricing runs cannot start:')).toBeVisible();
    await expect(page.getByText(`Solver: ${reason}`)).toBeVisible();
    await expect(page.getByText('Pricing runs can start.')).toBeHidden();
    await expect(page.getByText('Instance builds can start.')).toBeVisible();
    await expect(page.getByText('Simulations can start.')).toBeVisible();
  });
});
