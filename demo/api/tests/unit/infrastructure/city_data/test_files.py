import hashlib
from pathlib import Path

from pricing_demo.infrastructure.city_data.files import LocalDatasetFiles


def test_a_file_is_copied_into_the_data_set_folder_and_returned_relative(tmp_path: Path) -> None:
    source = tmp_path / "in" / "feed.zip"
    source.parent.mkdir()
    source.write_bytes(b"timetable")
    files = LocalDatasetFiles(tmp_path / "data")

    relative = files.copy_in("geneva-2026-11-26", source)

    assert relative == Path("datasets/geneva-2026-11-26/feed.zip")
    assert (tmp_path / "data" / relative).read_bytes() == b"timetable"
    assert files.resolve(str(relative)) == tmp_path / "data" / relative
    assert files.relative(tmp_path / "data" / relative) == str(relative)


def test_the_hash_is_the_sha256_of_the_content_in_chunks(tmp_path: Path) -> None:
    big = tmp_path / "big.bin"
    content = b"abc" * 700_000
    big.write_bytes(content)

    assert LocalDatasetFiles(tmp_path).sha256(big) == hashlib.sha256(content).hexdigest()


def test_removing_a_data_set_removes_its_folder_and_nothing_else(tmp_path: Path) -> None:
    files = LocalDatasetFiles(tmp_path)
    files.folder("a").joinpath("x").write_text("x")
    files.folder("b").joinpath("y").write_text("y")

    files.remove("a")
    files.remove("never-existed")

    assert not (tmp_path / "datasets" / "a").exists()
    assert (tmp_path / "datasets" / "b" / "y").exists()


def test_a_folder_is_claimed_once(tmp_path: Path) -> None:
    files = LocalDatasetFiles(tmp_path / "data")

    assert files.claim("geneva-2026-11-26") is True
    assert files.claim("geneva-2026-11-26") is False
    assert (tmp_path / "data" / "datasets" / "geneva-2026-11-26").is_dir()
