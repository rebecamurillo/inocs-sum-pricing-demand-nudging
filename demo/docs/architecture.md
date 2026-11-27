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
      pricing_model/           the package gateway: the probes, the city preparation and its
                               stage child (stage_runner.py is the child's entry; worker only),
                               the routes step's progress reader (routes_progress.py), sort
                               (routes_file.py) and retry policy (retry_policy.py)
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
    characterisation/          the unmodified package on committed fixtures (marker: characterisation)
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

The four steps run in a stage child. The worker writes a spec file (`stage-spec.json`: the
step, the working directory, the worker's pid, the package's settings) and starts
`python -m pricing_demo.infrastructure.pricing_model.stage_runner {spec.json}` in its own
session and process group, with the step's working directory as current directory and its output
in `stdout.log` and `stderr.log` there. The child installs a handler on the logger
`sum_nsm_dynamic_pricing` that appends JSON lines to `progress.jsonl`, runs the package, and
leaves `outcome.json` (`status` and `counts`, or the exception's type, message and traceback);
it exits on its own when its parent pid changes (checked every 2 s). The worker reaps it only
through `os.wait4`, which also gives its peak memory, and maps what it left: `done` with counts,
`instance_unbalanced` for the package's second validation failure, `stage_error` for any other
exception ("{type}: {message}", the traceback only in the log), `killed` for a signal the worker
did not send. A cancel sends SIGTERM to the process group, SIGKILL after 10 s, and the working
directory is deleted. The run step stores `log_excerpt` (the whole log up to 256 KiB, else the
first and last 128 KiB) and `peak_rss_bytes`. Step 4 also writes `option_bike_legs.json`, the
bike-leg count of each option from the package's own parser.

Step 3 (routes) runs in the same child. The worker writes `otp_timestamp` (the period's routing
date and time, local wall clock with a `Z` suffix), `otp_url`, `otp_workers` and the version's
minimum trip distance into the spec; the child sets the route builder's logger to DEBUG and the
client's to INFO, deletes any `od_cache.json` before and after (a resumed build repeats option ids), and mounts the
demonstrator's retry policy (`PRICING_DEMO_OTP_RETRIES` retries, a fixed wait of
`PRICING_DEMO_OTP_RETRY_WAIT_S` seconds, also on `POST`) on every `OTPClient` the step creates,
restoring the package's own `__post_init__` afterwards; then it sorts `od_results` by (`from_id`,
`to_id`) so that one seed gives one set of travellers. While it runs the worker reads
`progress.jsonl` every 500 ms (and once after the child ended): the total, one query done per
pair line, and each failed query as a `route_failures` row. An unreachable trip planner ends the
step `trip_planner_unreachable`, no pair left `no_public_transport`. Before any child starts, a
graph manifest whose `gtfs_sha256` differs from the data set's timetable fails the step
`timetable_mismatch` (`BuildStepExecutor`).

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

A third worker command, `pricing-demo-worker otp-graph` (`make otp-graph`, optional `--dataset
{id}`, default the latest), builds the trip planner's graph from a data set. The use case
`BuildTripPlannerGraph` refuses before it writes anything (no data set, unknown id, another
`*gtfs*.zip` in the graph folder, not exactly one `.osm.pbf`), removes a stale
`graph-manifest.json`, copies the data set's GTFS copy to `gtfs.zip`, writes
`build-config.json` with the feed's first and last valid dates as the service window, runs the
build and only then writes the manifest (OTP image, data set id, hashes of `gtfs.zip` and of the
`.osm.pbf`, the build config). The ports are `GraphFolder` (`LocalGraphFolder`, the files in
`PRICING_DEMO_OTP_GRAPH_DIR`, default `otp/data/`), `GraphBuilder` (`ComposeGraphBuilder` runs
`docker compose --profile otp run --rm otp-build`; `FakeGraphBuilder` in the unit tests) and
`GraphFingerprints` (`FileGraphFingerprints`). At start and at each report the worker adds
`graph_manifest` and `graph_sha256` (the hash of `graph.obj`, recomputed only when its size or
modification time changed; both null without a manifest) to the `trip_planner` component's
`details`; the solver and package reports keep `details = {}`. No route exposes `details`.

