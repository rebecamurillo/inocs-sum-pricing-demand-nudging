import { test as base } from '@playwright/test';
import { TestControl } from './test-control';

export { expect } from '@playwright/test';

export const test = base.extend<{ control: TestControl }>({
  // Applied to every test: the fakes start each scenario in their default state.
  control: [
    async ({ request }, use) => {
      const control = new TestControl(request);
      await control.reset();
      await use(control);
    },
    { auto: true },
  ],
});
