"""What import-linter cannot say: an inner layer imports an allowlist, not "everything but".

import-linter forbids named packages, so a package nobody thought of passes. Here a layer may
import the standard library, the pricing_demo packages listed for it and the third-party
packages listed for it, and nothing else.
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

import pricing_demo

SOURCE = Path(pricing_demo.__file__).parent


@dataclass(frozen=True)
class Allowed:
    internal: tuple[str, ...]
    external: tuple[str, ...] = ()


# layer -> what it may import besides the standard library
ALLOWED = {
    "domain": Allowed(internal=("pricing_demo.domain",)),
    "application": Allowed(internal=("pricing_demo.application", "pricing_demo.domain")),
    "interface": Allowed(
        internal=("pricing_demo.interface", "pricing_demo.application", "pricing_demo.domain"),
        external=("fastapi", "pydantic"),
    ),
}


def imported_modules(path: Path) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
    return modules


def is_inside(module: str, package: str) -> bool:
    return module == package or module.startswith(f"{package}.")


def is_allowed(module: str, allowed: Allowed) -> bool:
    if module.split(".")[0] in sys.stdlib_module_names:
        return True
    return any(is_inside(module, package) for package in (*allowed.internal, *allowed.external))


def offences(layer: str, root: Path = SOURCE) -> list[str]:
    return [
        f"{path.relative_to(root)} imports {module}"
        for path in sorted((root / layer).rglob("*.py"))
        for module in imported_modules(path)
        if not is_allowed(module, ALLOWED[layer])
    ]


def layer_importing(tmp_path: Path, layer: str, module: str) -> Path:
    """A copy of nothing but one module of `layer` that imports `module`."""
    (tmp_path / layer).mkdir()
    (tmp_path / layer / "module.py").write_text(f"import {module}\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("layer", sorted(ALLOWED))
def test_a_layer_imports_only_what_it_is_allowed_to(layer: str) -> None:
    assert offences(layer) == []


@pytest.mark.parametrize("module", ["pandas", "requests", "starlette.responses", "sqlalchemy"])
def test_the_interface_layer_refuses_a_package_nobody_listed(module: str, tmp_path: Path) -> None:
    root = layer_importing(tmp_path, "interface", module)

    assert offences("interface", root) == [f"interface/module.py imports {module}"]


@pytest.mark.parametrize(
    "module",
    ["fastapi", "fastapi.exceptions", "pydantic", "pricing_demo.application.errors", "http"],
)
def test_the_interface_layer_accepts_what_is_listed(module: str, tmp_path: Path) -> None:
    root = layer_importing(tmp_path, "interface", module)

    assert offences("interface", root) == []


@pytest.mark.parametrize("module", ["fastapi", "pricing_demo.interface.http.app"])
def test_the_application_layer_refuses_the_packages_of_the_layers_outside_it(
    module: str, tmp_path: Path
) -> None:
    root = layer_importing(tmp_path, "application", module)

    assert offences("application", root) == [f"application/module.py imports {module}"]


def test_a_package_that_only_shares_a_prefix_is_not_the_package() -> None:
    assert not is_inside("pydantic_settings", "pydantic")
    assert not is_inside("pricing_demo.domains", "pricing_demo.domain")
