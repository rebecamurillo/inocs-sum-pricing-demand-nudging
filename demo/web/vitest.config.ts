import { defineConfig } from 'vitest/config';

const threshold = { lines: 90, functions: 90, branches: 90, statements: 90 };

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    setupFiles: ['./vitest.setup.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/domain/**/*.ts', 'src/application/**/*.ts'],
      exclude: ['**/*.test.ts'],
      thresholds: {
        'src/domain/**': threshold,
        'src/application/**': threshold,
      },
    },
  },
});
