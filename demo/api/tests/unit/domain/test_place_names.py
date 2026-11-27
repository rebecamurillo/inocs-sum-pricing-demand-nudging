from pricing_demo.domain.place_names import MAX_LINES, normalise, place_lines
from pricing_demo.domain.read_model import StationRow


def stop(station_id: str, name: str, kind: str = "pt", lat: float = 46.2) -> StationRow:
    return StationRow(station_id, kind, name, lat, 6.1)  # type: ignore[arg-type]


def hubs(*rows: StationRow, hub: str = "H1") -> dict[str, str]:
    return {row.station_id: hub for row in rows}


def test_matching_ignores_case_and_accents() -> None:
    rows = [stop("a", "Gare Cornavin")]
    assert [line.name for line in place_lines("cornavín", rows, hubs(*rows))] == ["Gare Cornavin"]
    assert [line.name for line in place_lines("GARE CORN", rows, hubs(*rows))] == ["Gare Cornavin"]


def test_normalise_drops_accents_and_case() -> None:
    assert normalise("Étoile-Ça") == "etoile-ca"


def test_a_parent_station_and_its_platforms_are_one_line_at_the_lowest_station_id() -> None:
    rows = [stop("b", "Plainpalais", lat=46.3), stop("a", "Plainpalais", lat=46.1)]
    lines = place_lines("plain", rows, hubs(*rows))
    assert len(lines) == 1
    assert (lines[0].lat, lines[0].kind, lines[0].hub_id) == (46.1, "stop", "H1")


def test_the_same_name_in_another_kind_or_hub_is_another_line() -> None:
    rows = [stop("a", "Rive"), stop("b", "Rive", "bs"), stop("c", "Rive")]
    links = {"a": "H1", "b": "H1", "c": "H2"}
    lines = place_lines("rive", rows, links)
    assert sorted((line.kind, line.hub_id) for line in lines) == [
        ("bike_station", "H1"),
        ("stop", "H1"),
        ("stop", "H2"),
    ]


def test_a_station_that_belongs_to_no_hub_is_left_out() -> None:
    assert place_lines("rive", [stop("a", "Rive")], {}) == []


def test_names_that_start_with_the_text_come_first_then_alphabetical() -> None:
    rows = [
        stop("1", "Zeta Rive"),
        stop("2", "Rive Gauche"),
        stop("3", "Alpha Rive"),
        stop("4", "Rive"),
    ]
    names = [line.name for line in place_lines("rive", rows, hubs(*rows))]
    assert names == ["Rive", "Rive Gauche", "Alpha Rive", "Zeta Rive"]


def test_at_most_ten_lines_come_back() -> None:
    rows = [stop(str(n), f"Stop {n:02d}") for n in range(15)]
    assert len(place_lines("stop", rows, hubs(*rows))) == MAX_LINES


def test_a_query_shorter_than_two_characters_has_no_line() -> None:
    rows = [stop("a", "Rive")]
    assert place_lines("r", rows, hubs(*rows)) == []
    assert place_lines(" r ", rows, hubs(*rows)) == []
    assert place_lines("", rows, hubs(*rows)) == []


def test_bike_stations_are_named_bike_station() -> None:
    rows = [stop("a", "Rive bikes", "bs")]
    assert place_lines("rive", rows, hubs(*rows))[0].kind == "bike_station"
