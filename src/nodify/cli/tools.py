import typing
from collections.abc import Sequence
from copy import copy
from dataclasses import is_dataclass
from enum import Enum

import yaml


# Classes that hold information regarding how a given parameter should behave in a CLI
# They are meant to be used as metadata for the type annotations. That is, passing them
# to Annotated. E.g.: Annotated[int, CLIArgument(option="some_option")]. Even if they
# are empty, they indicate whether to treat the parameter as an argument or an option.
class CLIArgument:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class CLIOption:
    def __init__(self, *param_decls: str, **kwargs):
        if len(param_decls) > 0:
            kwargs["param_decls"] = param_decls
        self.kwargs = kwargs


def get_params_help(func) -> dict:
    """Gets the text help of parameters from the docstring"""
    params_help = {}

    in_parameters = False
    read_key = None
    arg_content = ""

    for line in func.__doc__.split("\n"):
        if "Parameters" in line:
            in_parameters = True
            space = line.find("Parameters")
            continue

        if in_parameters:
            if len(line) < space + 1:
                continue
            if len(line) > 1 and line[0] != " ":
                break

            if line[space] not in (" ", "-"):
                if read_key is not None:
                    params_help[read_key] = arg_content

                read_key = line.split(":")[0].strip()
                arg_content = ""
            else:
                if arg_content == "":
                    arg_content = line.strip()
                    arg_content = arg_content[0].upper() + arg_content[1:]
                else:
                    arg_content += " " + line.strip()

        if line.startswith("------"):
            break

    if read_key is not None:
        params_help[read_key] = arg_content

    return params_help


def get_dict_param_kwargs(dict_annotation_args):
    def yaml_dict(d: str):
        if isinstance(d, dict):
            return d

        return yaml.safe_load(d)

    argument_kwargs = {"parser": yaml_dict}

    if len(dict_annotation_args) == 2:
        try:
            argument_kwargs["metavar"] = (
                f"YAML_DICT[{dict_annotation_args[0].__name__}: {dict_annotation_args[1].__name__}]"
            )
        except:
            argument_kwargs["metavar"] = (
                f"YAML_DICT[{dict_annotation_args[0]}: {dict_annotation_args[1]}]"
            )

    return argument_kwargs


def get_sequence_param_kwargs(dict_annotation_args):
    def yaml_dict(d: str):
        if isinstance(d, (list, tuple)):
            return d

        return yaml.safe_load(d)

    argument_kwargs = {"parser": yaml_dict}

    if len(dict_annotation_args) == 2:
        try:
            argument_kwargs["metavar"] = f"Sequence"
        except:
            argument_kwargs["metavar"] = f"Sequence"

    return argument_kwargs


# This dictionary keeps the kwargs that should be passed to typer arguments/options
# for a given type. This is for example to be used for types that typer does not
# have built in support for.
_CUSTOM_TYPE_KWARGS = {dict: get_dict_param_kwargs, Sequence: get_sequence_param_kwargs}


def _get_custom_type_kwargs(type_, custom_type_kwargs=None):
    if custom_type_kwargs is None:
        custom_type_kwargs = {}

    custom_type_kwargs = {
        **_CUSTOM_TYPE_KWARGS,
        **{k.__name__: v for k, v in custom_type_kwargs.items()},
        **custom_type_kwargs,
    }

    if hasattr(type_, "__metadata__"):
        type_ = type_.__origin__

    if typing.get_origin(type_) is not None:
        args = typing.get_args(type_)
        type_ = typing.get_origin(type_)
    else:
        args = ()

    try:
        argument_kwargs = custom_type_kwargs.get(type_, {})
        if callable(argument_kwargs):
            argument_kwargs = argument_kwargs(args)
    except:
        argument_kwargs = {}

    if type_ is typing.Literal:
        pass
        # argument_kwargs = {"parser": lambda x: x, **argument_kwargs}
    elif type_ is typing.Union:
        argument_kwargs = {"parser": lambda x: x, **argument_kwargs}
    elif is_dataclass(type_):
        pass

        # def _dataclass_parser(d: str):
        #     if isinstance(d, dict):
        #         return type_(**d)

        #     return type_(**yaml.safe_load(d))

        # argument_kwargs = {"parser": _dataclass_parser, **argument_kwargs}

    return argument_kwargs
