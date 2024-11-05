from __future__ import annotations

import json
from typing import Annotated, Any, Dict, get_args

import tyro

json_constructor_spec = tyro.constructors.PrimitiveConstructorSpec(
    nargs=1,
    metavar="JSON",
    instance_from_str=lambda args: json.loads(args[0]),
    is_instance=lambda x: isinstance(x, dict),
    str_from_instance=lambda x: [json.dumps(x)],
)


def test_custom_primitive_registry():
    """Test that we can use a custom primitive registry to parse a custom type."""
    primitive_registry = tyro.constructors.ConstructorRegistry()

    @primitive_registry.primitive_rule
    def json_dict_spec(
        type_info: tyro.constructors.PrimitiveTypeInfo,
    ) -> tyro.constructors.PrimitiveConstructorSpec | None:
        if not (
            type_info.type_origin is dict and get_args(type_info.type) == (str, Any)
        ):
            return None
        return json_constructor_spec

    def main(x: Dict[str, Any]) -> Dict[str, Any]:
        return x

    with primitive_registry:
        assert tyro.cli(main, args=["--x", '{"a": 1}']) == {"a": 1}


def test_custom_primitive_annotated():
    """Test that we can use typing.Annotated to specify custom constructors."""

    def main(x: Annotated[Dict[str, Any], json_constructor_spec]) -> Dict[str, Any]:
        return x

    assert tyro.cli(main, args=["--x", '{"a": 1}']) == {"a": 1}