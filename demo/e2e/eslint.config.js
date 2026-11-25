import js from '@eslint/js';
import { defineConfig, globalIgnores } from 'eslint/config';
import playwright from 'eslint-plugin-playwright';
import tseslint from 'typescript-eslint';

export default defineConfig(
  globalIgnores(['node_modules', 'playwright-report', 'test-results']),

  js.configs.recommended,
  {
    files: ['**/*.ts'],
    extends: [tseslint.configs.strictTypeChecked, tseslint.configs.stylisticTypeChecked],
    languageOptions: { parserOptions: { projectService: true } },
  },
  {
    files: ['**/*.js'],
    extends: [tseslint.configs.disableTypeChecked],
  },

  // A scenario that is skipped, focused or waits a fixed time proves nothing (AGENTS.md rule 4
  // and docs/testing.md): the recommended rules, plus selectors that are not roles or text.
  {
    ...playwright.configs['flat/recommended'],
    files: ['tests/**/*.ts'],
    rules: {
      ...playwright.configs['flat/recommended'].rules,
      'playwright/no-skipped-test': ['error', { allowConditional: false }],
      'playwright/no-focused-test': 'error',
      'playwright/no-wait-for-timeout': 'error',
      'playwright/no-raw-locators': 'error',
      'playwright/expect-expect': 'error',
      // The plugin's no-skipped-test does not see fixme or fail, and slow raises the timeout.
      'no-restricted-syntax': [
        'error',
        {
          selector: 'MemberExpression[property.name=/^(fixme|fail|slow|setTimeout)$/]',
          message:
            'A fixme, expected-failure or lengthened test is not allowed (AGENTS.md rule 4).',
        },
      ],
    },
  },
);
