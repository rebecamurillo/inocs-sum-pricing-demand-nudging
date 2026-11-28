"""Story 2-8's maintainer checks of the routes step: a running OpenTripPlanner with a built
graph, the city data set in PostgreSQL. Collected only with `-m live` (`make live-smoke`)."""

import threading
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import requests

from pricing_demo.application.ports.city_preparation import PreparationRequest
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.city_instances import first_period, parameters_from_defaults
from pricing_demo.domain.runs import StepName
from pricing_demo.domain.trip_planner_graph import timetable_matches
from pricing_demo.infrastructure.config.settings import DEMO_DIR, Settings
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.pricing_model.city_preparation import PackageCityPreparation
from pricing_demo.infrastructure.pricing_model.package_fingerprint import PackageFingerprintReader
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild
from pricing_demo.infrastructure.trip_planner.graph_fingerprints import FileGraphFingerprints

pytestmark = pytest.mark.live

MONDAY = date(2025, 3, 10)
QUERY = """query trip($from: InputCoordinates!, $to: InputCoordinates!, $date: String!,
  $time: String!, $arriveBy: Boolean) {
  plan(from: $from, to: $to, date: $date, time: $time, arriveBy: $arriveBy) {
    itineraries { legs { mode } }
  }
}"""


def latest_dataset() -> CityDataset:
    dataset = PostgresCityDatasets(create_db_engine(Settings().database_url)).latest()
    assert dataset is not None, "no city data set: run `make city-data`"
    return dataset


def test_the_trip_planner_answers_a_monday_query_with_a_transit_leg() -> None:
    variables: dict[str, Any] = {
        "from": {"lat": 46.2100, "lon": 6.1420},
        "to": {"lat": 46.1980, "lon": 6.1550},
        "date": MONDAY.isoformat(),
        "time": "08:30:00",
        "arriveBy": True,
    }

    response = requests.post(
        Settings().otp_url, json={"query": QUERY, "variables": variables}, timeout=60
    )

    response.raise_for_status()
    itineraries = response.json()["data"]["plan"]["itineraries"]
    modes = {leg["mode"] for item in itineraries for leg in item["legs"]}
    assert modes & {"BUS", "TRAM", "RAIL", "SUBWAY"}, modes


def test_the_graph_was_built_from_the_latest_datasets_timetable() -> None:
    fingerprint = FileGraphFingerprints(Settings().otp_graph_dir).read()

    assert fingerprint.manifest is not None, "no graph manifest: run `make otp-graph`"
    assert timetable_matches(fingerprint.manifest, latest_dataset().gtfs)


def test_a_500_m_instance_builds_steps_1_to_4_on_the_real_adapters(tmp_path: Path) -> None:
    settings = Settings()
    dataset = latest_dataset()
    data_dir = settings.data_dir
    port = PackageCityPreparation(
        data_dir,
        StageChild(),
        settings.otp_url,
        settings.otp_workers,
        settings.otp_retries,
        settings.otp_retry_wait_s,
    )
    defaults = PackageFingerprintReader(DEMO_DIR.parent / "sum_nsm_dynamic_pricing").read().defaults
    parameters = parameters_from_defaults(defaults, dataset.preset)
    parameters = replace(parameters, radius_m=500)
    period = first_period("live.v1", dataset)
    for step in (
        StepName.AREA,
        StepName.HUBS,
        StepName.ROUTES,
        StepName.TRAVELLERS_AND_BIKES,
    ):
        request = PreparationRequest("live", step, tmp_path, parameters, dataset, period)
        outcome = port.prepare(request, lambda done, total: None, threading.Event())
        assert outcome.failure_code is None, (step, outcome.failure_reason)
