# Architecture — the dynamic pricing demonstrator

How `demo/` is organised and why. `AGENTS.md` holds the rules; this file says where code
goes and what may import what. Decisions and their reasons are in
[`decisions.md`](decisions.md).

## The system

```
 browser ──► web (static files) ──► /api ──► api (FastAPI) ──► PostgreSQL ◄── worker ──┬──► pricing package (sum_nsm_dynamic_pricing, unmodified, Gurobi)
                                                                              │         └──► OpenTripPlanner (routes)
                                                                              └──► var/data (working directories, artefacts)
```

- The web app is a static build. It reaches the API on the same origin under `/api`: the dev
  server proxies it, and in Docker the web container's nginx does. There is no CORS set-up.
- The API touches only the database. The worker is the process that runs the package and
  reaches the trip planner: it claims queued runs from PostgreSQL, one at a time, and executes
  their steps ([D-12](decisions.md)). The API and the worker share only PostgreSQL, so the API
  starts and serves stored results with no licence, no trip planner and no package import.
- **The system status.** The API probes the database only and reads the worker's reports.
  Every `PRICING_DEMO_COMPONENT_REPORT_INTERVAL_S` (default 30 s), idle or while a run
  executes, the worker probes the solver (a 2 001-variable model, which tells a full Gurobi
  licence from the size-limited one), the pricing package and the trip planner, and upserts
  one row each into `component_reports`. The runner's state comes from
  `workers.heartbeat_at`: a runner, or a report of a worker, that did not beat for 30 s reads
  `unavailable`. `GET /api/v1/system-status` turns the six components (`storage`, `runner`,
  `solver`, `package`, `trip_planner`, `city_data`, each `available`, `limited` or `unavailable`) into
  three verdicts (instance builds, pricing runs, simulations) that carry their blocking
  reasons. `city_data` is the API's own: `unavailable` ("No city data is imported yet") while
  `city_datasets` is empty, and it blocks instance builds only; what each action needs is tabulated in the initiative's `ARCHITECTURE.md` § 10.1.
  The API process never imports the package (an architecture test checks it).
- The worker runs on the host for live runs (`make worker`, also started by `make dev`),
  because a named-user Gurobi licence does not work inside a container
  ([D-10](decisions.md)); in `make up` it is a container, and in the e2e stack a container
  with fake adapters. Its working files are under `var/data` (`PRICING_DEMO_DATA_DIR`).
- **Worker restart.** A worker that stops (Ctrl-C, a container restart, a crash, a kill)
  leaves its run `running`. Every worker looks for interrupted runs when it starts and again
  every 10 s of its loop (`RECOVERY_EVERY`, on the injected clock), idle or while it executes
  a run: a `running` run whose heartbeat is more than 60 s old is queued again once
  (`attempt` + 1, `queued_at` kept), failed with the code `interrupted` when it is found stale
  on its second attempt, and cancelled when a cancellation was requested. A pass never
  recovers the run its own worker has in hand (compared by run id). So a worker restarted
  within 60 s picks up its predecessor's run on a later pass, and a run abandoned after a
  failed end-of-step write (the worker logs the step and the error and polls again) is
  recovered the same way.
- `contracts/openapi.json` is generated from the API and the web's API types are generated
  from it, so a mismatch between the two is a build failure, not a runtime surprise.

## The four roles

Both applications use the same roles and the same direction of dependency: inwards.

| Role | Holds | Knows about |
| --- | --- | --- |
| **domain** | entities, value objects, rules, calculations, typed errors | nothing outside itself |
| **application** | use cases (one per intention) and the ports they need | domain |
| **infrastructure** | adapters that implement ports: database, package, trip planner, HTTP client | application, domain |
| **delivery** (`interface/http`, `presentation`) | routes, schemas, components: turns a request or a click into a use-case call | application, domain |
| **composition root** | builds adapters, injects them into use cases | everything |

How the SOLID principles show up here, as things a reviewer can check:

- **Single responsibility** — one use case per module; a route calls exactly one use case; a
  component renders and delegates.
- **Open/closed** — a new source of data is a new adapter of an existing port; behaviour is
  never switched by a flag inside a use case.
- **Liskov** — a fake and its real adapter pass the same contract test suite
  ([`testing.md`](testing.md) § Contract tests), so one can stand for the other.
- **Interface segregation** — a port holds only what its use cases call. Split a port before
  it grows a method only one caller needs.
- **Dependency inversion** — ports are declared in `application/`, implemented in
  `infrastructure/`, and chosen in the composition root. A use case never constructs an
  adapter.

## API (`api/`)

