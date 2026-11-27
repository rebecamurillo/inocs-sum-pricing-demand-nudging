from collections.abc import Sequence
from dataclasses import dataclass

from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.solves import Solves
from pricing_demo.application.use_cases.get_pricing_result import GetPricingResult, PricingResult
from pricing_demo.domain.comparison import (
    ComparedVersion,
    ComparisonGroup,
    DifferentInstances,
    FlatReference,
    HubDifference,
    PairDifference,
    check_version_count,
    comparison_groups,
    derived_hub_differences,
    derived_pair_differences,
    flat_references,
    goal_numbers,
    identical_solve_groups,
)
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.pricing_versions import (
    NoResult,
    PricingVersion,
    PricingVersionNotFound,
    ResultNotFound,
)
from pricing_demo.domain.solves import PT_BIKE


@dataclass(frozen=True)
class ComparedVersionView:
    """A compared version with its result (simulations, model split, package) and the reference
    of its flat simulation."""

    version: PricingVersion
    result: PricingResult
    flat_reference: str
    package_fingerprint: str
    package_commit: str | None
    goals: dict[str, Number]


@dataclass(frozen=True)
class Comparison:
    instance_version_id: str
    instance_version_name: str
    period_id: str
    period_name: str
    versions: tuple[ComparedVersionView, ...]
    flat_references: tuple[FlatReference, ...]
    groups: tuple[ComparisonGroup, ...]
    pair_difference_letters: tuple[str, str]
    pair_differences: tuple[PairDifference, ...]
    hub_differences: tuple[HubDifference, ...]
    identical_solves: tuple[tuple[str, ...], ...]


def _letter_order(version: PricingVersion) -> tuple[int, str]:
    return len(version.letter), version.letter


class ComparePricingVersions:
    """Two to four finished versions of one instance version side by side. Computed on each
    request from the stored results, never stored. Checks, in order: the count, that each
    version exists, that they share an instance version, that each has a result."""

    def __init__(
        self,
        pricing: PricingVersions,
        get_result: GetPricingResult,
        solves: Solves,
        instances: CityInstances,
    ) -> None:
        self._pricing = pricing
        self._get_result = get_result
        self._solves = solves
        self._instances = instances

    def execute(self, version_ids: Sequence[str], period_id: str | None = None) -> Comparison:
        check_version_count(len(version_ids))
        distinct = list(dict.fromkeys(version_ids))
        found = []
        for version_id in distinct:
            version = self._pricing.get(version_id)
            if version is None:
                raise PricingVersionNotFound(version_id)
            found.append(version)
        check_version_count(len(distinct))
        instance_version_ids = sorted({item.instance_version_id for item in found})
        if len(instance_version_ids) > 1:
            raise DifferentInstances(instance_version_ids)
        ordered = sorted(found, key=_letter_order)
        periods = self._pricing.period_ids(ordered[0].id)
        period = period_id or (periods[0] if periods else None)
        results = []
        for version in ordered:
            try:
                results.append(self._get_result.execute(version.id, period))
            except ResultNotFound as error:
                raise NoResult(version.id) from error
        compared = [self._compared(item) for item in results]
        references = flat_references(compared)
        by_letter = {item.letter: item.flat_reference_id for item in compared}
        views = tuple(
            ComparedVersionView(
                item.version,
                item,
                by_letter[item.version.letter],
                item.provenance.package_fingerprint,
                item.provenance.package_commit,
                goal_numbers(item.version.goals),
            )
            for item in results
        )
        return self._assemble(instance_version_ids[0], results, compared, references, views)

    def _assemble(
        self,
        instance_version_id: str,
        results: list[PricingResult],
        compared: list[ComparedVersion],
        references: tuple[FlatReference, ...],
        views: tuple[ComparedVersionView, ...],
    ) -> Comparison:
        a, b = compared[-2], compared[-1]
        instance_version = self._instances.get_version(instance_version_id)
        instance = (
            None
            if instance_version is None
            else self._instances.get_instance(instance_version.instance_id)
        )
        name = (
            instance_version_id
            if instance is None or instance_version is None
            else f"{instance.name} v{instance_version.number}"
        )
        period_id = results[0].period_id
        label = next(
            (
                item.label
                for item in self._instances.periods_of(instance_version_id)
                if item.id == period_id
            ),
            period_id,
        )
        return Comparison(
            instance_version_id,
            name,
            period_id,
            label,
            views,
            references,
            comparison_groups(compared, references),
            (a.letter, b.letter),
            derived_pair_differences(a, b),
            derived_hub_differences(a, b),
            identical_solve_groups(compared),
        )

    def _compared(self, result: PricingResult) -> ComparedVersion:
        by_scheme = {item.link.price_scheme: item for item in result.simulations}
        flat = by_scheme["flat"]
        solve_key = result.provenance.solve_key
        offered = sum(
            1
            for row in self._solves.rows(solve_key)
            if row.type == PT_BIKE and row.bike_price is not None
        )
        return ComparedVersion(
            result.version.letter,
            result.version.goals,
            result.numbers,
            by_scheme["model_prices"].summary,
            flat.summary,
            flat.rule_current,
            solve_key,
            result.advanced,
            offered,
        )
