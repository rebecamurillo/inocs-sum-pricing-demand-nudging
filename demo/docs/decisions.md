# Decisions — the dynamic pricing demonstrator

Technical decisions that shape `demo/`, newest last. An entry is never rewritten: a change
of mind is a new entry that names the one it replaces.

## D-1 — Two applications in one folder, each in clean architecture (2026-11-25)

- **Decision:** `api/` (Python, FastAPI) and `web/` (Astro static build with React islands,
  TypeScript) live side by side under `demo/`, both organised as domain, application,
  infrastructure and a delivery layer, with the dependency rule enforced by `import-linter`
  and ESLint boundaries in the quality gate.
- **Why:** the app sits next to the model it runs; the back end must be Python to call the
  package; the two existing SUM demonstrators are Astro and React. Agents build most of the
  code, so the layer rules are checked by tools and not left to review.

## D-2 — The model is reached through ports, with a fake for every test (2026-11-25)

- **Decision:** only `infrastructure/pricing_model/` imports the package. A deterministic
  fake implements the same ports and passes the same contract tests; tests and the e2e stack
  use it.
- **Why:** the model is used unmodified, a run needs a Gurobi licence and a trip planner and
  can take minutes to hours. Tests must run anywhere, in seconds, with the same result.

## D-3 — PostgreSQL in a container (2026-11-25)

- **Decision:** storage is PostgreSQL, started by Docker Compose, accessed through
  SQLAlchemy 2 repositories behind ports, with Alembic migrations.
- **Why:** the maintainer's choice: a real database server from the first day, close to a
  hosted set-up.
- **Consequence:** tests that need the database (integration, end-to-end) need Docker. The
  quality gate `make check` therefore stops at unit and contract tests with fakes;
  `make e2e` is a second, separate gate.

## D-4 — Same origin, generated contract (2026-11-25)

- **Decision:** the web app calls `/api` on its own origin (dev proxy, nginx in Docker).
  `contracts/openapi.json` is generated from the API, the web's types are generated from it,
  and the gate fails when either is stale.
- **Why:** no CORS configuration to get wrong, and the two applications cannot drift apart
  unnoticed.

## D-5 — One end-to-end suite, against Docker Compose, with a test-control API (2026-11-25)

- **Decision:** Playwright runs from the host against `compose.e2e.yaml` (PostgreSQL, API
  with fakes, web). The API exposes `/api/test-control` only with the fake adapters, to
  reset data and to set what the fakes answer.
- **Why:** acceptance needs scenarios such as "the trip planner stops before a run"; they
  must be reproducible without the real services, and through the real browser, API and
  database rather than by stubbing the network.

## D-6 — `uv` and Python 3.13, npm and Node 22 (2026-11-25)

- **Decision:** the API is managed by `uv` with a committed lockfile on Python 3.13; the web
  app and the e2e suite use npm with committed lockfiles on Node 22.
- **Why:** the package needs Python 3.10 or later and `gurobipy` publishes wheels for 3.13;
  the two other SUM repositories use npm and Node 22.

## D-7 — What the independent review changed (2026-11-25)

- **Decision:** after a review of the skeleton by an engineer who did not write it, the
  rules the documents state are backed by a check wherever one is cheap: files outside the
  web's six folders and network globals outside `infrastructure` fail the lint; the API's
  delivery layer has an import allowlist; a skipped test fails the gate; every error class
  must be mapped; integration tests refuse to run on the application's database; the e2e
  reset empties the database; CI runs the integration tests.
- **Why:** agents write most of the code and copy what they find. A rule that only a
  document states is broken by the fiftieth copy.

## Known debt

Accepted for a tool that runs on one machine; each must be settled before any hosting.

- Base images use moving tags (`python:3.13-slim`, `node:22-alpine`, `postgres:17`, nginx
  `stable-alpine`), and nothing proposes dependency updates.
- The database credentials are defaults committed in the settings and the Compose files.
- `/api/docs` is served in every mode.
- The e2e test seam is enabled by the single setting `PRICING_DEMO_ADAPTERS=fake` and has no
  authentication. A hosted set-up needs a second, explicit switch.
- The Compose services have no restart policy; nginx sets no cache headers for the built
  assets.
- Node 22 reaches its end of life on 2027-04-30.
- `web/` is pinned to Astro 7.4.1, which `npm audit` reports for two moderate advisories
  (GHSA-mh32-jxcr-mh9f, GHSA-r3h5-4585-7x3w). Neither is reachable here: no template builds
  a tag name from input, and the build is static with no `@astrojs/node`. Every fixed Astro
  needs Node 22.23.4 or later; on such a machine, run `npm --prefix web audit fix` and raise
  `engines.node` and `.nvmrc`.
- `web/` lints with ESLint 9, which is no longer supported upstream: `eslint-plugin-jsx-a11y`
  does not accept ESLint 10 yet. `e2e/` is on ESLint 10. Move `web/` when the plugin allows.
- Playwright's global `timeout` in `e2e/playwright.config.ts` is not protected by a check;
  raising it is covered by rule 4 of `AGENTS.md` only.
- CI does not lint the Dockerfiles, the Compose files or the workflow itself.
- The package is installed in editable mode, which writes an `egg-info` folder inside
  `sum_nsm_dynamic_pricing/src/`. Git ignores it, so the "model unmodified" check holds.

## Open, for the initiative's architecture step

- How long runs are queued and executed so that they outlive a request and a restart.
- How the solver's licence reaches the API: a named-user academic licence does not work
  inside a container, which may mean running the API on the host (`make dev`) for live runs.
- How the system status tells a full licence from the size-limited one that `gurobipy`
  ships with (`model-notes.md` entry 8). The skeleton's solver probe reports "available" as
  soon as an environment starts.
- The data model of city instances, pricing versions, results and periods.
- The map and its basemap.
