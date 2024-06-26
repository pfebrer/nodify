import inspect
import typing
from copy import copy
from enum import Enum

import typer
from typing_extensions import Annotated


def annotate_typer(func, custom_type_kwargs=None):
    """Annotates a function for a typer app.

    It returns a new function, the original function is not modified.
    """
    # Get the help message for all parameters found at the docstring
    params_help = get_params_help(func)

    # Get the original signature of the function
    sig = inspect.signature(func)

    # Loop over parameters in the signature, modifying them to include the
    # typer info.
    new_parameters = []
    for param in sig.parameters.values():

        annotation = param.annotation
        if typing.get_origin(annotation) is typing.Union:
            args = typing.get_args(annotation)
            if len(args) == 2 and (args[-1] is None or args[-1] is type(None)):
                annotation = args[0]

        argument_kwargs = _get_custom_type_kwargs(annotation, custom_type_kwargs)

        default = param.default
        if isinstance(param.default, Enum):
            default = default.value

        typer_arg_cls = (
            typer.Argument if param.default == inspect.Parameter.empty else typer.Option
        )
        if hasattr(annotation, "__metadata__"):
            for meta in annotation.__metadata__:
                if isinstance(meta, CLIArgument):
                    typer_arg_cls = typer.Argument
                    argument_kwargs.update(meta.kwargs)
                elif isinstance(meta, CLIOption):
                    typer_arg_cls = typer.Option
                    argument_kwargs.update(meta.kwargs)

        if "param_decls" in argument_kwargs:
            argument_args = argument_kwargs.pop("param_decls")
        else:
            argument_args = []

        if typing.get_origin(annotation) is typing.Union:
            annotation = str

        # print("PREV", param.annotation)
        # print(annotation)

        new_parameters.append(
            param.replace(
                default=default,
                annotation=Annotated[
                    annotation,
                    typer_arg_cls(
                        *argument_args,
                        help=params_help.get(param.name),
                        **argument_kwargs,
                    ),
                ],
            )
        )

    # Create a copy of the function and update it with the modified signature.
    # Also remove parameters documentation from the docstring.
    annotated_func = copy(func)

    annotated_func.__signature__ = sig.replace(parameters=new_parameters)
    annotated_func.__doc__ = func.__doc__[: func.__doc__.find("Parameters\n")]

    return annotated_func


# ----------------------------------------------------
#           Typer markdown patch
# ----------------------------------------------------
# This is a patch for typer to allow for markdown in the help messages (see https://github.com/tiangolo/typer/issues/678)

# import inspect
# from typing import Union, Iterable

# import click
# from rich.console import group
# from rich.markdown import Markdown
# from rich.text import Text
# from typer.core import MarkupMode
# from typer.rich_utils import (
#     MARKUP_MODE_MARKDOWN,
#     STYLE_HELPTEXT_FIRST_LINE,
#     _make_rich_rext,
# )


# @group()
# def _get_custom_help_text(
#     *,
#     obj: Union[click.Command, click.Group],
#     markup_mode: MarkupMode,
# ) -> Iterable[Union[Markdown, Text]]:
#     # Fetch and dedent the help text
#     help_text = inspect.cleandoc(obj.help or "")

#     # Trim off anything that comes after \f on its own line
#     help_text = help_text.partition("\f")[0]

#     # Get the first paragraph
#     first_line = help_text.split("\n\n")[0]
#     # Remove single linebreaks
#     if markup_mode != MARKUP_MODE_MARKDOWN and not first_line.startswith("\b"):
#         first_line = first_line.replace("\n", " ")
#     yield _make_rich_rext(
#         text=first_line.strip(),
#         style=STYLE_HELPTEXT_FIRST_LINE,
#         markup_mode=markup_mode,
#     )

#     # Get remaining lines, remove single line breaks and format as dim
#     remaining_paragraphs = help_text.split("\n\n")[1:]
#     if remaining_paragraphs:
#         remaining_lines = inspect.cleandoc(
#             "\n\n".join(remaining_paragraphs).replace("<br/>", "\\")
#         )
#         yield _make_rich_rext(
#             text=remaining_lines,
#             style="cyan",
#             markup_mode=markup_mode,
#         )


# import typer.rich_utils

# typer.rich_utils._get_help_text = _get_custom_help_text
