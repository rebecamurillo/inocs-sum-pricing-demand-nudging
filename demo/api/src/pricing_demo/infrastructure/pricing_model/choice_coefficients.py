"""The twelve choice-model constants of the package's solver, read from its source text with
`ast` (ARCHITECTURE.md § 6.4). Standard library only: the worker reads them in a child that
holds the package's folder, and this module is imported there without the package.
"""

import ast

from pricing_demo.domain.package_fingerprint import CHOICE_COEFFICIENT_NAMES


def _number(node: ast.expr) -> float | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        inner = _number(node.operand)
        if inner is None:
            return None
        return -inner if isinstance(node.op, ast.USub) else inner
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    ):
        return float(node.value)
    return None


def read_choice_coefficients(source: str) -> dict[str, float | None]:
    """The value of each of the twelve names, assigned anywhere in `source` as a single name
    equal to a numeric constant; a name that is not assigned so is `None`. The last assignment
    wins."""
    found: dict[str, float | None] = dict.fromkeys(CHOICE_COEFFICIENT_NAMES)
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in found
        ):
            value = _number(node.value)
            if value is not None:
                found[node.targets[0].id] = value
    return found
