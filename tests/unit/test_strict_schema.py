"""The strict structured-output schema (PRD D-02, FR-003.4; Phase 2 step 10a; B-224)."""

import copy
import json

from credit_intel.llm.provider import STRUCTURED_OUTPUT_MODE
from credit_intel.llm.strict_schema import ADAPTER_VERSION, strict_schema
from credit_intel.models import ExtractionResponse

DROPPED = {
    "title", "default", "description", "minLength", "maxLength", "pattern", "format", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minItems", "maxItems", "uniqueItems",
}  # fmt: skip
SOURCE = ExtractionResponse.model_json_schema()
STRICT = strict_schema(SOURCE)


def schema_nodes(node, path=""):
    """Every schema object (not the name maps) with its path."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            if key in ("properties", "$defs"):
                for name, child in value.items():
                    yield from schema_nodes(child, f"{path}/{key}/{name}")
            else:
                yield from schema_nodes(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from schema_nodes(item, f"{path}[{index}]")


def test_the_version_is_part_of_the_cache_keys_structured_output_mode():
    assert ADAPTER_VERSION == "1" and STRUCTURED_OUTPUT_MODE == "json_schema.v1"


def test_every_object_lists_all_its_properties_as_required_and_refuses_extras():
    objects = [(p, n) for p, n in schema_nodes(STRICT) if "properties" in n]

    assert len(objects) == 3  # the response, an attribute and a field
    for path, node in objects:
        assert node["required"] == list(node["properties"]), path
        assert node["additionalProperties"] is False, path


def test_the_optional_property_becomes_nullable_and_the_required_ones_do_not():
    attribute = STRICT["$defs"]["ProposedAttribute"]["properties"]

    assert {"type": "null"} in attribute["period_role"]["anyOf"]
    assert {"$ref": "#/$defs/PeriodRole"} in attribute["period_role"]["anyOf"]
    assert attribute["raw_text"] == {"type": "string"}
    assert attribute["attribute"] == {"$ref": "#/$defs/DocumentAttributeName"}
    field = STRICT["$defs"]["ProposedField"]["properties"]
    assert field["period_role"] == {"$ref": "#/$defs/PeriodRole"}  # required in the model, so not nullable


def test_keywords_the_provider_does_not_accept_are_removed_everywhere():
    for path, node in schema_nodes(STRICT):
        assert not DROPPED & set(node), (path, DROPPED & set(node))


def test_property_names_that_look_like_keywords_are_kept():
    schema = {"type": "object", "properties": {"title": {"type": "string"}, "default": {"type": "integer"}},
              "required": ["title"]}  # fmt: skip

    converted = strict_schema(schema)

    assert list(converted["properties"]) == ["title", "default"]
    assert converted["properties"]["default"]["type"] == ["integer", "null"]
    assert converted["required"] == ["title", "default"]


def test_enums_and_references_are_kept_intact():
    assert STRICT["$defs"]["Scale"]["enum"] == SOURCE["$defs"]["Scale"]["enum"]
    assert STRICT["$defs"]["PeriodRole"] == {"enum": ["current", "comparative"], "type": "string"}
    assert STRICT["properties"]["fields"]["items"] == {"$ref": "#/$defs/ProposedField"}
    assert set(STRICT["$defs"]) == set(SOURCE["$defs"])


def test_every_reference_resolves():
    refs = {n["$ref"] for _, n in schema_nodes(STRICT) if "$ref" in n}

    assert refs and all(ref.startswith("#/$defs/") and ref.split("/")[-1] in STRICT["$defs"] for ref in refs)


def test_the_root_is_an_object_with_the_two_lists():
    assert STRICT["type"] == "object" and list(STRICT["properties"]) == ["attributes", "fields"]
    assert all(STRICT["properties"][k]["type"] == "array" for k in ("attributes", "fields"))


def test_the_input_is_not_changed_and_the_result_is_stable():
    before = copy.deepcopy(SOURCE)

    first, second = strict_schema(SOURCE), strict_schema(SOURCE)

    assert SOURCE == before and first == second
    assert json.dumps(first, sort_keys=False) == json.dumps(second, sort_keys=False)


def test_converting_twice_changes_nothing_more():
    assert strict_schema(STRICT) == STRICT


def test_other_shapes_are_made_nullable_correctly():
    schema = {
        "type": "object",
        "properties": {
            "a": {"type": "string", "enum": ["x", "y"]},
            "b": {"type": ["integer", "string"]},
            "c": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "d": {"$ref": "#/$defs/D"},
            "e": {"enum": [1, 2]},
        },
        "required": [],
    }  # fmt: skip

    p = strict_schema(schema)["properties"]

    assert p["a"] == {"type": ["string", "null"], "enum": ["x", "y", None]}
    assert p["b"]["type"] == ["integer", "string", "null"]
    assert p["c"] == {"anyOf": [{"type": "integer"}, {"type": "null"}]}  # already nullable, once
    assert p["d"] == {"anyOf": [{"$ref": "#/$defs/D"}, {"type": "null"}]}
    assert p["e"] == {"anyOf": [{"enum": [1, 2]}, {"type": "null"}]}


def test_a_reply_the_model_may_give_fits_the_converted_shape():
    reply = {"attributes": [{"attribute": "scale", "period_role": None, "raw_text": "in crore",
                             "normalised_value": "crore", "page_number": 1, "evidence_quote": "(in crore)"}],
             "fields": []}  # fmt: skip

    ExtractionResponse.model_validate(reply)  # null period_role is accepted by the model
    keys = STRICT["$defs"]["ProposedAttribute"]["required"]
    assert set(reply["attributes"][0]) == set(keys)  # and every key is present, as strict mode wants


def test_objects_without_the_flag_are_closed_and_nested_objects_too():
    schema = {"type": "object", "properties": {"a": {"type": "object", "properties": {"b": {"type": "string"}}}},
              "required": ["a"]}  # fmt: skip

    converted = strict_schema(schema)

    assert converted["additionalProperties"] is False
    assert converted["properties"]["a"]["additionalProperties"] is False
    assert converted["properties"]["a"]["required"] == ["b"]
