"""Adding an error to the domain or the application without giving it a status fails here."""

import importlib
import pkgutil

from pricing_demo.application.errors import ComponentNotControllable, InvalidProbeSet
from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.runs import (
    InvalidRunTransition,
    InvalidStepTransition,
    RunAlreadyFinished,
    RunNotFound,
)
from pricing_demo.domain.system_status import IncompleteSystemStatus, InvalidComponentStatus
from pricing_demo.interface.http.problems import DOMAIN_PROBLEMS

LAYERS = ("pricing_demo.domain", "pricing_demo.application")


def import_every_module(package_name: str) -> None:
    package = importlib.import_module(package_name)
    for module in pkgutil.walk_packages(package.__path__, prefix=f"{package_name}."):
        importlib.import_module(module.name)


def subclasses(error: type[DomainError]) -> list[type[DomainError]]:
    found: list[type[DomainError]] = []
    for child in error.__subclasses__():
        found.extend([child, *subclasses(child)])
    return found


def declared_errors() -> list[type[DomainError]]:
    for layer in LAYERS:
        import_every_module(layer)
    return [
        error
        for error in subclasses(DomainError)
        if error.__module__.startswith(tuple(f"{layer}." for layer in LAYERS))
    ]


def test_the_walk_finds_the_errors_the_domain_and_the_application_declare() -> None:
    assert {
        InvalidComponentStatus,
        IncompleteSystemStatus,
        ComponentNotControllable,
        InvalidProbeSet,
        InvalidRunTransition,
        InvalidStepTransition,
        RunNotFound,
        RunAlreadyFinished,
    } <= set(declared_errors())


def test_every_error_of_the_domain_and_the_application_has_an_explicit_mapping() -> None:
    unmapped = [error.__qualname__ for error in declared_errors() if error not in DOMAIN_PROBLEMS]

    assert unmapped == []
