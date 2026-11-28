"""Finding the result of a pricing version: the one rule every result route and the showcase
share."""

from collections.abc import Mapping
from dataclasses import dataclass

from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.simulations import SimulationLink, Simulations
from pricing_demo.application.ports.solves import SolveRecord, Solves, StoredResultSummary
from pricing_demo.domain.derived_result import DERIVATION_VERSION
from pricing_demo.domain.pricing_versions import (
    PricingVersion,
    PricingVersionNotFound,
    ResultNotFound,
)
from pricing_demo.domain.runs import Run, RunState

SCHEMES = ("model_prices", "flat")


@dataclass(frozen=True)
class FoundResult:
    version: PricingVersion
    period_id: str
    run: Run
    solve: SolveRecord
    summary: StoredResultSummary
    # The latest simulation of each scheme: the link with the greatest `created_at` (the
    # greatest rule version on a tie).
    links: Mapping[str, SimulationLink]


class ResultLookup:
    """A version has a result when its latest pricing run succeeded, the solve of the period is
    stored with a summary of the current derivation version, and both schemes are simulated."""

    def __init__(self, pricing: PricingVersions, solves: Solves, simulations: Simulations) -> None:
        self._pricing = pricing
        self._solves = solves
        self._simulations = simulations

    def find(self, version_id: str, period_id: str | None = None) -> FoundResult:
        """Raises `PricingVersionNotFound`, and `ResultNotFound` for any missing part (a
        period the version does not price included)."""
        version = self._pricing.get(version_id)
        if version is None:
            raise PricingVersionNotFound(version_id)
        periods = self._pricing.period_ids(version_id)
        period = period_id or (periods[0] if periods else None)
        if period is None or period not in periods:
            raise ResultNotFound(version_id)
        run = self._pricing.latest_run(version_id)
        if run is None or run.state is not RunState.SUCCEEDED:
            raise ResultNotFound(version_id)
        solve = self._solves.solve_of(version_id, period)
        summary = None if solve is None else self._solves.summary_of(solve.key, DERIVATION_VERSION)
        if solve is None or summary is None:
            raise ResultNotFound(version_id)
        latest: dict[str, SimulationLink] = {}
        for link in self._simulations.links_of(version_id):
            if link.period_id != period:
                continue
            known = latest.get(link.price_scheme)
            if known is None or (link.created_at, link.rule_version) > (
                known.created_at,
                known.rule_version,
            ):
                latest[link.price_scheme] = link
        if any(scheme not in latest for scheme in SCHEMES):
            raise ResultNotFound(version_id)
        return FoundResult(version, period, run, solve, summary, latest)
