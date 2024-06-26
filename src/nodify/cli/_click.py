import dataclasses
import inspect
import typing
from copy import copy
from dataclasses import is_dataclass
from enum import Enum

import click
import yaml

from .tools import CLIArgument, CLIOption, _get_custom_type_kwargs, get_params_help


class ChoiceNoString(click.Choice):
    """Click type to support Literal types."""

    def __init__(self, choices, *args, **kwargs):
        self._conversion = {str(choice): choice for choice in choices}
        super().__init__(list(self._conversion), *args, **kwargs)

    def convert(self, value, param, ctx):
        return self._conversion[value]


class DataclassType(click.ParamType):
    """Click type to support dataclasses."""

    name = "dataclass"

    def __init__(self, dataclass, *args, **kwargs):
        self.dataclass = dataclass
        self.name = dataclass.__name__
        super().__init__(*args, **kwargs)

    def convert(self, value, param, ctx):

        def _dataclass_parser(d: str):
            if isinstance(d, dict):
                return self.dataclass(**d)
            elif value.startswith("{"):
                return self.dataclass(**yaml.safe_load(d))
            else:
                values = [val.strip() for val in value.split(" ")]
                fields = dataclasses.fields(self.dataclass)

                d = "{"
                for k, v in zip(fields, values):
                    d += f"{k.name}: {v}, "

                d = d[:-2] + "}"
                return self.dataclass(**yaml.safe_load(d))

        return _dataclass_parser(value)

    def get_metavar(self, param):

        try:
            s = typing.get_type_hints(self.dataclass)

            def _san_type(name):

                type_ = s[name]
                if typing.get_origin(type_) is typing.Union:
                    args = typing.get_args(type_)
                    if len(args) == 2 and (args[-1] is None or args[-1] is type(None)):
                        type_ = args[0]

                if typing.get_origin(type_) is typing.Literal:
                    return "|".join([str(x) for x in typing.get_args(type_)])

                if hasattr(type_, "__name__"):
                    return type_.__name__

                return type_

            return (
                f"{self.name}"
                + "{\n  "
                + "\n  ".join(
                    [
                        f"{field.name}: {_san_type(field.name)}"
                        for field in dataclasses.fields(self.dataclass)
                    ]
                )
                + "\n}\n"
            )
        except:
            return self.name


def decorate_click(func, custom_type_kwargs=None):
    """Decorates a function with arguments for a click app.

    It returns a new function, the original function is not modified.
    """
    # Get the help message for all parameters found at the docstring
    params_help = get_params_help(func)

    # Get the original signature of the function
    sig = inspect.signature(func)

    # Loop over parameters in the signature, modifying them to include the
    # typer info.
    for param in reversed(sig.parameters.values()):

        annotation = param.annotation
        if typing.get_origin(annotation) is typing.Union:
            args = typing.get_args(annotation)
            if len(args) == 2 and (args[-1] is None or args[-1] is type(None)):
                annotation = args[0]

        argument_kwargs = _get_custom_type_kwargs(annotation, custom_type_kwargs)

        default = param.default
        if isinstance(param.default, Enum):
            default = default.value

        click_decorator = (
            click.argument if param.default == inspect.Parameter.empty else click.option
        )
        if hasattr(annotation, "__metadata__"):
            for meta in annotation.__metadata__:
                if isinstance(meta, CLIArgument):
                    click_decorator = click.argument
                    argument_kwargs.update(meta.kwargs)
                elif isinstance(meta, CLIOption):
                    click_decorator = click.option
                    argument_kwargs.update(meta.kwargs)

        if "param_decls" in argument_kwargs:
            argument_args = argument_kwargs.pop("param_decls")
        else:
            if click_decorator is click.option:
                argument_args = [f"--{param.name}", param.name]
                argument_kwargs["default"] = default
                argument_kwargs["help"] = params_help.get(param.name, "")
                argument_kwargs["show_default"] = True
            else:
                argument_args = [param.name]
                # argument_kwargs["required"] = True

        if annotation is inspect.Parameter.empty:
            annotation = str
        elif annotation is bool:
            argument_kwargs["is_flag"] = True
            argument_args = [f"--{param.name}/--no-{param.name}", param.name]

        origin = typing.get_origin(annotation)
        if origin is typing.Union:
            annotation = str
        elif origin is tuple:
            args = typing.get_args(annotation)
            argument_kwargs["nargs"] = len(args)
            annotation = args
        elif origin is typing.Literal:
            args = typing.get_args(annotation)
            annotation = ChoiceNoString(args)
        elif is_dataclass(annotation):
            annotation = DataclassType(annotation)

        # print("PREV", param.annotation)
        # print(annotation)

        if "parser" in argument_kwargs:
            argument_kwargs["type"] = argument_kwargs.pop("parser")
        else:
            argument_kwargs["type"] = annotation

        func = click_decorator(*argument_args, **argument_kwargs)(func)

    # Create a copy of the function and update it with the modified signature.
    # Also remove parameters documentation from the docstring.
    # annotated_func = copy(func)

    # annotated_func.__signature__ = sig.replace(parameters=new_parameters)
    func.__doc__ = func.__doc__[: func.__doc__.find("Parameters\n")]

    return func
