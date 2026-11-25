"""A bare `__import__(...)` call escapes ruff's TID251, which bans only names it can resolve.

`importlib.import_module` and `builtins.__import__` are banned by ruff (pyproject.toml); this
test closes the one spelling ruff cannot see. Only the model adapter may import by name.
"""

import ast
from pathlib import Path

import pricing_demo

SOURCE = Path(pricing_demo.__file__).parent
ALLOWED = Path("infrastructure") / "pricing_model"


def bare_dynamic_imports(root: Path) -> list[str]:
    return [
        f"{path.relative_to(root)}:{node.lineno}"
        for path in sorted(root.rglob("*.py"))
        if ALLOWED not in path.relative_to(root).parents
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "__import__"
    ]


def test_no_module_outside_the_model_adapter_imports_by_name() -> None:
    assert bare_dynamic_imports(SOURCE) == []


def test_a_bare_dynamic_import_is_found_outside_the_model_adapter(tmp_path: Path) -> None:
    (tmp_path / "infrastructure" / "pricing_model").mkdir(parents=True)
    (tmp_path / "interface").mkdir()
    (tmp_path / "interface" / "bad.py").write_text('__import__("os")\n', encoding="utf-8")
    allowed = tmp_path / "infrastructure" / "pricing_model" / "ok.py"
    allowed.write_text('__import__("os")\n', encoding="utf-8")

    assert bare_dynamic_imports(tmp_path) == ["interface/bad.py:1"]