The GTFS copy is shaped: after copying, the import hands the copy and the `.osm.pbf` to the
`BusShapeMatcher` port, and `ZipTimetableShapes` writes the tool's `shapes.txt` and the
`shape_id` of the bus trips (route types 3 and 700-799) into the copy; every other entry stays
byte for byte as in the source zip, and `gtfs_sha256` is taken after the rewrite. The real
adapter, `DockerPfaedleMatcher`, runs pfaedle (image `PRICING_DEMO_SHAPE_TOOL_IMAGE`, pinned by
digest) in a container, moving the files with `docker cp` so that it works with any Docker
daemon, and keeps only `shapes.txt` and the trips' `shape_id` from its output; the fake
(`FakeBusShapeMatcher`) draws each bus trip through its stops and needs no Docker. A matcher that
cannot run, exits non-zero or produces no bus shape does not fail the import: the copy stays the
source zip and the data set records `bus_shapes = none`. The columns `bus_shapes`
(`generated` or `none`), `bus_shapes_reason` (set exactly when `none`) and `shape_tool_image`
record the outcome and the tool; the refresh carries them over with the reused copy.

### City instances

A city instance is a named set of parameters on one data set, saved as numbered versions that
never change once saved. Four tables hold it (`city_instances`, `instance_versions`,
`instance_periods`, `package_fingerprints`). The instance's id is the slug of its name, fixed
at creation (`Geneva 3 km` becomes `geneva-3km`); a version is `{instance}.v{n}` and its
first period `{version}.mon-08`. `city_instances.next_number` is taken and incremented in the
transaction that creates a draft, under a row lock, so a discarded number is never used
again. A partial unique index allows one draft per instance. The 14 parameters are typed
`double precision` columns of `instance_versions`: a value is stored as sent, so a seed of
1.5 is kept and reported as a broken rule. A `BEFORE UPDATE` trigger (declared in the
migration only) raises when a row with `status = 'sealed'` has any parameter column changed.
`runs.instance_version_id` and `run_steps.period_id` are foreign keys to the version and the
period.

The ten rules a draft is checked against live in `domain/instance_rules.py`; every `PATCH` of
a draft answers with their results, each naming two values, and with "what changes" against
the version the draft is based on. A rule reports, it never corrects.

At start and with every heartbeat the worker records the package it runs
(`RecordPackageFingerprint`, port `PackageFingerprints`): the sha256 over the package's source
files and the repository commit, `git_dirty`, the version from `pyproject.toml` and the
dataclass defaults of `PipelineConfig`, `InstanceParams` and `OptimizerParams`, read in a child
process by `infrastructure/pricing_model/package_fingerprint.py`. The row is insert-if-new, and
its fingerprint is also written on the worker's `workers` row (no foreign key: the e2e reset
truncates both tables). The API reads the latest row for "start from the package defaults".
The fake adapter set records a fixed fingerprint whose defaults are constants copied from the
package.

### Builds and the artefact store

`POST /api/v1/instance-versions/{id}/builds` (`BuildInstanceVersion`) checks, in this order,
that the version exists, that a draft breaks no rule, that no run of the version is queued or
running, that its latest build has not succeeded, and that the components its plan needs are
available. It then, in one transaction (`Builds.queue_build`), seals the draft and inserts a
`build` run with four `pending` `run_steps`; a sealed version whose build failed or was
cancelled is queued again without sealing. The one-active-run index turns a racing second
request into `run_active`.

A step's **input key** is the sha256 of the canonical JSON (sorted keys, compact, a whole
number written without a decimal) of: the step name, the parameters it reads
(`domain/build_plan.py`: `STEP_PARAMETERS`), the keys of the steps it reads, the snapshot
hashes it reads (the timetable and bike-station hashes for `area`, the timetable's for `hubs`,
the trip planner's graph manifest for `routes`), the routing moment (steps 3 and 4) and the
package fingerprint. `otp_workers` is not in any key. A key is null while the fingerprint (or,
for steps 3 and 4, the graph manifest) is unknown; the step is then planned as rebuilt and the
plan's `build_verdict` says which component lacks it. The API computes the plan from what is
stored (`application/build_planning.py`); the worker computes it again for each step and writes
the key it finds to the run step, so the stored artefacts, not the plan the API made earlier,
decide `kept`.

A **working directory** `var/data/runs/{run}/{step}/` holds a step while it runs, with the
upstream artefacts copied in by the file names the package expects (copies, made writable,
because the package rewrites its inputs). On success the step's outputs move to
`var/data/artifacts/{step}/{key}/` through a temporary sibling name and a rename, so no partial
folder is ever visible; the files are made `0444` and the folder `0555`. One `artifacts` row
holds the key, the step, the canonical inputs, each file's name, sha256 and size, the path
(relative to the data directory) and the package fingerprint; the folder is never changed. A
key whose folder exists is reused: same key, same content. The working directory is deleted on
success and on a stop, and kept on a failure. Once the outputs are stored the worker ingests them
into the read model (§ Read model) and only then writes the step's `instance_version_steps` row
(version, step, period, key), so the steps already done are readable while the run goes on and
a link always names an ingested artefact. That table's key is a unique constraint with
`NULLS NOT DISTINCT`, because steps 1 and 2 have no period and a primary key cannot hold a
null.

`ProcessNextRun` asks a step's keeper (`StepKeeper`, implemented by `BuildStepExecutor` with
the executor) before it starts the step; a step whose key has an ingested artefact moves
`pending` to `kept` at once and costs nothing. The city is prepared through the `CityPreparation` port;
its fake and the pricing-model adapter implement it.

