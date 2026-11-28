"""Reads what the pricing package is: a hash of its sources and the repository commit, its
version, the defaults of its configuration dataclasses and the solver's twelve choice-model
coefficients.

The defaults and the coefficients are read in a child process: importing the package loads
its heavy dependencies, and the worker process stays free of them.
"""

import hashlib
import json
import subprocess
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from pricing_demo.domain.package_fingerprint import CHOICE_COEFFICIENT_NAMES, PackageFingerprint

# Runs a command in a folder and returns its standard output; raises when it fails.
CommandRunner = Callable[[Sequence[str], Path], str]

DEFAULTS_SCRIPT = """
import dataclasses, json
from pathlib import Path
from sum_nsm_dynamic_pricing.config import InstanceParams, OptimizerParams, PipelineConfig

def plain(value):
    return str(value) if isinstance(value, Path) else value

print(json.dumps({
    cls.__name__: {
        field.name: plain(field.default)
        for field in dataclasses.fields(cls)
        if field.default is not dataclasses.MISSING
    }
    for cls in (PipelineConfig, InstanceParams, OptimizerParams)
}))
"""

# Locates the installed solver's source and reads its coefficients with `ast`; neither the
# package nor its solver module is imported.
COEFFICIENTS_SCRIPT = """
import importlib.util, json
from pathlib import Path
from pricing_demo.infrastructure.pricing_model.choice_coefficients import read_choice_coefficients

origin = importlib.util.find_spec("sum_nsm_dynamic_pricing").origin
solver = Path(origin).parent / "optimizer" / "solver.py"
print(json.dumps(read_choice_coefficients(solver.read_text(encoding="utf-8"))))
"""


def run_command(command: Sequence[str], folder: Path) -> str:
    completed = subprocess.run(  # fixed commands, never built from input
        command, cwd=folder, capture_output=True, text=True, check=True, timeout=120
    )
    return completed.stdout


def hash_sources(source_dir: Path, commit: str) -> str:
    """The sha256 over the sorted relative paths and contents of the source files, then the
    commit. Bytecode caches and build metadata are not sources."""
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file()
        and path.suffix != ".pyc"
        and "__pycache__" not in path.parts
        and not any(part.endswith(".egg-info") for part in path.parts)
    )
    for path in files:
        content = path.read_bytes()
        digest.update(path.relative_to(source_dir).as_posix().encode())
        digest.update(b"\0" + str(len(content)).encode() + b"\0")
        digest.update(content)
    digest.update(commit.encode())
    return digest.hexdigest()


class PackageFingerprintReader:
    def __init__(
        self,
        package_dir: Path,
        run: CommandRunner = run_command,
        python: str = sys.executable,
    ) -> None:
        self._package_dir = package_dir
        self._run = run
        self._python = python

    def read(self) -> PackageFingerprint:
        repository = self._package_dir.parent
        commit = self._run(["git", "rev-parse", "HEAD"], repository).strip()
        dirty = bool(
            self._run(["git", "status", "--porcelain", str(self._package_dir)], repository).strip()
        )
        pyproject = tomllib.loads((self._package_dir / "pyproject.toml").read_text("utf-8"))
        return PackageFingerprint(
            fingerprint=hash_sources(self._package_dir / "src", commit),
            version=str(pyproject["project"]["version"]),
            git_commit=commit,
            git_dirty=dirty,
            defaults=self._defaults(),
            choice_coefficients=self._choice_coefficients(),
        )

    def _defaults(self) -> Mapping[str, Mapping[str, object]]:
        output = self._run([self._python, "-I", "-c", DEFAULTS_SCRIPT], self._package_dir.parent)
        # The package may print while it imports: the answer is the last line.
        return json.loads(output.strip().splitlines()[-1])  # type: ignore[no-any-return]

    def _choice_coefficients(self) -> Mapping[str, float | None]:
        output = self._run(
            [self._python, "-I", "-c", COEFFICIENTS_SCRIPT], self._package_dir.parent
        )
        found = json.loads(output.strip().splitlines()[-1])
        # Only the twelve names count: any other answer reads as twelve missing ones.
        return {
            name: found.get(name) if isinstance(found, dict) else None
            for name in CHOICE_COEFFICIENT_NAMES
        }
