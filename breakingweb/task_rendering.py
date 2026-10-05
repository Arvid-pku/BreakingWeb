from __future__ import annotations

import re
from typing import Any

_TARGET_REF_RE = re.compile(r"^\{target\.([^}]+)\}$")


def render_template(value: Any, targets: dict[str, Any]) -> Any:
    """Recursively substitute {target.foo} placeholders in nested structures."""
    if isinstance(value, str):
        exact = _TARGET_REF_RE.match(value)
        if exact:
            return targets.get(exact.group(1), value)
        rendered = value
        for key, replacement in targets.items():
            rendered = rendered.replace(f"{{target.{key}}}", str(replacement))
        return rendered
    if isinstance(value, list):
        return [render_template(item, targets) for item in value]
    if isinstance(value, dict):
        return {key: render_template(item, targets) for key, item in value.items()}
    return value
