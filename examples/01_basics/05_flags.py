"""Booleans and Flags

Booleans can either be expected to be explicitly passed in, or, if given a default
value, automatically converted to flags.

To turn off conversion, see :class:`tyro.conf.FlagConversionOff`.

Usage:
`python ./05_flags.py --help`
`python ./05_flags.py --boolean True`
`python ./05_flags.py --boolean False --flag-a`
`python ./05_flags.py --boolean False --no-flag-b`
"""

import dataclasses

import tyro


@dataclasses.dataclass
class Args:
    # Boolean. This expects an explicit "True" or "False".
    boolean: bool

    # Optional boolean. Same as above, but can be omitted.
    optional_boolean: bool | None = None

    # Pass --flag-a in to set this value to True.
    flag_a: bool = False

    # Pass --no-flag-b in to set this value to False.
    flag_b: bool = True


if __name__ == "__main__":
    args = tyro.cli(Args)
    print(args)
