"""What the characterisation tests share: the committed synthetic city, packed the way a city
data set is stored, and the real `CityPreparation` on it."""

import shutil
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path

from pricing_demo.application.ports.city_preparation import PreparationRequest
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.city_instances import first_period, parameters_from_defaults
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.pricing_model.city_preparation import PackageCityPreparation
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild
from tests.support.runs import T0

FIXTURES = Path(__file__).parent / "fixtures"
# `demo/` is three folders above `demo/api/tests/characterisation`.
GENEVA_GTFS = (
    Path(__file__).resolve().parents[4]
    / "Geneva_Complete_Link_Instances_and_Optimization"
    / "OTP2_Geneva_Instances"
    / "tpg_gtfs.zip"
)
GBFS_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "src/pricing_demo/infrastructure/fakes/fixtures/gbfs_station_information.json"
)


def zip_feed(folder: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w") as archive:
        for item in sorted(folder.iterdir()):
            archive.write(item, item.name)


@dataclass
class City:
    """A data directory holding one data set's two files, and the port that reads it."""

    data_dir: Path
    dataset: CityDataset
    port: PackageCityPreparation

    def request(self, folder: Path, step: StepName, **changes: float) -> PreparationRequest:
        folder.mkdir(parents=True, exist_ok=True)
        parameters = parameters_from_defaults(FAKE_FINGERPRINT.defaults, self.dataset.preset)
        return PreparationRequest(
            "run-1", step, folder, replace(parameters, **changes), self.dataset, self.period
        )

    @property
    def period(self):  # type: ignore[no-untyped-def]
        return first_period("geneva-3km.v1", self.dataset)

    def prepare(
        self, folder: Path, step: StepName, stop: StopSignal, **changes: float
    ) -> StepOutcome:
        return self.port.prepare(self.request(folder, step, **changes), lambda d, t: None, stop)


def make_city(data_dir: Path, gtfs: Path | None, gbfs: Path, name: str = "synthetic") -> City:
    """`gtfs` is a zip to use in place (`None`: zip the synthetic feed into the data set)."""
    folder = data_dir / "datasets" / name
    folder.mkdir(parents=True)
    gbfs_copy = folder / "station_information.json"
    shutil.copyfile(gbfs, gbfs_copy)
    if gtfs is None:
        gtfs_copy = folder / "gtfs.zip"
        zip_feed(FIXTURES / "gtfs", gtfs_copy)
        file = str(gtfs_copy.relative_to(data_dir))
    else:
        file = str(gtfs.resolve().relative_to(data_dir.resolve(), walk_up=True))
    base = fake_city_dataset(name, T0)
    dataset = replace(
        base,
        gtfs=replace(base.gtfs, file=file),
        gbfs=replace(base.gbfs, file=str(gbfs_copy.relative_to(data_dir))),
    )
    return City(data_dir, dataset, PackageCityPreparation(data_dir, StageChild()))
