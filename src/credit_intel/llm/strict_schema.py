"""Pydantic JSON schema to the strict structured-output form (PRD D-02, FR-003.4).

A hosted provider's strict JSON-schema mode asks for a narrower schema than Pydantic
writes: every object lists all its properties as required, optional ones are nullable,
extra properties are refused, and validation keywords the provider does not support are
left out. Python still validates every reply (FR-004), so dropping a keyword such as
``minLength`` loses nothing. The conversion is a pure function of the schema, and its
version is part of the structured-output mode in the response-cache key (FR-003.5), so a
change here can never replay a reply that was made under the old form.

The rules follow the provider's documented strict mode as I know it; they are confirmed
against its documentation at D-02 verification and by the first live call.
"""

from collections.abc import Mapping, Sequence
from typing import Any

ADAPTER_VERSION = "1"

# Keywords that describe or validate but are not accepted in strict mode.
_DROPPED = frozenset(
    {
        "title", "default", "description", "minLength", "maxLength", "pattern", "format",
        "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
        "minItems", "maxItems", "uniqueItems",
    }
)  # fmt: skip
_NULL = {"type": "null"}


def _nullable(node: dict[str, Any]) -> dict[str, Any]:
    """The node, also accepting null."""
    if "anyOf" in node:
        options = node["anyOf"]
        return node if _NULL in options else {**node, "anyOf": [*options, _NULL]}
    if "$ref" in node:
        return {"anyOf": [node, _NULL]}
    kind = node.get("type")
    if isinstance(kind, str):
        result = {**node, "type": [kind, "null"]}
    elif isinstance(kind, list):
        result = node if "null" in kind else {**node, "type": [*kind, "null"]}
    else:
        return {"anyOf": [node, _NULL]}
    if "enum" in result and None not in result["enum"]:
        result["enum"] = [*result["enum"], None]
    return result


def _convert(node: Any) -> Any:
    if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        return [_convert(item) for item in node]
    if not isinstance(node, Mapping):
        return node
    converted: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROPPED:
            continue
        if key in ("properties", "$defs"):  # the keys of these are names, never keywords
            converted[key] = {name: _convert(child) for name, child in value.items()}
        else:
            converted[key] = _convert(value)
    properties = converted.get("properties")
    if isinstance(properties, dict):
        required = set(node.get("required", ()))
        converted["properties"] = {
            name: child if name in required else _nullable(child) for name, child in properties.items()
        }
        converted["required"] = list(properties)
        converted["additionalProperties"] = False
    return converted


def strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """The schema in strict structured-output form. The input is not changed."""
    return _convert(schema)
