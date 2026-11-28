"""Story 3-4's maintainer check of the pricing model: a 500 m Geneva instance solved end to end
with a full Gurobi licence and a running trip planner. Collected only with `-m live`
(`make live-smoke`); never part of an unattended run."""

import threading
from dataclasses import replace
from pathlib import Path

import pytest

from pricing_demo.application.ports.city_preparation import PreparationRequest
from pricing_demo.application.ports.pricing_solver import SolveRequest
from pricing_demo.domain.city_instances import first_period, parameters_from_defaults
from pricing_demo.domain.pricing_keys import FIXED_SOLVER_INPUTS, SOLVER_GOALS
from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.config.settings import DEMO_DIR, Settings
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.pricing_model.city_preparation import PackageCityPreparation
from pricing_demo.infrastructure.pricing_model.package_fingerprint import PackageFingerprintReader
from pricing_demo.infrastructure.pricing_model.pricing_solver import PackagePricingSolver
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild

pytestmark = pytest.mark.live


def test_a_500_m_instance_solves_end_to_end_under_a_full_licence(tmp_path: Path) -> None:
    settings = Settings()
    dataset = PostgresCityDatasets(create_db_engine(settings.database_url)).latest()
    assert dataset is not None, "no city data set: run `make city-data`"
    port = PackageCityPreparation(
        settings.data_dir,
        StageChild(),
        settings.otp_url,
        settings.otp_workers,
        settings.otp_retries,
        settings.otp_retry_wait_s,
    )
    fingerprint = PackageFingerprintReader(DEMO_DIR.parent / "sum_nsm_dynamic_pricing").read()
    parameters = replace(
        parameters_from_defaults(fingerprint.defaults, dataset.preset), radius_m=500
    )
    period = first_period("live.v1", dataset)
    for step in (
        StepName.AREA,
        StepName.HUBS,
        StepName.ROUTES,
        StepName.TRAVELLERS_AND_BIKES,
    ):
        request = PreparationRequest("live", step, tmp_path, parameters, dataset, period)
        built = port.prepare(request, lambda done, total: None, threading.Event())
        assert built.failure_code is None, (step, built.failure_reason)
    goals = {name: new_draft_goals(None).as_dict()[name] for name in SOLVER_GOALS}

    outcome = PackagePricingSolver(StageChild(), "live", "live").solve(
        SolveRequest("live", tmp_path, goals, dict(FIXED_SOLVER_INPUTS), fingerprint.fingerprint),
        threading.Event(),
    )

    assert outcome.failure_code is None, (outcome.failure_reason, outcome.log_excerpt)
    assert outcome.solve is not None
    assert outcome.solve.rows
    assert outcome.solve.provenance.licence_kind == "full"