```
api/
  pyproject.toml  uv.lock  .python-version  alembic.ini  Dockerfile
  src/pricing_demo/
    domain/                    stdlib only; frozen dataclasses; no I/O
    application/
      ports/                   one Protocol per module
      use_cases/               one use case per module: a class with execute()
      step_registry.py         the executor of each step, filled by the worker's composition root
    infrastructure/
      config/                  settings read from the environment
      persistence/             engine, the shared metadata, repositories, component reports,
                               the fake settings, migrations/
      pricing_model/           the package gateway: the package and solver probes (worker only)
      trip_planner/            the OpenTripPlanner client
      fakes/                   every fake adapter, one module per kind
    interface/
      http/                    app factory, error mapping, schemas, the e2e test seam
        routers/               one module per feature: a factory that takes its use case
    bootstrap.py               composition root: adapters → use cases → routers → app
    asgi.py                    the ASGI entry point: create the app from bootstrap
    worker/                    the worker's entry point (pricing-demo-worker) and composition root
  tests/
    unit/                      domain and use cases, with fakes; mirrors src/
    contract/                  one suite per port, run against the fake and the real adapter
    integration/               adapters against a real PostgreSQL (marker: integration)
    live/                      the real package, solver and trip planner (marker: live)
    architecture/              tests of the rules a linter cannot express
```

### Allowed imports

| Package | May import | Never imports |
| --- | --- | --- |
| `domain` | the standard library | any other layer, any third-party package |
| `application` | `domain`, the standard library | `infrastructure`, `interface`, `fastapi`, `sqlalchemy`, `pydantic`, `httpx`, `sum_nsm_dynamic_pricing`, `gurobipy` |
| `infrastructure` | `application`, `domain`, its libraries | `interface` |
| `interface` | `application`, `domain`, `fastapi`, `pydantic` | `infrastructure`, `sqlalchemy`, `sum_nsm_dynamic_pricing` |
| `bootstrap`, `asgi`, `worker` | everything | — |

`sum_nsm_dynamic_pricing` and `gurobipy` are imported only inside
`infrastructure/pricing_model/`. These rules are `import-linter` contracts in
`pyproject.toml` and an allowlist test in `tests/architecture/`, run by `make check`.
Dynamic imports are refused outside that folder: `importlib.import_module` and
`builtins.__import__` by the linter, a bare `__import__(…)` by a test in
`tests/architecture/`. Only the architecture tests may call `import_module`, to walk the
layers.

### Routes and the composition root

A feature's router module exposes a factory that receives its use case and returns the
router. `bootstrap.py` builds the adapters, then the use cases, then the routers, and hands
them to the app factory; adding a feature adds lines there and never changes the app
factory. The app factory also takes a `lifespan`, through which the composition root
releases what the adapters hold (the database engine) at shutdown. Two kinds of route call no use case, and no other may: `GET /api/health`
(liveness, used by the container health checks; it touches nothing) and the e2e test seam
under `/api/test-control`, whose protocol belongs to the delivery layer because no use case
needs it.

### The model behind a port

The package is installed from `../sum_nsm_dynamic_pricing` as it is. The application sees it
only through ports. The adapter translates between the product's vocabulary and the
package's (`P_bar`, `theta`, file layouts), runs it, and turns what it writes into domain
objects. A fake adapter (in `infrastructure/fakes/`, like every fake) returns deterministic
data and is what every test and the e2e stack use; `PRICING_DEMO_ADAPTERS=fake|real` selects
the set in the composition root. Storage is the real PostgreSQL in both sets.

What the package cannot do as it stands is recorded in [`model-notes.md`](model-notes.md)
and worked around in the adapter, never in the package.

### City data

A city data set is one immutable row of `city_datasets` plus a folder
`{data_dir}/datasets/{id}/` (id `geneva-{import date}`, then `-2`, `-3`, ... on the same
day) holding the GTFS copy and one GBFS `station_information` snapshot, with their hashes,
the timetable's validity and time zone, the available area (the intersection of the stops'
bounding box and the OSM header's box), the preset and the provisional routing moment.
Two worker commands create data sets and nothing else does:
`pricing-demo-worker import-city-data` (`make city-data`; needs the one `.osm.pbf` in
`otp/data/`) and `pricing-demo-worker refresh-bike-stations` (the latest timetable and a new
snapshot). The station feed sits behind the `BikeStationFeed` port: the real adapter runs the
package's Donkey Republic provider in a child process, the fake copies a committed fixture.
The timetable and the street extract are read by `infrastructure/city_data/` (`zipfile` and
`csv` for GTFS, `osmium` for the PBF header). `GET /api/v1/city-datasets` lists the data sets.

