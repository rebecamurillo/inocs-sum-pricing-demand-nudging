"""The comparison of a stored build with its rebuild (`pricing-demo-worker verify-build`).

A build is described by the sha256 of each output file of the four steps and, for the routes and
travellers steps, by the content of each hub pair. The file hashes decide a step unless a hub-pair
query failed in either build: a failed query removes a pair from a build, so the two builds then
agree only on the pairs both of them have. Option ids differ between builds
(ARCHITECTURE.md § 9), so options are compared without their `arc_id`. Pure: no I/O.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pricing_demo.domain.build_plan import BUILD_STEPS, canonical_json
from pricing_demo.domain.read_model import INSTANCE_ARC_LISTS, ROUTE_ARC_LISTS
from pricing_demo.domain.runs import StepName

Pair = tuple[str, str]
Side = Literal["stored", "rebuilt"]
PAIR_STEPS = (StepName.ROUTES, StepName.TRAVELLERS_AND_BIKES)


@dataclass(frozen=True)
class PairContent:
    """What a build holds for one hub pair: its options (canonical JSON, sorted, without
    `arc_id`) and, in the instance, its demand."""

    options: tuple[str, ...]
    demand: float | None = None


@dataclass(frozen=True)
class BuildDescription:
    files: Mapping[StepName, Mapping[str, str]]
    failed_pairs: frozenset[Pair] = frozenset()
    route_pairs: Mapping[Pair, PairContent] = field(default_factory=dict)
    instance_pairs: Mapping[Pair, PairContent] = field(default_factory=dict)

    def pairs_of(self, step: StepName) -> Mapping[Pair, PairContent]:
        return self.route_pairs if step is StepName.ROUTES else self.instance_pairs

    def has(self, step: StepName, pair: Pair) -> bool:
        return pair in self.pairs_of(step) and pair not in self.failed_pairs


@dataclass(frozen=True)
class FileComparison:
    name: str
    stored: str
    rebuilt: str

    @property
    def matches(self) -> bool:
        return self.stored == self.rebuilt


@dataclass(frozen=True)
class StepComparison:
    step: StepName
    files: tuple[FileComparison, ...]
    by_pairs: bool = False
    compared: int = 0
    only_in: tuple[tuple[Pair, Side], ...] = ()
    differing: tuple[Pair, ...] = ()

    @property
    def matches(self) -> bool:
        if self.by_pairs:
            return not self.differing
        return all(item.matches for item in self.files)


@dataclass(frozen=True)
class BuildComparison:
    steps: tuple[StepComparison, ...]

    @property
    def matches(self) -> bool:
        return all(step.matches for step in self.steps)


def compare_builds(stored: BuildDescription, rebuilt: BuildDescription) -> BuildComparison:
    by_pairs = bool(stored.failed_pairs or rebuilt.failed_pairs)
    return BuildComparison(
        tuple(_compare_step(step, stored, rebuilt, by_pairs) for step in BUILD_STEPS)
    )


def _compare_step(
    step: StepName, stored: BuildDescription, rebuilt: BuildDescription, by_pairs: bool
) -> StepComparison:
    old, new = stored.files.get(step, {}), rebuilt.files.get(step, {})
    files = tuple(
        FileComparison(name, old.get(name, "missing"), new.get(name, "missing"))
        for name in sorted(set(old) | set(new))
    )
    if not (by_pairs and step in PAIR_STEPS):
        return StepComparison(step, files)
    before, after = stored.pairs_of(step), rebuilt.pairs_of(step)
    stored_has = {pair for pair in before if stored.has(step, pair)}
    rebuilt_has = {pair for pair in after if rebuilt.has(step, pair)}
    both = stored_has & rebuilt_has
    only = tuple(
        [(pair, "stored") for pair in sorted(stored_has - rebuilt_has)]
        + [(pair, "rebuilt") for pair in sorted(rebuilt_has - stored_has)]
    )
    differing = tuple(sorted(pair for pair in both if before[pair] != after[pair]))
    return StepComparison(step, files, True, len(both), only, differing)  # type: ignore[arg-type]


def _pair_name(pair: Pair) -> str:
    return f"{pair[0]}>{pair[1]}"


def _step_line(item: StepComparison) -> str:
    verdict = "match" if item.matches else "differ"
    if not item.by_pairs:
        shown = "; ".join(f"{f.name} stored {f.stored} rebuilt {f.rebuilt}" for f in item.files)
        return f"{item.step.value}: {verdict} {shown}"
    count = f"{item.compared} pair{'' if item.compared == 1 else 's'} compared"
    parts = [f"{item.step.value}: {verdict} by hub pairs ({count})"]
    for pair, side in item.only_in:
        parts.append(f"{_pair_name(pair)} only in the {side} build")
    for pair in item.differing:
        parts.append(f"{_pair_name(pair)} differs")
    return "; ".join(parts)


def report_lines(version_id: str, comparison: BuildComparison) -> tuple[str, ...]:
    verdict = "match" if comparison.matches else "differ"
    return (
        *(_step_line(item) for item in comparison.steps),
        f"verify-build {version_id}: {verdict}",
    )


def _malformed(name: str, error: Exception) -> ValueError:
    return ValueError(f"{name} does not have the expected shape: {error!r}")


def _without_id(arc: Mapping[str, Any], mode: str, geometry: Any = None) -> str:
    content = {key: value for key, value in arc.items() if key != "arc_id"}
    content["mode"] = mode
    if geometry is not None:
        content["legs_geometry"] = geometry
    return canonical_json(content)


def route_pair_contents(od_routes: Any, od_geometry: Any) -> dict[Pair, PairContent]:
    """The options of each pair of `od_routes.json`, each with its geometry."""
    try:
        geometries = {item["arc_id"]: item["legs_geometry"] for item in od_geometry["geometries"]}
        found: dict[Pair, PairContent] = {}
        for pair in od_routes["od_results"]:
            options = [
                _without_id(arc, mode, geometries.get(arc["arc_id"]))
                for mode, name in ROUTE_ARC_LISTS.items()
                for arc in pair[name]
            ]
            found[(str(pair["from_id"]), str(pair["to_id"]))] = PairContent(tuple(sorted(options)))
    except (KeyError, TypeError) as error:
        raise _malformed("od_routes.json or od_geometry.json", error) from error
    return found


def instance_pair_contents(instance: Any) -> dict[Pair, PairContent]:
    """The demand and the options of each pair of `Instance_1.json`; the package keys the arcs
    of an instance `{from}_{to}`."""
    try:
        found: dict[Pair, PairContent] = {}
        for item in instance["OD_pairs"]:
            pair = (str(item["origin"]), str(item["destination"]))
            options: list[str] = []
            for mode, name in INSTANCE_ARC_LISTS.items():
                arcs = instance[name]
                if isinstance(arcs, Mapping):
                    options += [
                        _without_id(arc, mode) for arc in arcs.get(f"{pair[0]}_{pair[1]}", [])
                    ]
            found[pair] = PairContent(tuple(sorted(options)), item["demand"])
    except (KeyError, TypeError, AttributeError) as error:
        raise _malformed("Instance_1.json", error) from error
    return found
