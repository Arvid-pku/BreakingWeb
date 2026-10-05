"""Single expression sandbox for all evaluator paths."""

from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from types import CodeType
from typing import Any, Mapping

from .access import FrozenDotMap, readonly


class SafeEvalError(Exception):
    """Expression failed safety validation or evaluation."""


SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "frozenset": frozenset,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "next": next,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "Decimal": Decimal,
    "datetime": datetime,
    "timedelta": timedelta,
    "timezone": timezone,
    "True": True,
    "False": False,
    "None": None,
}

_FORBIDDEN_NAMES = {
    "__builtins__", "__debug__", "breakpoint", "compile", "dir",
    "eval", "exec", "globals", "help", "input", "locals",
    "memoryview", "open", "quit", "super", "type", "vars", "__import__",
}

_FORBIDDEN_NODES = (
    ast.Await, ast.Delete, ast.Global, ast.Import, ast.ImportFrom,
    ast.NamedExpr, ast.Nonlocal, ast.Yield, ast.YieldFrom,
)

_TARGET_RE = re.compile(r"\{target\.([^}]+)\}")


def _validate_ast(tree: ast.AST, *, max_nodes: int = 2000) -> None:
    count = 0
    for node in ast.walk(tree):
        count += 1
        if count > max_nodes:
            raise SafeEvalError(f"expression too large: >{max_nodes} AST nodes")
        if isinstance(node, _FORBIDDEN_NODES):
            raise SafeEvalError(f"forbidden expression node: {type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id.startswith("__") or node.id in _FORBIDDEN_NAMES:
                raise SafeEvalError(f"forbidden name: {node.id}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                raise SafeEvalError(f"forbidden attribute: {node.attr}")


def validate_expression(source: str) -> ast.Expression:
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise SafeEvalError(f"syntax error: {exc.msg}") from exc
    assert isinstance(tree, ast.Expression)
    _validate_ast(tree)
    return tree


@lru_cache(maxsize=4096)
def _compile_validated(source: str) -> CodeType:
    tree = validate_expression(source)
    return compile(tree, "<safe-eval>", "eval")


def safe_eval(
    source: str,
    bindings: Mapping[str, Any] | None = None,
    *,
    extra_builtins: Mapping[str, Any] | None = None,
) -> Any:
    """Evaluate a trusted-author expression with restricted globals.

    This is NOT a general-purpose security sandbox. It is a restricted
    evaluator for trusted task-author expressions only. The expression
    string is AST-validated to reject imports, dunder access, and
    forbidden builtins before execution. Bindings are placed in globals
    so comprehension scopes can see them.
    """
    code = _compile_validated(source)
    builtins = dict(SAFE_BUILTINS)
    if extra_builtins:
        for key, value in extra_builtins.items():
            if key.startswith("__") or key in _FORBIDDEN_NAMES:
                raise SafeEvalError(f"forbidden builtin override: {key}")
            builtins[key] = value
    globs: dict[str, Any] = {"__builtins__": builtins}
    for key, value in dict(bindings or {}).items():
        if key.startswith("__"):
            raise SafeEvalError(f"forbidden binding name: {key}")
        globs[key] = value
    try:
        return _restricted_execute(code, globs)
    except SafeEvalError:
        raise
    except Exception as exc:
        raise SafeEvalError(str(exc)) from exc


def _restricted_execute(code: Any, globs: dict[str, Any]) -> Any:
    return eval(code, globs, {})  # noqa: S307 — AST-validated, restricted builtins


def sanitize_target_value(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def resolve_dotted(mapping: Mapping[str, Any], dotted: str) -> Any:
    value: Any = mapping
    for part in dotted.split("."):
        if isinstance(value, Mapping):
            value = value.get(part)
        else:
            value = getattr(value, part, None)
        if value is None:
            return None
    return value


def substitute_target_templates(expr: str, targets: Mapping[str, Any]) -> str:
    """Legacy ``{target.x}`` string-level substitution."""

    def replace(match: re.Match[str]) -> str:
        value = resolve_dotted(targets, match.group(1))
        if value is None:
            return match.group(0)
        if isinstance(value, str):
            return sanitize_target_value(value)
        return repr(value)

    return _TARGET_RE.sub(replace, expr)


def target_view(targets: Mapping[str, Any]) -> FrozenDotMap:
    return readonly(dict(targets))  # type: ignore[return-value]
