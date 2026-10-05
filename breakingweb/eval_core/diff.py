"""Environment-agnostic entity diff extraction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .access import dump_entity, iter_public_state_fields, unwrap


@dataclass(frozen=True)
class Create:
    entity: str
    entity_id: str
    fields: dict[str, Any]


@dataclass(frozen=True)
class Update:
    entity: str
    entity_id: str
    field_changes: dict[str, tuple[Any, Any]]


@dataclass(frozen=True)
class Delete:
    entity: str
    entity_id: str
    last_fields: dict[str, Any]


DiffEntry = Create | Update | Delete

_PRIMITIVE_TYPES = (str, int, float, bool)


def _strip_ignored(entity: Any, dumped: dict[str, Any]) -> dict[str, Any]:
    ignore = getattr(type(entity), "DIFF_IGNORE_FIELDS", ())
    if not ignore:
        return dumped
    return {k: v for k, v in dumped.items() if k not in ignore}


def _try_dump_entity_list(value: list) -> list[dict[str, Any]] | None:
    """Try to interpret a list as a list of entities (dicts with ``id``).

    Returns the dumped list, or ``None`` if any item is not dumpable or
    lacks an ``id`` key.
    """
    dumped: list[dict[str, Any]] = []
    for item in value:
        try:
            entity_dict = _strip_ignored(item, dump_entity(item))
        except TypeError:
            return None
        if "id" not in entity_dict:
            return None
        dumped.append(entity_dict)
    return dumped


_STATE_CLASS_BY_ENV: dict[str, type] | None = None


def _resolve_state_class(env_id: str) -> type | None:
    """Look up the state class for an env_id (lazy, cached)."""
    global _STATE_CLASS_BY_ENV
    if _STATE_CLASS_BY_ENV is None:
        _STATE_CLASS_BY_ENV = {}
        try:
            from breakingweb.backend.models.amazon import AmazonState
            from breakingweb.backend.models.booking import BookingState
            from breakingweb.backend.models.gmail import GmailState
            from breakingweb.backend.models.lms import LMSState
            from breakingweb.backend.models.patient_portal import PatientPortalState
            from breakingweb.backend.models.reddit import RedditState
            from breakingweb.backend.models.robinhood import RobinhoodState
            for cls in (AmazonState, BookingState, GmailState, LMSState,
                        PatientPortalState, RedditState, RobinhoodState):
                _STATE_CLASS_BY_ENV[cls.model_fields["env_id"].default or cls.__name__] = cls
            # Also alias by lowercased class basename
            _STATE_CLASS_BY_ENV.update({
                "amazon": AmazonState, "booking": BookingState, "gmail": GmailState,
                "lms": LMSState, "patient_portal": PatientPortalState,
                "reddit": RedditState, "robinhood": RobinhoodState,
            })
        except ImportError:
            pass
    return _STATE_CLASS_BY_ENV.get(env_id)


def _state_attr(state: Any, name: str, default: Any = ()) -> Any:
    """Read a state-class attribute, looking through dict snapshots via env_id."""
    raw = unwrap(state)
    if isinstance(raw, Mapping):
        env_id = raw.get("env_id")
        if env_id:
            cls = _resolve_state_class(env_id)
            if cls is not None:
                return getattr(cls, name, default)
        return default
    return getattr(type(raw), name, default)


def collections_of(state: Any) -> dict[str, list[dict[str, Any]]]:
    """Return entity collections as ``{collection_name: [entity_dict, ...]}``.

    Walks every public field of ``state``:

    * ``list[entity_with_id]`` → kept as-is (default; structural discovery).
    * ``list[primitive]`` (str/int/float/bool) → kept ONLY if the field name
      is listed in ``DIFF_DIFFABLE_PRIMITIVE_LISTS`` on the state class.
      Each item becomes ``{"id": str(item), "value": item}``. Used for
      primitive collections like ``state.wishlist`` and
      ``state.subscriptions``.
    * Singleton object (non-list, non-primitive) → kept ONLY if the field
      name is listed in ``DIFF_DIFFABLE_SINGLETONS``. Wrapped as a
      one-element collection with synthetic id ``__singleton_<name>__`` if
      the object lacks its own ``id``. Supports ``state.settings``,
      ``state.patient``.
    * Top-level primitive scalar (``state.owner_phone``) → kept ONLY if the
      field name is listed in ``DIFF_DIFFABLE_SCALARS``. Wrapped as
      ``[{"id": "__singleton_<name>__", "value": ...}]``.
    * Always-skipped: ``Mapping``, ``set``, ``tuple``, ``None``, anything
      listed in ``DIFF_IGNORE_FIELDS``.

    Opt-in is per-class (a state model lists which singleton/primitive-list
    fields should be diff-discoverable) so existing tasks aren't surprised
    by new diff entries on unrelated fields.
    """
    diffable_singletons = set(_state_attr(state, "DIFF_DIFFABLE_SINGLETONS", ()))
    diffable_primitive_lists = set(_state_attr(state, "DIFF_DIFFABLE_PRIMITIVE_LISTS", ()))
    diffable_scalars = set(_state_attr(state, "DIFF_DIFFABLE_SCALARS", ()))
    ignore = set(_state_attr(state, "DIFF_IGNORE_FIELDS", ()))

    out: dict[str, list[dict[str, Any]]] = {}
    for name, value in iter_public_state_fields(state):
        if name in ignore:
            continue

        if isinstance(value, list):
            if not value:
                # Preserve existing behavior: empty entity-typed lists keep
                # the slot for diff-by-presence. Empty primitive lists too,
                # but only if explicitly opted in.
                if name in diffable_primitive_lists:
                    out[name] = []
                else:
                    out[name] = []
                continue
            entities = _try_dump_entity_list(value)
            if entities is not None:
                out[name] = entities
                continue
            if name in diffable_primitive_lists and all(
                isinstance(item, _PRIMITIVE_TYPES) for item in value
            ):
                out[name] = [{"id": str(item), "value": item} for item in value]
                continue
            # Non-opt-in primitive lists or mixed lists → drop (existing behavior).
            continue

        if value is None:
            continue
        if isinstance(value, _PRIMITIVE_TYPES):
            if name in diffable_scalars:
                out[name] = [{"id": f"__singleton_{name}__", "value": value}]
            continue
        if isinstance(value, (set, tuple, bytes)):
            continue
        if isinstance(value, Mapping) and name not in diffable_singletons:
            # Generic mappings (e.g. id_counters) stay skipped unless explicitly opted in.
            continue

        if name not in diffable_singletons:
            continue
        try:
            entity_dict = _strip_ignored(value, dump_entity(value))
        except TypeError:
            continue
        entity_dict.setdefault("id", f"__singleton_{name}__")
        out[name] = [entity_dict]
    return out


def index_by_id(entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(e["id"]): e for e in entities if "id" in e}


def compute_diff(initial: Any, final: Any) -> list[DiffEntry]:
    before_cols = collections_of(initial)
    after_cols = collections_of(final)
    entries: list[DiffEntry] = []

    for collection in sorted(set(before_cols) | set(after_cols)):
        before = index_by_id(before_cols.get(collection, []))
        after = index_by_id(after_cols.get(collection, []))

        for entity_id in sorted(set(after) - set(before)):
            entries.append(Create(collection, entity_id, after[entity_id]))
        for entity_id in sorted(set(before) - set(after)):
            entries.append(Delete(collection, entity_id, before[entity_id]))
        for entity_id in sorted(set(before) & set(after)):
            fields = set(before[entity_id]) | set(after[entity_id])
            changes = {
                name: (before[entity_id].get(name), after[entity_id].get(name))
                for name in fields
                if before[entity_id].get(name) != after[entity_id].get(name)
            }
            if changes:
                entries.append(Update(collection, entity_id, changes))
    return entries


def collection_map_for(state: Any) -> dict[str, str]:
    """Map entity class names and collection names to collection names.

    Uses Pydantic model_fields type annotations when available (works
    even for empty lists), falling back to runtime introspection.
    """
    from typing import get_args, get_origin

    mapping: dict[str, str] = {}
    raw = unwrap(state)

    if hasattr(type(raw), "model_fields"):
        for field_name, field_info in type(raw).model_fields.items():
            annotation = field_info.annotation
            if get_origin(annotation) is list:
                args = get_args(annotation)
                if args and hasattr(args[0], "__name__"):
                    mapping.setdefault(args[0].__name__, field_name)
            mapping[field_name] = field_name

    for name, value in iter_public_state_fields(state):
        if not isinstance(value, list):
            continue
        mapping[name] = name
        if not value:
            continue
        cls_name = type(value[0]).__name__
        mapping.setdefault(cls_name, name)
    return mapping


def collection_for(entity_type: str, state: Any = None, explicit: str | None = None) -> str:
    if explicit:
        return explicit.removeprefix("state.")
    mapping = collection_map_for(state) if state is not None else {}
    if entity_type in mapping:
        return mapping[entity_type]
    lower = entity_type.lower()
    if lower.endswith("s"):
        return lower
    if lower.endswith("y"):
        return lower[:-1] + "ies"
    return lower + "s"
