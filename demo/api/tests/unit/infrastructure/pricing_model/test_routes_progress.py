from pathlib import Path
from typing import Any, cast

import pytest

from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.infrastructure.pricing_model import routes_progress as p
from pricing_demo.infrastructure.pricing_model.routes_progress import ProgressFile, RoutesProgress


def record(template: str, *args: object) -> dict[str, object]:
    return {"template": template, "args": list(args)}


def test_the_total_template_sets_the_total() -> None:
    progress = RoutesProgress(3)

    failures = progress.feed(record(p.ROUTE_TOTAL, 12, 0, 12, 4, 0.05))

    assert failures == []
    assert (progress.total, progress.done) == (12, 0)


def test_the_templates_are_the_packages_texts() -> None:
    assert p.ROUTE_TOTAL == (
        "Route building: %d total OD pairs | %d already cached | %d to query "
        "(workers=%d, delay=%.2fs)"
    )
    assert p.PT_FAILED == "OTP PT query failed for pair %s: %s"
    assert p.PT_NONE == "No PT patterns returned for pair %s"
    assert p.PT_UNCLASSIFIED == "All %d pattern(s) for pair %s were unclassified (no PT/bike modes)"
    assert p.CAR_DONE == "OTP CAR [%s]: car=%d"
    assert p.CAR_FAILED == "OTP CAR query failed for pair %s: %s"
    assert p.CLEANUP_REMOVED == "OD cleanup removed %d/%d OD pairs (%.2f%% invalid) from %s"


@pytest.mark.parametrize(
    ("line", "query", "kind", "attempts"),
    [
        (record(p.PT_FAILED, "1|2", "503"), "pt_bike", "technical", 4),
        (record(p.PT_NONE, "1|2"), "pt_bike", "no_route", 1),
        (record(p.PT_UNCLASSIFIED, 2, "1|2"), "pt_bike", "no_route", 1),
        (record(p.CAR_FAILED, "1|2", "boom"), "car", "technical", 4),
        (record(p.CAR_DONE, "1|2", 0), "car", "no_route", 1),
    ],
)
def test_each_failed_query_becomes_one_failure(
    line: dict[str, object], query: str, kind: str, attempts: int
) -> None:
    progress = RoutesProgress(3)

    failures = progress.feed(line)

    template = str(line["template"])
    args: Any = tuple(cast(list[Any], line["args"]))
    expected = RouteFailure("1", "2", query, kind, template % args, attempts)  # type: ignore[arg-type]
    assert failures == [expected]
    assert progress.done == 1


def test_a_car_answer_with_options_is_done_and_not_a_failure() -> None:
    progress = RoutesProgress(3)

    assert progress.feed(record(p.CAR_DONE, "1|2", 2)) == []
    assert progress.done == 1


def test_the_removed_pairs_are_read_and_unknown_templates_are_ignored() -> None:
    progress = RoutesProgress(0)

    assert progress.feed(record(p.CLEANUP_REMOVED, 2, 10, 20.0, "f")) == []
    assert progress.feed(record("something else %s", "x")) == []
    assert (progress.removed, progress.done) == (2, 0)


def test_the_pair_is_split_on_the_first_bar() -> None:
    failures = RoutesProgress(1).feed(record(p.PT_NONE, "a|b|c"))

    assert (failures[0].origin_hub, failures[0].destination_hub) == ("a", "b|c")


def test_a_file_returns_each_complete_line_once_and_keeps_a_partial_one(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    file = ProgressFile(path)
    assert file.read_new() == []
    path.write_text('{"a": 1}\n{"b"', encoding="utf-8")

    assert file.read_new() == [{"a": 1}]
    assert file.read_new() == []
    with path.open("a", encoding="utf-8") as out:
        out.write(': 2}\n{"c": 3}\n')

    assert file.read_new() == [{"b": 2}, {"c": 3}]
    assert file.read_new() == []
