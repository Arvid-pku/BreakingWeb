"""Read-only views over state, targets, and entity dicts.

Two wrappers:
* ``FrozenDotMap`` — immutable mapping with ``obj.key`` and ``obj['key']`` access.
* ``ReadOnlyProxy`` — recursive proxy for typed state objects.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any


_PRIMITIVE = (str, bytes, int, float, bool, type(None))


class FrozenDotMap(Mapping[str, Any]):
    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_data", {str(k): readonly(v) for k, v in data.items()})

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name) from None

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        return self._data.get(key, default)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("evaluation views are read-only")

    def __repr__(self) -> str:
        return f"FrozenDotMap({self._data!r})"


class ReadOnlyProxy:
    """Recursive read-only proxy for runtime state objects."""

    __slots__ = ("_obj",)

    def __init__(self, obj: Any) -> None:
        object.__setattr__(self, "_obj", obj)

    @property
    def __wrapped__(self) -> Any:  # pragma: no cover
        return object.__getattribute__(self, "_obj")

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        return readonly(getattr(object.__getattribute__(self, "_obj"), name))

    def __getitem__(self, key: Any) -> Any:
        return readonly(object.__getattribute__(self, "_obj")[key])

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("state is read-only during evaluation")

    def __iter__(self):
        for item in object.__getattribute__(self, "_obj"):
            yield readonly(item)

    def __len__(self) -> int:
        return len(object.__getattribute__(self, "_obj"))

    def __contains__(self, item: object) -> bool:
        return item in object.__getattribute__(self, "_obj")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return readonly(object.__getattribute__(self, "_obj")(*args, **kwargs))

    def __bool__(self) -> bool:
        return bool(object.__getattribute__(self, "_obj"))

    def __eq__(self, other: Any) -> bool:
        raw = object.__getattribute__(self, "_obj")
        if isinstance(other, ReadOnlyProxy):
            other = object.__getattribute__(other, "_obj")
        return raw == other

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __lt__(self, other: Any) -> bool:
        return object.__getattribute__(self, "_obj") < unwrap(other)

    def __le__(self, other: Any) -> bool:
        return object.__getattribute__(self, "_obj") <= unwrap(other)

    def __gt__(self, other: Any) -> bool:
        return object.__getattribute__(self, "_obj") > unwrap(other)

    def __ge__(self, other: Any) -> bool:
        return object.__getattribute__(self, "_obj") >= unwrap(other)

    def __add__(self, other: Any) -> Any:
        return object.__getattribute__(self, "_obj") + unwrap(other)

    def __radd__(self, other: Any) -> Any:
        return unwrap(other) + object.__getattribute__(self, "_obj")

    def __sub__(self, other: Any) -> Any:
        return object.__getattribute__(self, "_obj") - unwrap(other)

    def __rsub__(self, other: Any) -> Any:
        return unwrap(other) - object.__getattribute__(self, "_obj")

    def __mul__(self, other: Any) -> Any:
        return object.__getattribute__(self, "_obj") * unwrap(other)

    def __rmul__(self, other: Any) -> Any:
        return unwrap(other) * object.__getattribute__(self, "_obj")

    def __truediv__(self, other: Any) -> Any:
        return object.__getattribute__(self, "_obj") / unwrap(other)

    def __rtruediv__(self, other: Any) -> Any:
        return unwrap(other) / object.__getattribute__(self, "_obj")

    def __mod__(self, other: Any) -> Any:
        return object.__getattribute__(self, "_obj") % unwrap(other)

    def __rmod__(self, other: Any) -> Any:
        return unwrap(other) % object.__getattribute__(self, "_obj")

    def __hash__(self) -> int:
        return hash(object.__getattribute__(self, "_obj"))

    def __str__(self) -> str:
        return str(object.__getattribute__(self, "_obj"))

    def __repr__(self) -> str:
        return repr(object.__getattribute__(self, "_obj"))


class EntityView(FrozenDotMap):
    """Dict-backed view used for diff entries and invariant filters."""


def unwrap(value: Any) -> Any:
    if isinstance(value, ReadOnlyProxy):
        return object.__getattribute__(value, "_obj")
    return value


def readonly(value: Any) -> Any:
    if isinstance(value, (FrozenDotMap, ReadOnlyProxy)):
        return value
    if isinstance(value, _PRIMITIVE):
        return value
    if isinstance(value, Mapping):
        return FrozenDotMap(value)
    if isinstance(value, tuple):
        return tuple(readonly(v) for v in value)
    if isinstance(value, list):
        return tuple(readonly(v) for v in value)
    if isinstance(value, set):
        return frozenset(readonly(v) for v in value)
    return ReadOnlyProxy(value)


def get_value(obj: Any, field: str, default: Any = None) -> Any:
    obj = unwrap(obj)
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(field, default)
    return getattr(obj, field, default)


def dump_entity(entity: Any) -> dict[str, Any]:
    """Normalize a Pydantic model, dataclass, mapping, or simple object to a dict."""
    entity = unwrap(entity)
    if isinstance(entity, Mapping):
        return dict(entity)
    if hasattr(entity, "model_dump"):
        return dict(entity.model_dump())
    if is_dataclass(entity):
        return dict(asdict(entity))
    if hasattr(entity, "__dict__"):
        return {k: v for k, v in vars(entity).items() if not k.startswith("_")}
    raise TypeError(f"cannot dump entity of type {type(entity)!r}")


def is_entity_sequence(value: Any) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return False
    if not value:
        return True
    try:
        first = dump_entity(value[0])
    except TypeError:
        return False
    return "id" in first


def iter_public_state_fields(state: Any) -> Iterable[tuple[str, Any]]:
    """Yield ``(name, value)`` for each public state field."""
    state = unwrap(state)
    if isinstance(state, Mapping):
        yield from state.items()
        return
    if hasattr(type(state), "model_fields"):
        for name in type(state).model_fields:
            yield name, getattr(state, name)
        return
    if hasattr(state, "__dict__"):
        for name, value in vars(state).items():
            if not name.startswith("_"):
                yield name, value
