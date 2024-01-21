"""Implement a tiny subset of dataclasses_json for config."""
from collections.abc import Mapping, Sequence
from dataclasses import asdict, fields, is_dataclass
from typing import Any, Dict, Type


class DataClassJsonMixin:
    """Adds from_dict to dataclass."""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Any:
        """Parse dataclasses recursively."""
        kwargs: Dict[str, Any] = {}

        cls_fields = {field.name: field for field in fields(cls)}
        for key, value in data.items():
            if key not in cls_fields:
                # Skip unknown fields
                continue

            field = cls_fields[key]
            if is_dataclass(field.type):
                assert issubclass(field.type, DataClassJsonMixin), field.type
                kwargs[key] = field.type.from_dict(value)
            else:
                kwargs[key] = _decode(value, field.type)

        # Fill in optional fields with None
        for field in cls_fields.values():
            if (field.name not in kwargs) and _is_optional(field.type):
                kwargs[field.name] = None

        return cls(**kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Alias for asdict."""
        return asdict(self)


def _decode(value: Any, target_type: Type) -> Any:
    """Decode value using (possibly generic) type."""
    if is_dataclass(target_type):
        assert issubclass(target_type, DataClassJsonMixin), target_type
        return target_type.from_dict(value) if value is not None else None

    if hasattr(target_type, "__args__"):
        # Optional[T]
        if type(None) in target_type.__args__:
            optional_type = target_type.__args__[0]
            return _decode(value, optional_type)

        # List[T]
        if isinstance(value, Sequence):
            list_type = target_type.__args__[0]
            return [_decode(item, list_type) for item in value]

        # Dict[str, T]
        if isinstance(value, Mapping):
            value_type = target_type.__args__[1]
            return {
                map_key: _decode(map_value, value_type)
                for map_key, map_value in value.items()
            }

    return value


def _is_optional(target_type: Type):
    """True if type is Optional"""
    return hasattr(target_type, "__args__") and (type(None) in target_type.__args__)
