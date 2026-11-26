import hashlib
from collections.abc import Sequence
from pathlib import Path

import pytest

from pricing_demo.infrastructure.pricing_model.package_fingerprint import (
    PackageFingerprintReader,
    hash_sources,
)


def write(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def test_the_hash_does_not_depend_on_the_order_the_files_were_written(tmp_path: Path) -> None:
    first = write(tmp_path / "a", {"x.py": "1", "sub/y.py": "2"})
    second = write(tmp_path / "b", {"sub/y.py": "2", "x.py": "1"})

    assert hash_sources(first, "c") == hash_sources(second, "c")


def test_the_hash_follows_the_contents_the_paths_and_the_commit(tmp_path: Path) -> None:
    base = hash_sources(write(tmp_path / "a", {"x.py": "1"}), "c")

    assert hash_sources(write(tmp_path / "b", {"x.py": "2"}), "c") != base
    assert hash_sources(write(tmp_path / "c", {"z.py": "1"}), "c") != base
    assert hash_sources(tmp_path / "a", "d") != base


def test_the_hash_is_a_sha256_of_the_sorted_paths_and_contents_then_the_commit(
    tmp_path: Path,
) -> None:
    root = write(tmp_path, {"b.py": "B", "a.py": "A"})
    digest = hashlib.sha256()
    for name, content in (("a.py", b"A"), ("b.py", b"B")):
        digest.update(name.encode() + b"\0" + str(len(content)).encode() + b"\0" + content)
    digest.update(b"commit")

    assert hash_sources(root, "commit") == digest.hexdigest()


def test_caches_and_build_metadata_are_not_sources(tmp_path: Path) -> None:
    base = hash_sources(write(tmp_path / "a", {"x.py": "1"}), "c")
    noisy = write(
        tmp_path / "b",
        {
            "x.py": "1",
            "__pycache__/x.cpython-313.pyc": "bytes",
            "pkg/__pycache__/y.txt": "cache",
            "x.pyc": "bytes",
            "pkg.egg-info/PKG-INFO": "meta",
        },
    )

    assert hash_sources(noisy, "c") == base


class Runner:
    def __init__(self, status: str = "", defaults: str = '{"InstanceParams": {"a": 1}}') -> None:
        self.status = status
        self.defaults = defaults
        self.calls: list[tuple[Sequence[str], Path]] = []

    def __call__(self, command: Sequence[str], folder: Path) -> str:
        self.calls.append((command, folder))
        if command[:2] == ["git", "rev-parse"]:
            return "abc123\n"
        if command[:2] == ["git", "status"]:
            return self.status
        return "noise from the import\n" + self.defaults + "\n"


def package(tmp_path: Path) -> Path:
    return write(
        tmp_path / "pkg",
        {"pyproject.toml": '[project]\nname = "p"\nversion = "1.2.3"\n', "src/p/m.py": "x"},
    )


def test_the_reader_assembles_the_fingerprint(tmp_path: Path) -> None:
    runner = Runner()

    fingerprint = PackageFingerprintReader(package(tmp_path), runner, "py").read()

    assert fingerprint.version == "1.2.3"
    assert fingerprint.git_commit == "abc123"
    assert fingerprint.git_dirty is False
    assert fingerprint.fingerprint == hash_sources(tmp_path / "pkg/src", "abc123")
    assert fingerprint.defaults == {"InstanceParams": {"a": 1}}


def test_the_git_commands_run_in_the_repository_and_the_defaults_in_an_isolated_child(
    tmp_path: Path,
) -> None:
    runner = Runner()

    PackageFingerprintReader(package(tmp_path), runner, "py").read()

    commands = [command for command, _ in runner.calls]
    assert commands[0] == ["git", "rev-parse", "HEAD"]
    assert commands[1] == ["git", "status", "--porcelain", str(tmp_path / "pkg")]
    assert commands[2][:3] == ["py", "-I", "-c"]
    assert {folder for _, folder in runner.calls} == {tmp_path}


def test_a_status_that_prints_anything_is_dirty(tmp_path: Path) -> None:
    runner = Runner(status=" M src/p/m.py\n")

    assert PackageFingerprintReader(package(tmp_path), runner, "py").read().git_dirty is True


def test_a_failing_command_fails_the_read(tmp_path: Path) -> None:
    def failing(command: Sequence[str], folder: Path) -> str:
        raise OSError("git is not installed")

    with pytest.raises(OSError, match="git"):
        PackageFingerprintReader(package(tmp_path), failing, "py").read()
