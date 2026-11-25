# Notes on the model — what the package needs and where it resists

Facts about `sum_nsm_dynamic_pricing` 0.1.0 that the demonstrator must work around in its
adapter, since the package is not modified. Each entry cites the file. Add to this list
when a new one is found; report each to the model's author.

| # | Fact | Where | Effect on the demonstrator |
| --- | --- | --- | --- |
| 1 | The solver sets `NodefileDir` to a Windows path (`C:\b_b_gurobi`) | `optimizer/solver.py` (~line 616) | On macOS and Linux a folder of that name may be created in the working directory of a run |
| 2 | The summary hard-codes a bike cost of 0.5 and a per-minute logic | `optimizer/metrics.py` | Profit and cost per ride cannot be read from the package's summary |
| 3 | `display()` is called outside IPython, but only when `show` is true; `optimizer.summarize` passes `show=False` | `optimizer/metrics.py` (~line 158), `optimizer/__init__.py:80-81` | None through `summarize`; never call `summarize_experiment_solutions` with `show=True` |
| 4 | Every stage reads and writes files under one `output_dir` | `pipeline.py`, `config.py` | A run needs its own directory |
| 5 | A run needs a Gurobi licence, an OpenTripPlanner server and, unless a local file is given, the Donkey Republic feed | `optimizer/solver.py`, `routing/otp_client.py`, `stations/providers/donkey.py` | The API must start and serve stored results without them |
| 6 | The routing moment is one fixed timestamp, by default Sunday 2026-03-08, which is outside the validity of the committed GTFS feed (2024-12-15 to 2025-12-13, `feed_info.txt`) | `config.py` (`otp_timestamp`) | A run with the default date finds no public transport; the caller sets a routing date inside the feed's validity |
| 7 | The only GTFS file in the repository is under a legacy folder | `Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/tpg_gtfs.zip` | It may be read as input data; nothing else in that folder is used |
| 8 | `gurobipy` installed from PyPI starts under a built-in size-limited licence: an environment starts, and a model over the limit fails at `optimize()` with error 10010 | observed with `gurobipy` 14.0.0 (2026-11-25) | "A Gurobi environment starts" does not mean a city-sized run can be solved; the solver's status must tell the two apart |
| 9 | Importing the package loads every stage and its heavy dependencies (pandas, geopandas, scikit-learn) | `__init__.py` | The first import takes seconds; the adapter imports it lazily |
| 10 | The routes step appends hub pairs in the order its threads finish, and the travellers step draws each pair's demand in file order from one seeded generator | `routing/route_builder.py:328-332`, `instance/generator.py:110-116` | The same seed gives different travellers on each build unless the routes file is put in a fixed order between the two steps |
| 11 | Option ids come from a counter that restarts at 0 when a build resumes from `od_cache.json` | `routing/route_builder.py:253-255` | A resumed build repeats ids; every routes step starts from an empty directory |
| 12 | Itineraries without public transport (bike alone, walk alone) are dropped | `routing/route_builder.py:120-139, 209-215` | The model has three modes: public transport with bike, public transport alone, car |
| 13 | A failed trip-planner query drops its hub pair without an error | `routing/route_builder.py:188-193, 229-230` | A build can store holes; failures must be counted from the log |
| 14 | The solver reports its errors with `print` and returns `None`; the caller then writes `null` to the results file | `optimizer/solver.py:626-638, 875-890`, `optimizer/__init__.py:71-75` | The outcome of a solve is read from its return value and its captured output, not from an exception |
| 15 | The model sets one bike price per offered option (up to ten per hub pair), and the number of bike legs that multiplies price and cost is not in the solution | `optimizer/solver.py:251, 579-581`, `optimizer/parser.py:54-78` | There is no single price per hub pair; bike legs come from the package's parser |
| 16 | Clustering works in EPSG:3857, so the grouping distance is in Web-Mercator units (at Geneva one unit is about 0.69 m on the ground: the default 500 is about 346 m); the minimum trip distance is in ground metres | `clustering/strategy.py:12-13`, `routing/od_permutations.py:30-35` | The two distances are not in the same unit |
| 17 | The choice-model coefficients are constants local to the solver | `optimizer/solver.py:87-101` | They appear in no output |
| 18 | `optimizer.solve` always computes its own upper price bound, 0.2 above the lowest price | `optimizer/__init__.py:39-46`, `optimizer/p_off.py:72-73` | No value of its parameters fixes the price; a flat price needs the inner solver function the package exports |

Entries 1, 2 and 10 to 18 were read in the code (10, 15 and 18 re-checked on 2026-11-25) and
not yet reproduced by a run on this set-up. Each is to be reported to the model's author.