### Read model

The tables every screen reads, none of which needs a file: `stations`, `hubs` and
`station_hubs` (keyed by the `area` and `hubs` artefacts), `hub_pairs`, `route_options`,
`station_bikes` and `option_station_deltas` (keyed by the `travellers_and_bikes` artefact), each
with a foreign key `ON DELETE CASCADE` to `artifacts.input_key`, and `route_failures`. The API
reads PostgreSQL only; it never opens an artefact folder.

**Ingestion.** After a step's outputs are stored, `StepIngestion` reads the artefact's files
through `ArtifactFiles.read_json` (the last step also reads the routes artefact's
`od_routes.json` and `od_geometry.json`), builds the rows and the step's counts with the pure
readers of `domain/read_model.py`, and `ReadModel.ingest` writes them in one transaction: the
key's rows are replaced, then `artifacts.counts` and `artifacts.ingested_at` are set. The link
is written after it. A failure (a file that is missing or malformed, a database error) rolls
the transaction back, fails the step with `stage_error` and leaves the artefact row and folder
where they are. `ingested_at` decides `kept`: the next build of the version finds the artefact
without it, runs the step as an ingest-only rerun (no working directory, no call to the
preparation) and counts and rows are those a fresh build would write.

**Counts.** The step's counts are stored on its `artifacts` row and on its run step: `area`
`stops` and `bike_stations`; `hubs` `hubs`; `routes` `hub_pairs_requested`,
`hub_pairs_with_routes`, `hub_pairs_removed`, `queries` (two per pair requested),
`queries_failed`, `failure_pct` (`queries_failed` / `queries` × 100) and `retries`;
`travellers_and_bikes` `hub_pairs`, `travellers`, `bike_stations` and `options` per mode. The
artefact also keeps the run that produced it (`run_id`) and the counts that run's step reported
(`reported_counts`): an ingest-only rerun, which has no preparation to ask, reads them back.
`GET /instance-versions/{id}` derives its five headline numbers and its routes summary from
these, and both are null until every step of the version is linked to an ingested artefact.

**Route failures.** `CityPreparation.prepare` calls `route_failed` once per failed
trip-planner query as it happens; the executor writes one `route_failures` row for each (run,
run step, period, pair, query `pt_bike` | `car`, kind `technical` | `no_route`, message,
attempts) and clears the step's rows before a routes step starts. The run's `failure_pct` is set
when the routes step is done or kept. A kept routes step has no failures of its own: its
summary and `GET /runs/{run_id}/route-failures` name the run that produced the routes
(`artifacts.run_id`).

**`line_kind`.** Each leg of a `route_options` row records `street` for a street mode
(`BICYCLE`, `CAR`, `FOOT`, `WALK`), and for a transit leg `shape` when its public code is in the
set of routes that have a shape in the data set's timetable (`FeedShapes`), `straight`
otherwise.

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
      assets/  components/  hooks/  layouts/  map/  styles/
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
- The map ([D-9](decisions.md)): `presentation/map/` holds the map pane, the map context (a
  view declares its sources and layers with `useMapLayers` and where to look with
  `useMapFit`; it never creates a map), the narrow `MapHandle` the components use, the
  basemap style and the pure `l1Layers(...)`. `maplibre-gl` and `pmtiles` are imported only in
  `composition/map-factory.ts`, which `LabIsland` injects. `LabShell` mounts the pane once; hiding the
  map hides the pane without unmounting the map, and a `ResizeObserver` resizes the map and
  fits the study circle when the pane's width changes or the pane is shown again. Under
  `prefers-reduced-motion` the map has no fade and its camera jumps. The basemap file
  `web/public/basemap/{dataset}.pmtiles` comes from `make basemap`; the web sends
  `HEAD /basemap/{dataset}.pmtiles` through the `BasemapGateway` and, only on a 200, uses it;
  otherwise the style is the ground colour alone. The `CityDatasetGateway` reads
  `GET /api/v1/city-datasets` for the data set whose preset circle the map fits when no
  instance version is open.
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
[D-12 and D-10](decisions.md); the artefact store by [D-8](decisions.md) and the
[Builds and the artefact store](#builds-and-the-artefact-store) section. The data model of
pricing versions belongs to the initiative's architecture step, which builds on
this document.
