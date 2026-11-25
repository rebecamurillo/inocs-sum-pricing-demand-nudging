import js from '@eslint/js';
import boundaries from 'eslint-plugin-boundaries';
import astro from 'eslint-plugin-astro';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

const source = ['src/**/*.{ts,tsx,astro}'];

// The allowed-imports table of docs/architecture.md § Web, one policy per row.
// Anything not allowed below is an error; the rule is never switched off or loosened.
const layerPolicies = [
  { from: 'domain', to: ['domain'] },
  { from: 'application', to: ['application', 'domain'] },
  { from: 'infrastructure', to: ['infrastructure', 'application', 'domain'] },
  { from: 'presentation', to: ['presentation', 'application', 'domain'] },
  {
    from: 'composition',
    to: ['composition', 'pages', 'presentation', 'infrastructure', 'application', 'domain'],
  },
  { from: 'pages', to: ['pages', 'presentation', 'composition'] },
].map(({ from, to }) => ({
  from: { element: { type: from } },
  allow: { to: { element: { types: to } } },
}));

// Network access belongs to the adapters in infrastructure/; the browser's own objects are
// not available to the domain and the application, which must run anywhere.
const networkGlobals = ['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource'];
const browserGlobals = ['window', 'document', 'navigator', 'localStorage', 'sessionStorage'];

const networkMessage = 'is used only in src/infrastructure';
const browserMessage = 'is a browser object, not available to domain and application';

const asGlobals = (names, reason) => names.map((name) => ({ name, message: `${name} ${reason}.` }));
// `window.fetch` is the same object as `fetch`: close the way round the rule above.
const asProperties = (names, reason) =>
  ['window', 'globalThis', 'self'].flatMap((object) =>
    names.map((property) => ({ object, property, message: `${property} ${reason}.` })),
  );

// Vitest files: a test that is focused, skipped or a to-do does not run with the rest.
const notRunTests = [
  {
    selector: 'MemberExpression[property.name=/^(only|skip|skipIf|runIf|todo|fails)$/]',
    message: 'A focused, skipped or to-do test is not allowed (AGENTS.md rule 4).',
  },
  {
    selector: 'Identifier[name=/^(xit|xtest|xdescribe|fit|fdescribe)$/]',
    message: 'A focused or disabled test is not allowed (AGENTS.md rule 4).',
  },
];

export default tseslint.config(
  { ignores: ['dist', 'coverage', '.astro', 'node_modules', 'src/infrastructure/api/generated'] },

  js.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    extends: [tseslint.configs.strictTypeChecked, tseslint.configs.stylisticTypeChecked],
    languageOptions: { parserOptions: { projectService: true } },
  },
  {
    files: ['**/*.{js,mjs}'],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: { globals: globals.node },
  },
  astro.configs['flat/recommended'],
  astro.configs['flat/jsx-a11y-recommended'],
  {
    files: ['**/*.tsx'],
    plugins: { 'jsx-a11y': jsxA11y },
    rules: jsxA11y.flatConfigs.recommended.rules,
  },
  {
    files: ['**/*.{ts,tsx}'],
    ...reactHooks.configs.flat.recommended,
  },

  {
    files: source,
    plugins: { boundaries },
    settings: {
      'import/resolver': { typescript: { alwaysTryTypes: true } },
      'boundaries/elements': [
        { type: 'domain', pattern: 'src/domain' },
        { type: 'application', pattern: 'src/application' },
        { type: 'infrastructure', pattern: 'src/infrastructure' },
        { type: 'presentation', pattern: 'src/presentation' },
        { type: 'composition', pattern: 'src/composition' },
        { type: 'pages', pattern: 'src/pages' },
      ],
      'boundaries/files': [{ pattern: '**/*.test.{ts,tsx}', category: 'test' }],
      'boundaries/ignore': ['src/env.d.ts'],
    },
    rules: {
      // A file outside the six folders, or an import of one, has no row in the table above.
      'boundaries/no-unknown-files': 'error',
      'boundaries/no-unknown-dependencies': 'error',
      'boundaries/dependencies': [
        'error',
        {
          default: 'disallow',
          checkAllOrigins: true,
          policies: [
            ...layerPolicies,
            // Third-party packages: domain and application import none (never react).
            {
              from: {
                element: { types: ['infrastructure', 'presentation', 'composition', 'pages'] },
              },
              allow: { to: { module: { origin: 'external' } } },
            },
            // Test files may use the test libraries wherever they sit.
            {
              from: { file: { categories: 'test' } },
              allow: {
                to: { module: { origin: 'external', source: ['vitest', '@testing-library/*'] } },
              },
            },
          ],
        },
      ],
    },
  },

  {
    files: source,
    ignores: ['src/infrastructure/**'],
    rules: {
      'no-restricted-globals': ['error', ...asGlobals(networkGlobals, networkMessage)],
      'no-restricted-properties': ['error', ...asProperties(networkGlobals, networkMessage)],
    },
  },
  {
    files: ['src/domain/**', 'src/application/**'],
    rules: {
      'no-restricted-globals': [
        'error',
        ...asGlobals(networkGlobals, networkMessage),
        ...asGlobals(browserGlobals, browserMessage),
      ],
      'no-restricted-properties': [
        'error',
        ...asProperties(networkGlobals, networkMessage),
        ...asProperties(browserGlobals, browserMessage),
      ],
    },
  },

  {
    files: ['src/**/*.test.{ts,tsx}'],
    rules: { 'no-restricted-syntax': ['error', ...notRunTests] },
  },
);