### Persistence

PostgreSQL through SQLAlchemy 2 and psycopg 3. Repositories implement ports and return
domain objects; no ORM object leaves `infrastructure/persistence/`. Every table is declared
on the one `MetaData` of `persistence/metadata.py`, whose naming convention names every
constraint and index. The schema changes only through Alembic migrations, generated against
that metadata and applied at start-up by `make dev`, `make up` and the e2e stack.

## Web (`web/`)

```
web/
  package.json  astro.config.mjs  tsconfig.json  eslint.config.js  vitest.config.ts  Dockerfile  nginx.conf
  src/
    domain/                    types and pure functions: no React, no fetch, no window
    application/
      ports/                   interfaces the use cases need
      use-cases/               plain functions that take their ports as arguments
    infrastructure/
      api/                     HTTP adapters; generated/ holds the types from the contract
      storage/                 the browser-storage adapter of the layout preferences
    presentation/
      assets/  components/  hooks/  layouts/  styles/
    composition/               builds the adapters once; one island per page wraps its components in the provider
    pages/                     Astro routes: a layout and one island each
```

Unit tests sit beside the file they test (`thing.test.ts`).

### Allowed imports

| Folder | May import | Never imports |
| --- | --- | --- |
| `domain` | nothing | every other folder, `react`, browser globals |
| `application` | `domain` | `infrastructure`, `presentation`, `react` |
| `infrastructure` | `application`, `domain` | `presentation` |
| `presentation` | `application`, `domain` | `infrastructure` (adapters arrive through `composition`) |
| `composition` | everything | — |
| `pages` | `presentation`, `composition` | `infrastructure`, `application`, `domain` |

These rules are ESLint boundaries in `eslint.config.js`, run by `make check`. A source file
outside these six folders fails the lint. So does `fetch` (or any other network global)
outside `infrastructure`, and `window`, `document` or browser storage in `domain` and
`application`.

- The generated API types stay inside `infrastructure/api/`. An adapter maps a response to a
  domain type; a component never sees a wire type. The browser's `fetch` is called in one
  file, `infrastructure/api/browser-fetch.ts`; adapters receive it, so tests pass a fake.
- Components receive their gateways through a React context. The provider and its hook live
  in `presentation/hooks/` and are typed by the ports in `application/ports/`; `composition/`
  builds the real gateways and tests pass fakes through the same provider. React context
  does not cross Astro islands, so a page has one island, defined in `composition/`, that
  holds the provider and the page's components.
- Astro renders the page shell; everything interactive is a React island. Routing inside the
  Lab is in the URL hash, so the build stays static.
- The Lab is one page with one island, `composition/LabIsland.tsx` (mounted with `client:only`,
  because it reads the hash and the browser's storage). It wraps `LabShell` in the gateways
  provider and a TanStack Query client. Server state (the system status, refetched every 10 s)
  goes through TanStack Query hooks in `presentation/hooks/` that call the use cases.
- The router is the URL hash: `domain/route.ts` parses and serialises `#/lab…` routes
  (`#/lab/{instance version}/pricing|result/{letter}`, `compare/{letters}`,
  `traveller/{instance version}/{letter}`, each with an optional `?period=`), and
  `presentation/hooks/useHashRoute.ts` follows `hashchange` and replaces a hash that does not
  parse by `#/lab`.
- The layout the visitor chooses (menu, map, share per view, Advanced view, Aa) goes through the
  `LayoutPreferences` port; `infrastructure/storage/` holds the one `localStorage` adapter and
  `composition/gateways.ts` hands it `window.localStorage`.
- The footer's statement, the model's author and the "Run unmodified." switch are constants of
  `domain/footer.ts`; the funding mark is a bundled file in `presentation/assets/`.
- Styling is plain CSS on the SUM tokens in `presentation/styles/tokens.css` (light mode
  only), with a CSS module per component. Fonts are bundled; nothing is loaded from a CDN.

## Configuration

Every setting of the API and of the worker is an environment variable prefixed
`PRICING_DEMO_`, read once in `api/.../infrastructure/config/`, where its default is. The
worker reads the same settings as the API and chooses its adapters the same way. A person sets ports and options in
`.env` (documented in `.env.example`); the Makefile and the Compose files derive the API's
settings from them. The web build takes none: it calls `/api`.

## What is deliberately not decided here

The skeleton proves the layers, the tooling and one request from the screen to the
database. How runs are queued and executed, and where the worker runs, are settled by
[D-12 and D-10](decisions.md). The data model of city instances and pricing versions, the
map and the artefact store belong to the initiative's architecture step, which builds on this
document.
