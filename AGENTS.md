# AGENTS.md — orientation for coding agents

Read this first. It says what this repository is, which parts may change and where the rules
for each part live.

## What this repository is

The dynamic pricing model of the EU SUM project (shared bikes with public transport, Geneva
living lab) and the demonstrator that runs it.

| Part | Path | Owner | May you edit it? |
| --- | --- | --- | --- |
| The model | `sum_nsm_dynamic_pricing/` | the research team | **No.** See rule 1. |
| Legacy scripts, notebooks, report | `Geneva_Complete_Link_Instances_and_Optimization/`, `Old_codes_and_processes/`, `*.ipynb`, `*.pdf`, `data/` | the research team | **No.** Reference only. |
| The demonstrator | `demo/` | this repository | Yes — under [`demo/AGENTS.md`](demo/AGENTS.md) |
| CI for the demonstrator | `.github/workflows/demo-ci.yml` | this repository | Yes |
| Static pages on GitHub Pages | `site/`, `.github/workflows/pages.yml` | the maintainer | Only when asked. Not part of the demonstrator; see the root `README.md`. |

## Hard rules

1. **The model is used unmodified.** Never edit a file under `sum_nsm_dynamic_pricing/`. Results
   must stay attributable to the research team's code. A defect that blocks a run is worked
   around inside the demonstrator's adapter
   (`demo/api/src/pricing_demo/infrastructure/pricing_model/`) and reported in
   `demo/docs/model-notes.md`; it is never patched in place.
   Check: `git status --short sum_nsm_dynamic_pricing` prints nothing.
2. **Never change the legacy folders, the notebooks or `data/`.** They are not a reference for
   how the model works either: the package under `sum_nsm_dynamic_pricing/src/` is. One file
   there is input data: the Geneva GTFS feed listed in `demo/docs/model-notes.md`.
3. **All demonstrator work happens under `demo/`** and follows `demo/AGENTS.md`. Nothing is
   added at the repository root except this file, `CLAUDE.md` and the CI workflow.
4. **Git LFS trap.** The root `.gitattributes` sends every `*.json` and `*.geojson` to Git
   LFS, and no LFS server holds this repository's objects. `demo/.gitattributes` cancels the
   filter inside `demo/`; never remove it, and never add a JSON file outside `demo/`.
   Clone with `GIT_LFS_SKIP_SMUDGE=1`.
5. **Commit only when asked**, on the branch you were given. Never push.
