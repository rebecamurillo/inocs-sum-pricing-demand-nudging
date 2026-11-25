import { expect, test } from '../support/fixtures';

const components = ['Storage', 'Pricing model', 'Solver', 'Trip planner'];

test.describe('System status', () => {
  test('every component available: all four rows read available and new runs can start', async ({
    page,
  }) => {
    await page.goto('/');

    for (const component of components) {
      await expect(page.getByRole('listitem').filter({ hasText: component })).toContainText(
        'Available',
      );
    }
    await expect(page.getByText('New runs can start.')).toBeVisible();
  });

  test('NFR-2 · an unavailable trip planner is shown with its reason and refuses new runs', async ({
    page,
    control,
  }) => {
    const reason = 'No answer from http://otp:8080/otp/gtfs/v1 within 2 s.';
    await control.makeUnavailable('trip_planner', reason);

    await page.goto('/');

    // The row names the component alone; the blocking list below it reads "Trip planner: …".
    const tripPlanner = page
      .getByRole('listitem')
      .filter({ has: page.getByText('Trip planner', { exact: true }) });
    await expect(tripPlanner).toContainText('Unavailable');
    await expect(tripPlanner).toContainText(reason);
    await expect(page.getByText('New runs cannot start:')).toBeVisible();
    await expect(page.getByText(`Trip planner: ${reason}`)).toBeVisible();
    await expect(page.getByText('trip_planner')).toBeHidden();
    await expect(page.getByText('New runs can start.')).toBeHidden();
  });
});
