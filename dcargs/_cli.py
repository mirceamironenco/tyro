"""Core public API."""
import argparse
import dataclasses
import sys
import warnings
from typing import Callable, Optional, Sequence, Type, TypeVar, Union, cast, overload

import shtab

from . import _argparse_formatter, _calling, _fields, _parsers, _strings, conf

OutT = TypeVar("OutT")


# Overload notes:
# 1. Type[T] is almost a subtype of Callable[..., T]; the difference is types like
#    Union[T1, T2] which fall under the former but not the latter.
# 2. We really shouldn't need an overload here. But as of 1.1.268, it seems like it's
#    needed for pyright to understand that Union types are OK to pass in directly.
#    Hopefully we can just switch to a Union[Type[...], Callable[...]] in the future.


@overload
def cli(
    f: Type[OutT],
    *,
    prog: Optional[str] = None,
    description: Optional[str] = None,
    args: Optional[Sequence[str]] = None,
    default: Optional[OutT] = None,
) -> OutT:
    ...


@overload
def cli(
    f: Callable[..., OutT],
    *,
    prog: Optional[str] = None,
    description: Optional[str] = None,
    args: Optional[Sequence[str]] = None,
    default: Optional[OutT] = None,
) -> OutT:
    ...


def cli(
    f: Union[Type[OutT], Callable[..., OutT]],
    *,
    prog: Optional[str] = None,
    description: Optional[str] = None,
    args: Optional[Sequence[str]] = None,
    default: Optional[OutT] = None,
    **deprecated_kwargs,
) -> OutT:
    """Call `f(...)`, with arguments populated from an automatically generated CLI
    interface.

    `f` should have type-annotated inputs, and can be a function or class. Note that if
    `f` is a class, `dcargs.cli()` returns an instance.

    The parser is generated by populating helptext from docstrings and types from
    annotations; a broad range of core type annotations are supported...
    - Types natively accepted by `argparse`: str, int, float, pathlib.Path, etc.
    - Default values for optional parameters.
    - Booleans, which are automatically converted to flags when provided a default
      value.
    - Enums (via `enum.Enum`).
    - Various annotations from the standard typing library. Some examples:
      - `typing.ClassVar[T]`.
      - `typing.Optional[T]`.
      - `typing.Literal[T]`.
      - `typing.Sequence[T]`.
      - `typing.List[T]`.
      - `typing.Dict[K, V]`.
      - `typing.Tuple`, such as `typing.Tuple[T1, T2, T3]` or
        `typing.Tuple[T, ...]`.
      - `typing.Set[T]`.
      - `typing.Final[T]` and `typing.Annotated[T]`.
      - `typing.Union[T1, T2]`.
      - Various nested combinations of the above: `Optional[Literal[T]]`,
        `Final[Optional[Sequence[T]]]`, etc.
    - Hierarchical structures via nested dataclasses, TypedDict, NamedTuple,
      classes.
      - Simple nesting.
      - Unions over nested structures (subparsers).
      - Optional unions over nested structures (optional subparsers).
    - Generics (including nested generics).

    Args:
        f: Callable.
        prog: The name of the program printed in helptext. Mirrors argument from
            `argparse.ArgumentParser()`.
        description: Description text for the parser, displayed when the --help flag is
            passed in. If not specified, `f`'s docstring is used. Mirrors argument from
            `argparse.ArgumentParser()`.
        args: If set, parse arguments from a sequence of strings instead of the
            commandline. Mirrors argument from `argparse.ArgumentParser.parse_args()`.
        default: An instance of `T` to use for default values; only supported
            if `T` is a dataclass, TypedDict, or NamedTuple. Helpful for merging CLI
            arguments with values loaded from elsewhere. (for example, a config object
            loaded from a yaml file)

    Returns:
        The output of `f(...)`.
    """
    if "default_instance" in deprecated_kwargs:
        warnings.warn(
            "`default_instance=` is deprecated! use `default=` instead.", stacklevel=2
        )
        default = deprecated_kwargs["default_instance"]
    if deprecated_kwargs.get("avoid_subparsers", False):
        f = conf.AvoidSubcommands[f]  # type: ignore
        warnings.warn(
            "`avoid_subparsers=` is deprecated! use `dcargs.conf.AvoidSubparsers[]`"
            " instead.",
            stacklevel=2,
        )

    # Internally, we distinguish between two concepts:
    # - "default", which is used for individual arguments.
    # - "default_instance", which is used for _fields_ (which may be broken down into
    #   one or many arguments, depending on various factors).
    #
    # This could be revisited.
    default_instance_internal: Union[_fields.NonpropagatingMissingType, OutT] = (
        _fields.MISSING_NONPROP if default is None else default
    )

    if not _fields.is_nested_type(cast(Type, f), default_instance_internal):
        dummy_field = cast(
            dataclasses.Field,
            dataclasses.field(
                default=default if default is not None else dataclasses.MISSING
            ),
        )
        f = dataclasses.make_dataclass(
            cls_name="",
            fields=[(_strings.dummy_field_name, cast(Type, f), dummy_field)],
        )
        dummy_wrapped = True
    else:
        dummy_wrapped = False

    # Map a callable to the relevant CLI arguments + subparsers.
    parser_definition = _parsers.ParserSpecification.from_callable(
        f,
        description=description,
        parent_classes=set(),  # Used for recursive calls.
        parent_type_from_typevar=None,  # Used for recursive calls.
        default_instance=default_instance_internal,  # Overrides for default values.
        prefix="",  # Used for recursive calls.
    )

    # If we pass in the --dcargs-print-completion flag: turn termcolor off, and ge the
    # shell we want to generate a completion script for (bash/zsh/tcsh).
    args = sys.argv[1:] if args is None else args
    print_completion = len(args) >= 2 and args[0] == "--dcargs-print-completion"

    formatting_context = _argparse_formatter.ansi_context()
    completion_shell = None
    if print_completion:
        formatting_context = _argparse_formatter.dummy_termcolor_context()
        completion_shell = args[1]

    # Generate parser!
    with formatting_context:
        parser = argparse.ArgumentParser(
            prog=prog,
            formatter_class=_argparse_formatter.make_formatter_class(
                len(parser_definition.args)
            ),
        )
        parser_definition.apply(parser)

        if print_completion:
            assert completion_shell in (
                "bash",
                "zsh",
                "tcsh",
            ), f"Shell should be one `bash`, `zsh`, or `tcsh`, but got {completion_shell}"
            print(
                shtab.complete(
                    parser=parser,
                    shell=completion_shell,
                    root_prefix=f"dcargs_{parser.prog}",
                )
            )
            raise SystemExit()

        value_from_prefixed_field_name = vars(parser.parse_args(args=args))

    if dummy_wrapped:
        value_from_prefixed_field_name = {
            k.replace(_strings.dummy_field_name, ""): v
            for k, v in value_from_prefixed_field_name.items()
        }

    try:
        # Attempt to call `f` using whatever was passed in.
        out, consumed_keywords = _calling.call_from_args(
            f,
            parser_definition,
            default_instance_internal,
            value_from_prefixed_field_name,
            field_name_prefix="",
        )
    except _calling.InstantiationError as e:
        # Emulate argparse's error behavior when invalid arguments are passed in.
        parser.print_usage()
        print()
        print(e.args[0])
        raise SystemExit()

    assert len(value_from_prefixed_field_name.keys() - consumed_keywords) == 0, (
        f"Parsed {value_from_prefixed_field_name.keys()}, but only consumed"
        f" {consumed_keywords}"
    )

    if dummy_wrapped:
        out = getattr(out, _strings.dummy_field_name)
    return out
